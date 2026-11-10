"""
Commander Brackets (Wizards of the Coast, 2025; Game Changers list updated
February 9, 2026). Estimates the lowest bracket a deck fits in from what can
be checked with card data:

    Bracket            Game Changers   Mass land denial   Extra turns
    1 Exhibition       none            no                 restricted
    2 Core             none            no                 not chained
    3 Upgraded         up to 3         no                 not chained
    4 Optimized        any             yes                yes
    5 cEDH             any             yes                yes

Bracket 1 vs 2 depends on the deck's theme, and 4 vs 5 on a competitive
focus, so those are shown as ranges. Two-card combos and the expected game
length can't be checked from card data. Tutors have no restriction since
the October 2025 update.

The card lists come from Scryfall searches (kept up to date by Scryfall):
    is:gamechanger           -> the official Game Changers list
    otag:mass-land-denial    -> mass land denial (Scryfall tagger)
    otag:extra-turn          -> cards that give extra turns (Scryfall tagger)
"""

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from api.scryfall_api import search_card_names
from src.config import BASE_DIR

LISTS_FILE = BASE_DIR / "cache" / "brackets.json"

# The Game Changers list changes a few times a year: refresh weekly
LISTS_MAX_AGE = timedelta(days=7)

LIST_QUERIES = {
    "game_changers": "is:gamechanger",
    "mass_land_denial": "otag:mass-land-denial",
    "extra_turns": "otag:extra-turn",
}

BRACKET_NAMES = {1: "Exhibition", 2: "Core", 3: "Upgraded", 4: "Optimized", 5: "cEDH"}

# Bracket 3 allows up to this many Game Changers
MAX_GAME_CHANGERS_BRACKET_3 = 3

_lists = None


@dataclass
class BracketEstimate:
    """
    bracket: lowest bracket the deck fits in (1-4).
    label: what to show, e.g. "Bracket 1–2 · Exhibition / Core".
    reasons: why (one line each).
    """

    bracket: int
    label: str
    short_label: str
    reasons: list = field(default_factory=list)
    game_changers: list = field(default_factory=list)
    mass_land_denial: list = field(default_factory=list)
    extra_turns: list = field(default_factory=list)


# ==================================
# CARD LISTS
# ==================================

def _read_lists():

    global _lists

    if _lists is None:
        try:
            _lists = json.loads(LISTS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _lists = {}

    return _lists


def lists_ready():
    """True when the three card lists are on disk."""

    data = _read_lists()
    return all(key in data for key in LIST_QUERIES)


def lists_need_update():

    data = _read_lists()

    if not lists_ready():
        return True

    try:
        fetched = datetime.fromisoformat(data.get("fetched_at", ""))
    except ValueError:
        return True

    return datetime.now() - fetched > LISTS_MAX_AGE


def update_lists():
    """
    Download the three card lists from Scryfall (network: background
    thread). Return True if they changed. Raise ScryfallError on failure.
    """

    global _lists

    new = {key: sorted(search_card_names(query)) for key, query in LIST_QUERIES.items()}
    old = _read_lists()
    changed = any(new[key] != old.get(key) for key in LIST_QUERIES)

    new["fetched_at"] = datetime.now().isoformat(timespec="seconds")

    LISTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=LISTS_FILE.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        json.dump(new, file, indent=1)
    os.replace(temp_name, LISTS_FILE)

    _lists = new
    return changed


def _names(key):
    return {name.lower() for name in _read_lists().get(key, [])}


def _matches(card_name, names):
    """
    Double-faced cards: "Front // Back" matches if any face is in the list.
    """

    lowered = card_name.lower()
    return lowered in names or any(face in names for face in lowered.split(" // "))


# ==================================
# ESTIMATE
# ==================================

def estimate_bracket(deck_cards):
    """
    Estimate the bracket of a Commander deck from its commander + main
    cards. Return a BracketEstimate, or None while the card lists aren't
    downloaded yet.
    """

    if not lists_ready():
        return None

    game_changer_names = _names("game_changers")
    land_denial_names = _names("mass_land_denial")
    extra_turn_names = _names("extra_turns")

    playing = sorted(
        {entry.name for entry in deck_cards if entry.section in ("commander", "main")}
    )

    game_changers = [name for name in playing if _matches(name, game_changer_names)]
    land_denial = [name for name in playing if _matches(name, land_denial_names)]
    extra_turns = [name for name in playing if _matches(name, extra_turn_names)]

    bracket = 1
    reasons = []

    if game_changers:
        if len(game_changers) <= MAX_GAME_CHANGERS_BRACKET_3:
            bracket = max(bracket, 3)
        else:
            bracket = max(bracket, 4)
        reasons.append(f"{len(game_changers)} Game Changer{'s' if len(game_changers) != 1 else ''}: "
                       + ", ".join(game_changers))
    else:
        reasons.append("No Game Changers.")

    if land_denial:
        bracket = max(bracket, 4)
        reasons.append("Mass land denial: " + ", ".join(land_denial))

    if extra_turns:
        bracket = max(bracket, 2)
        reasons.append(
            "Extra turns: " + ", ".join(extra_turns)
            + " (below Bracket 4 they must not be chained)"
        )

    if bracket == 1:
        number, name = "1–2", f"{BRACKET_NAMES[1]} / {BRACKET_NAMES[2]}"
        reasons.append("Bracket 1 or 2 depends on how casual and themed the deck is.")
    elif bracket == 4:
        number, name = "4–5", f"{BRACKET_NAMES[4]} / {BRACKET_NAMES[5]}"
        reasons.append("Bracket 5 (cEDH) is for decks built for the competitive scene.")
    else:
        number, name = str(bracket), BRACKET_NAMES[bracket]

    reasons.append("Not checked: two-card combos and how fast the deck wins.")

    return BracketEstimate(
        bracket=bracket,
        label=f"Bracket {number} · {name}",
        short_label=f"Bracket {number}",
        reasons=reasons,
        game_changers=game_changers,
        mass_land_denial=land_denial,
        extra_turns=extra_turns,
    )
