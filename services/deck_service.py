"""
Deck builder logic: formats, grouping by card type and deck validation.
The UI talks to this module; it talks to database.deck_manager.
"""

import re
from collections import Counter
from dataclasses import dataclass

from api.scryfall_api import get_cards_by_identifiers
from database import deck_manager
from database.database_manager import add_card, get_all_cards
from models.card import Card
from models.deck import SECTION_LABELS, SECTIONS
from services.card_service import is_basic_land

# ==================================
# FORMATS
# ==================================

# key (as used by Scryfall's "legalities") -> rules
FORMATS = {
    "commander": {"label": "Commander", "size": 100, "copies": 1, "sideboard": 0, "commander": True},
    "standard": {"label": "Standard", "size": 60, "copies": 4, "sideboard": 15, "commander": False},
    "pioneer": {"label": "Pioneer", "size": 60, "copies": 4, "sideboard": 15, "commander": False},
    "modern": {"label": "Modern", "size": 60, "copies": 4, "sideboard": 15, "commander": False},
    "legacy": {"label": "Legacy", "size": 60, "copies": 4, "sideboard": 15, "commander": False},
    "vintage": {"label": "Vintage", "size": 60, "copies": 4, "sideboard": 15, "commander": False},
    "pauper": {"label": "Pauper", "size": 60, "copies": 4, "sideboard": 15, "commander": False},
}

DEFAULT_FORMAT = "commander"


def format_label(deck_format):
    return FORMATS.get(deck_format, {}).get("label", deck_format.capitalize())


def is_commander_format(deck_format):
    return FORMATS.get(deck_format, {}).get("commander", False)


def deck_size(deck_format):
    return FORMATS.get(deck_format, FORMATS[DEFAULT_FORMAT])["size"]


# ==================================
# GROUPING BY TYPE
# ==================================

# Order of the groups in the deck view. A card goes to the first group
# whose type appears in its (front face) type line.
TYPE_GROUPS = [
    ("Lands", "Land"),
    ("Creatures", "Creature"),
    ("Planeswalkers", "Planeswalker"),
    ("Battles", "Battle"),
    ("Instants", "Instant"),
    ("Sorceries", "Sorcery"),
    ("Artifacts", "Artifact"),
    ("Enchantments", "Enchantment"),
]

# Display order (lands at the end, as most deck sites do)
TYPE_GROUP_ORDER = [
    "Creatures", "Planeswalkers", "Battles", "Instants", "Sorceries",
    "Artifacts", "Enchantments", "Lands", "Other",
]


def type_group(card):
    """
    "Creatures", "Lands"... for a card. Uses the front face of double-faced
    cards. "Artifact Land" -> Lands, "Artifact Creature" -> Creatures.
    """

    front = (card.type_line or "").split(" // ")[0]

    for group, card_type in TYPE_GROUPS:
        if card_type in front:
            return group

    return "Other"


def group_deck_cards(deck_cards):
    """
    Return [(title, [DeckCard])] in display order:
    Commander, the type groups of the main deck, Sideboard, Maybeboard.
    Empty groups are left out.
    """

    groups = []

    commanders = [entry for entry in deck_cards if entry.section == "commander"]
    if commanders:
        groups.append(("Commander", commanders))

    main = [entry for entry in deck_cards if entry.section == "main"]
    by_type = {}
    for entry in main:
        by_type.setdefault(type_group(entry.card), []).append(entry)

    for group in TYPE_GROUP_ORDER:
        if group in by_type:
            groups.append((group, by_type[group]))

    for section in ("sideboard", "maybeboard"):
        entries = [entry for entry in deck_cards if entry.section == section]
        if entries:
            groups.append((SECTION_LABELS[section], entries))

    return groups


# ==================================
# VALIDATION
# ==================================

@dataclass
class DeckIssue:
    """A validation message. level: "error" (breaks the format) or "warning"."""

    level: str
    message: str


# "A deck can have any number of cards named ..." (Relentless Rats...)
ANY_NUMBER = re.compile(r"a deck can have any number of cards named", re.IGNORECASE)

# "A deck can have up to seven cards named ..." (Seven Dwarves...)
UP_TO = re.compile(r"a deck can have up to (\w+) cards named", re.IGNORECASE)

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10,
}


def copy_limit(card, deck_format):
    """
    Maximum copies of a card in this format, or None for "any number".
    """

    if is_basic_land(card):
        return None

    text = card.oracle_text or ""

    if ANY_NUMBER.search(text):
        return None

    match = UP_TO.search(text)
    if match:
        word = match.group(1).lower()
        return NUMBER_WORDS.get(word) or (int(word) if word.isdigit() else None)

    limit = FORMATS.get(deck_format, FORMATS[DEFAULT_FORMAT])["copies"]

    # Vintage: restricted cards are limited to one copy
    if card.legalities.get(deck_format) == "restricted":
        return 1

    return limit


def can_be_commander(card):

    type_line = card.type_line or ""
    front = type_line.split(" // ")[0]

    return (
        ("Legendary" in front and "Creature" in front)
        or "can be your commander" in (card.oracle_text or "").lower()
    )


def _allows_two_commanders(commanders):
    """
    Partner, "Friends forever", Doctor's companion and "Choose a Background"
    let a deck have two commanders.
    """

    texts = [(card.oracle_text or "") for card in commanders]
    types = [(card.type_line or "") for card in commanders]

    if all("Partner" in text or "Friends forever" in text for text in texts):
        return True

    if any("Choose a Background" in text for text in texts) and any("Background" in t for t in types):
        return True

    if any("Doctor's companion" in text for text in texts) and any("Doctor" in t for t in types):
        return True

    return False


def validate_deck(deck_format, deck_cards):
    """
    Check the deck against its format. Return a list of DeckIssue
    (empty = the deck is legal). The maybeboard is ignored.
    """

    rules = FORMATS.get(deck_format, FORMATS[DEFAULT_FORMAT])
    label = rules["label"]
    issues = []

    playing = [entry for entry in deck_cards if entry.section in ("commander", "main")]
    commanders = [entry.card for entry in deck_cards if entry.section == "commander"]
    sideboard = [entry for entry in deck_cards if entry.section == "sideboard"]

    main_count = sum(entry.quantity for entry in playing)

    # ---------- Size ----------

    if rules["commander"]:
        if main_count != rules["size"]:
            issues.append(DeckIssue(
                "error",
                f"A {label} deck needs exactly {rules['size']} cards "
                f"(commander included): it has {main_count}.",
            ))
    elif main_count < rules["size"]:
        issues.append(DeckIssue(
            "error", f"A {label} deck needs at least {rules['size']} cards: it has {main_count}."
        ))

    side_count = sum(entry.quantity for entry in sideboard)

    if rules["commander"] and side_count:
        cards_text = "1 sideboard card doesn't" if side_count == 1 else f"{side_count} sideboard cards don't"
        issues.append(DeckIssue("warning", f"{label} has no sideboard: {cards_text} count."))
    elif not rules["commander"] and side_count > rules["sideboard"]:
        issues.append(DeckIssue(
            "error", f"The sideboard can have at most {rules['sideboard']} cards: it has {side_count}."
        ))

    # ---------- Copies (by name, all editions together) ----------

    counted = playing if rules["commander"] else playing + sideboard
    copies = Counter()
    cards_by_name = {}

    for entry in counted:
        copies[entry.name] += entry.quantity
        cards_by_name[entry.name] = entry.card

    for name, count in sorted(copies.items()):
        limit = copy_limit(cards_by_name[name], deck_format)
        if limit is not None and count > limit:
            issues.append(DeckIssue(
                "error", f"{name}: {count} copies, the limit is {limit}."
            ))

    # ---------- Legality ----------

    for name in sorted(copies):
        card = cards_by_name[name]
        legality = card.legalities.get(deck_format)

        # No data (old card line): nothing to check
        if legality is None or legality in ("legal", "restricted"):
            continue

        reason = "banned" if legality == "banned" else "not legal"
        issues.append(DeckIssue("error", f"{name} is {reason} in {label}."))

    # ---------- Commander rules ----------

    if rules["commander"]:

        if not commanders:
            issues.append(DeckIssue("error", "Choose a commander (Commander section)."))

        elif len(commanders) > 2:
            issues.append(DeckIssue("error", f"A deck can have at most 2 commanders: it has {len(commanders)}."))

        else:
            if len(commanders) == 2 and not _allows_two_commanders(commanders):
                issues.append(DeckIssue(
                    "warning",
                    "Two commanders are only allowed with Partner, Friends forever or a Background.",
                ))

            for commander in commanders:
                if not can_be_commander(commander):
                    issues.append(DeckIssue(
                        "warning", f"{commander.name} is not a legendary creature."
                    ))

            identity = set()
            for commander in commanders:
                identity.update(commander.color_identity)

            outside = sorted({
                entry.name for entry in playing
                if entry.section == "main" and not set(entry.card.color_identity) <= identity
            })

            for name in outside:
                issues.append(DeckIssue(
                    "error", f"{name} is outside the commander's color identity."
                ))

    # Errors first
    issues.sort(key=lambda issue: issue.level != "error")
    return issues


# ==================================
# FACADE FOR THE UI
# ==================================

def get_decks():
    return deck_manager.get_decks()


def get_deck(deck_id):
    return deck_manager.get_deck(deck_id)


def create_deck(name, deck_format=DEFAULT_FORMAT):
    return deck_manager.create_deck(name.strip(), deck_format)


def rename_deck(deck_id, name):
    deck_manager.update_deck(deck_id, name=name.strip())


def set_deck_format(deck_id, deck_format):
    deck_manager.update_deck(deck_id, deck_format=deck_format)


def delete_deck(deck_id):
    deck_manager.delete_deck(deck_id)


def get_deck_cards(deck_id):
    return deck_manager.get_deck_cards(deck_id)


def add_card_to_deck(deck_id, card, quantity=1, section="main"):
    return deck_manager.add_card_to_deck(deck_id, card, quantity, section)


def set_deck_card_quantity(deck_card_id, quantity):
    deck_manager.set_deck_card_quantity(deck_card_id, quantity)


def remove_deck_cards(deck_card_ids):
    deck_manager.remove_deck_cards(deck_card_ids)


def move_deck_card(deck_card_id, section):
    return deck_manager.move_deck_card(deck_card_id, section)


def change_deck_card_printing(deck_card_id, new_card):
    return deck_manager.change_deck_card_printing(deck_card_id, new_card)


# ==================================
# COLLECTION: OWNED / MISSING CARDS
# ==================================

# Sections whose cards you need to own to play the deck (not the maybeboard)
NEEDED_SECTIONS = ("commander", "main", "sideboard")


@dataclass
class MissingCard:
    """
    A card of the deck you don't have enough copies of (counted by name:
    any edition of the collection counts). entry is the deck line used for
    its edition, price and image.
    """

    name: str
    entry: object
    needed: int
    owned: int

    @property
    def missing(self):
        return max(0, self.needed - self.owned)

    def cost(self, currency):
        """Price of the missing copies, or None if there's no price."""
        price = self.entry.card.price(currency)
        return None if price is None else price * self.missing


def collection_counts():
    """{card name (lowercase): copies in the collection, all editions}."""

    counts = Counter()
    for card in get_all_cards():
        counts[(card.name or "").lower()] += card.quantity or 0
    return counts


def needed_counts(deck_cards):
    """{card name (lowercase): copies the deck needs} (maybeboard excluded)."""

    counts = Counter()
    for entry in deck_cards:
        if entry.section in NEEDED_SECTIONS:
            counts[entry.name.lower()] += entry.quantity
    return counts


def missing_cards(deck_cards, owned=None):
    """
    The deck's cards you don't have enough copies of, sorted by name.
    owned: result of collection_counts() (read from the database if None).
    """

    owned = collection_counts() if owned is None else owned
    needed = needed_counts(deck_cards)

    first_entry = {}
    for entry in deck_cards:
        if entry.section in NEEDED_SECTIONS:
            first_entry.setdefault(entry.name.lower(), entry)

    result = [
        MissingCard(entry.name, entry, needed[key], owned.get(key, 0))
        for key, entry in first_entry.items()
        if owned.get(key, 0) < needed[key]
    ]

    return sorted(result, key=lambda item: item.name.lower())


def add_to_collection(card, quantity, foil=False):
    """
    Register copies you got of a deck card (a Card from Scryfall or a
    deck line's card): they are added to the collection, foil or not.
    """

    copy = Card(
        name=card.name, set_name=card.set_name, type_line=card.type_line,
        mana_cost=card.mana_cost, rarity=card.rarity, image_url=card.image_url,
        quantity=quantity, scryfall_id=card.scryfall_id, set_code=card.set_code,
        collector_number=card.collector_number,
        price_eur=card.price_eur, price_eur_foil=card.price_eur_foil,
        price_usd=card.price_usd, price_usd_foil=card.price_usd_foil,
        foil=foil,
    )
    add_card(copy)


# ==================================
# STATS
# ==================================

# Mana curve columns: 0, 1, ... 6, "7+"
CURVE_MAX = 7


@dataclass
class DeckStats:
    curve: list            # copies per mana value 0..CURVE_MAX (last = 7+), lands excluded
    colors: dict           # {"W": copies, ...} cards of each color ("C" = colorless)
    types: list            # [(group, copies)] in display order
    average_mana_value: float
    lands: int
    nonlands: int


def deck_stats(deck_cards):
    """
    Mana curve, colors and card types of the commander + main deck.
    """

    playing = [entry for entry in deck_cards if entry.section in ("commander", "main")]

    curve = [0] * (CURVE_MAX + 1)
    colors = Counter()
    types = Counter()
    total_mana_value = 0
    lands = nonlands = 0

    for entry in playing:
        card = entry.card
        group = type_group(card)
        types[group] += entry.quantity

        if group == "Lands":
            lands += entry.quantity
            continue

        nonlands += entry.quantity
        mana_value = int(card.cmc or 0)
        curve[min(mana_value, CURVE_MAX)] += entry.quantity
        total_mana_value += (card.cmc or 0) * entry.quantity

        card_colors = card.colors or []
        if card_colors:
            for color in card_colors:
                colors[color] += entry.quantity
        else:
            colors["C"] += entry.quantity

    ordered_types = [(group, types[group]) for group in TYPE_GROUP_ORDER if types[group]]

    return DeckStats(
        curve=curve,
        colors=dict(colors),
        types=ordered_types,
        average_mana_value=(total_mana_value / nonlands) if nonlands else 0.0,
        lands=lands,
        nonlands=nonlands,
    )


def add_collection_cards_to_deck(deck_id, cards, quantity, section):
    """
    Add collection cards to a deck, keeping their edition. The collection
    doesn't store mana value, colors, legalities... so the printings are
    fetched from Scryfall in one batch (network: call it from a background
    thread). Return (added card lines, names not found).
    Raise ScryfallError on connection problems.
    """

    identifiers = [
        {"id": card.scryfall_id} if card.scryfall_id else {"name": card.name}
        for card in cards
    ]

    results = get_cards_by_identifiers(identifiers)

    added = 0
    not_found = []

    for card, (_, fresh) in zip(cards, results):
        if fresh is None:
            not_found.append(card.name)
            continue
        deck_manager.add_card_to_deck(deck_id, fresh, quantity, section)
        added += 1

    return added, not_found


@dataclass
class DeckSummary:
    """What other pages (life counter) need to know about a deck."""

    deck: object
    commanders: list          # Card objects (0, 1 or 2)
    bracket: object           # BracketEstimate or None (not Commander / lists not ready)


def deck_summary(deck_id):
    """DeckSummary of a deck, or None if it doesn't exist anymore."""

    deck = deck_manager.get_deck(deck_id)
    if deck is None:
        return None

    entries = deck_manager.get_deck_cards(deck_id)
    commanders = [entry.card for entry in entries if entry.section == "commander"]

    bracket = None
    if is_commander_format(deck.format):
        from services.bracket_service import estimate_bracket
        bracket = estimate_bracket(entries)

    return DeckSummary(deck=deck, commanders=commanders, bracket=bracket)


def create_deck_from_list(name, deck_format, found):
    """
    Create a deck from an imported list. found is [(ListEntry, Card)] as
    returned by list_service.resolve_entries(); each card goes to its
    entry's section (repeated lines are added up). Return the new deck id.
    """

    deck_id = deck_manager.create_deck(name.strip(), deck_format)

    for entry, card in found:
        section = entry.section if entry.section in SECTIONS else "main"
        deck_manager.add_card_to_deck(deck_id, card, entry.quantity, section)

    return deck_id


__all__ = [
    "FORMATS", "SECTIONS", "SECTION_LABELS", "DeckIssue",
    "format_label", "is_commander_format", "deck_size",
    "type_group", "group_deck_cards", "validate_deck", "copy_limit", "can_be_commander",
    "get_decks", "get_deck", "create_deck", "rename_deck", "set_deck_format",
    "delete_deck", "get_deck_cards", "add_card_to_deck", "set_deck_card_quantity",
    "remove_deck_cards", "move_deck_card", "change_deck_card_printing", "create_deck_from_list",
    "MissingCard", "collection_counts", "needed_counts", "missing_cards", "add_to_collection",
    "DeckStats", "deck_stats", "CURVE_MAX", "add_collection_cards_to_deck",
    "DeckSummary", "deck_summary",
]
