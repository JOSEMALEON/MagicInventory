"""
Import and export the collection as card lists.

Text format (one card per line, the usual format of Moxfield/Arena lists):

    4 Sol Ring
    1 Sol Ring (CMM) 410      <- optional set code and collector number
    2x Lightning Bolt         <- "2x" is also accepted

Empty lines, comments (# or //) and section headers ("Deck", "Sideboard:",
"Commander"...) are ignored. CSV files need a "Name" column and may have
"Quantity", "Set Code" and "Collector Number" columns.
"""

import csv
import io
import re
from dataclasses import dataclass

from api.scryfall_api import ScryfallError, get_cards_by_identifiers, search_card_by_name
from database.database_manager import add_card, get_all_cards

# "4 Sol Ring", "4x Sol Ring", "4 Sol Ring (CMM) 410", "4 Sol Ring (CMM)"
LINE_PATTERN = re.compile(
    r"""^
    (?P<quantity>\d+)\s*x?\s+                 # quantity, optional "x"
    (?P<name>.+?)                             # card name
    (?:\s+\((?P<set>[A-Za-z0-9]{2,6})\)       # optional (SET)
       (?:\s+(?P<number>[A-Za-z0-9★\-]+))?    # optional collector number
    )?
    \s*$""",
    re.VERBOSE,
)

# Markers some sites add at the end of a line: "*F*" (foil), "*E*" (etched),
# "*CMDR*" (this card is the commander)
END_MARKER = re.compile(r"\s+\*([A-Za-z]+)\*\s*$")

# Section titles in exported decks -> deck section (None = skip its cards)
SECTION_HEADERS = {
    "commander": "commander",
    "commanders": "commander",
    "deck": "main",
    "main": "main",
    "mainboard": "main",
    "maindeck": "main",
    "sideboard": "sideboard",
    "side": "sideboard",
    "companion": "sideboard",      # the companion starts in the sideboard
    "maybeboard": "maybeboard",
    "considering": "maybeboard",
    "tokens": None,
    "about": "about",              # MTG Arena: "About" + "Name My deck"
}

# Accepted CSV column names (lowercase) for each field
CSV_COLUMNS = {
    "quantity": ("quantity", "qty", "count", "amount"),
    "name": ("name", "card", "card name"),
    "set": ("set code", "set_code", "edition code", "set"),
    "number": ("collector number", "collector_number", "number", "cn"),
    "section": ("section", "board", "category"),
    "foil": ("foil", "finish", "is foil", "printing"),
}

# Values of a CSV "Foil" column that mean foil
FOIL_VALUES = {"foil", "yes", "y", "true", "1", "x", "etched", "f"}

# Order and titles used when writing a deck list
DECK_TEXT_SECTIONS = [
    ("commander", "Commander"),
    ("main", "Deck"),
    ("sideboard", "Sideboard"),
    ("maybeboard", "Maybeboard"),
]

MAX_QUANTITY = 999

# Fuzzy suggestions cost one request each: limit them
MAX_SUGGESTIONS = 20


@dataclass
class ListEntry:
    """One valid line of a card list."""

    line: int
    quantity: int
    name: str
    set_code: str = None
    collector_number: str = None
    # Deck section ("commander", "main"...); only used when importing decks
    section: str = "main"
    # Foil copies (marked "*F*" or "*E*" in the list, or a CSV "Foil" column)
    foil: bool = False

    def describe(self):
        """ "Sol Ring (CMM #410)" or just "Sol Ring". """

        if self.set_code and self.collector_number:
            return f"{self.name} ({self.set_code.upper()} #{self.collector_number})"
        if self.set_code:
            return f"{self.name} ({self.set_code.upper()})"
        return self.name


@dataclass
class ListProblem:
    """A line that can't be added: bad syntax or card not found."""

    line: int
    message: str

    def __str__(self):
        return f"Line {self.line}: {self.message}"


# ==================================
# PARSING
# ==================================

def _section_header(line):
    """
    If the line is a section title ("Sideboard", "SIDEBOARD:", "// Commander"),
    return its key in SECTION_HEADERS; otherwise None.
    """

    title = line.lstrip("/").strip().rstrip(":").strip().lower()
    return title if title in SECTION_HEADERS else None


def _parse_card_line(number, raw_line, line):
    """
    Parse "4 Sol Ring (CMM) 410 *F*". Return (ListEntry, None) or
    (None, ListProblem). entry.section is "commander" if marked *CMDR*.
    """

    markers = set()
    while True:
        marker = END_MARKER.search(line)
        if not marker:
            break
        markers.add(marker.group(1).upper())
        line = line[:marker.start()]

    match = LINE_PATTERN.match(line)

    if not match:
        return None, ListProblem(
            number,
            f"“{raw_line.strip()}” is not valid. Use “quantity name”, e.g. “1 Sol Ring”.",
        )

    quantity = int(match["quantity"])

    if not 1 <= quantity <= MAX_QUANTITY:
        return None, ListProblem(
            number, f"quantity {quantity} must be between 1 and {MAX_QUANTITY}."
        )

    entry = ListEntry(
        line=number,
        quantity=quantity,
        name=match["name"].strip(),
        set_code=match["set"].lower() if match["set"] else None,
        collector_number=match["number"],
    )

    if markers & {"F", "E"}:
        entry.foil = True

    if "CMDR" in markers:
        entry.section = "commander"

    return entry, None


def parse_deck_list(text):
    """
    Parse a deck list with sections (Moxfield / Archidekt / MTG Arena):

        About
        Name Atraxa superfriends
        Commander
        1 Atraxa, Praetors' Voice
        Deck
        1 Sol Ring
        Sideboard
        ...

    Cards before any title go to the main deck. Return (entries, problems,
    deck_name): each entry has its .section; deck_name comes from an
    Arena "Name ..." line (or None).
    """

    entries = []
    problems = []
    deck_name = None
    section = "main"

    for number, raw_line in enumerate(text.splitlines(), start=1):

        line = raw_line.strip()

        if not line:
            continue

        header = _section_header(line)
        if header is not None:
            section = SECTION_HEADERS[header]
            continue

        if line.startswith(("#", "//")):
            continue

        if section == "about":
            # "Name My deck": the deck's name; other About lines are ignored
            if line.lower().startswith("name "):
                deck_name = line[5:].strip() or deck_name
            continue

        if section is None:
            # Tokens and other skipped sections
            continue

        entry, problem = _parse_card_line(number, raw_line, line)

        if problem:
            problems.append(problem)
            continue

        if entry.section != "commander":
            entry.section = section

        entries.append(entry)

    return entries, problems, deck_name


def parse_card_list(text):
    """
    Parse a text list for the collection: section titles are ignored.
    Return (entries, problems): the valid lines as ListEntry objects and
    the syntax errors as ListProblem objects.
    """

    entries, problems, _ = parse_deck_list(text)

    for entry in entries:
        entry.section = "main"

    return entries, problems


def suggest_deck_format(entries):
    """
    "commander" when the list has a commander or about 100 cards, else None
    (the user chooses the 60-card format).
    """

    if any(entry.section == "commander" for entry in entries):
        return "commander"

    main = sum(entry.quantity for entry in entries if entry.section == "main")

    return "commander" if 98 <= main <= 101 else None


def _find_column(header, field):
    """
    Index of the column for this field. Names are tried in order of
    preference, so "Set Code" wins over a "Set" column with full set names.
    """

    columns = [column.strip().lower() for column in header]

    for name in CSV_COLUMNS[field]:
        if name in columns:
            return columns.index(name)

    return None


def csv_to_list_text(content):
    """
    Convert CSV content to the text list format, so it can be reviewed and
    checked like a pasted list. Return (text, problems).
    """

    rows = list(csv.reader(io.StringIO(content)))
    problems = []

    if not rows:
        return "", [ListProblem(1, "the CSV file is empty.")]

    header = rows[0]
    columns = {field: _find_column(header, field) for field in CSV_COLUMNS}

    if columns["name"] is None:
        return "", [ListProblem(1, "the CSV file needs a “Name” column.")]

    # {section title or "": [lines]}: rows of a "Section"/"Board" column are
    # written under their title so deck imports keep them
    sections = {}

    for line_number, row in enumerate(rows[1:], start=2):

        if not any(cell.strip() for cell in row):
            continue

        def cell(field):
            index = columns[field]
            return row[index].strip() if index is not None and index < len(row) else ""

        name = cell("name")
        quantity = cell("quantity") or "1"

        if not name:
            problems.append(ListProblem(line_number, "the card name is empty."))
            continue

        if not quantity.isdigit():
            problems.append(ListProblem(line_number, f"“{quantity}” is not a valid quantity."))
            continue

        line = f"{quantity} {name}"

        set_code = cell("set")
        # Only short codes ("CMM"), not full set names in a "Set" column
        if set_code and re.fullmatch(r"[A-Za-z0-9]{2,6}", set_code):
            line += f" ({set_code.upper()})"
            if cell("number"):
                line += f" {cell('number')}"

        if cell("foil").lower() in FOIL_VALUES:
            line += " *F*"

        section = cell("section")
        title = section if _section_header(section) else ""
        sections.setdefault(title, []).append(line)

    blocks = []
    for title, lines in sections.items():
        blocks.append("\n".join(([title] if title else []) + lines))

    return "\n\n".join(blocks), problems


def read_list_file(path):
    """
    Read a .txt or .csv file and return (text in list format, problems).
    """

    with open(path, "r", encoding="utf-8-sig", errors="replace") as file:
        content = file.read()

    if str(path).lower().endswith(".csv"):
        return csv_to_list_text(content)

    return content, []


# ==================================
# FINDING THE CARDS
# ==================================

def _identifier(entry):

    if entry.set_code and entry.collector_number:
        return {"set": entry.set_code, "collector_number": entry.collector_number}

    if entry.set_code:
        return {"name": entry.name, "set": entry.set_code}

    return {"name": entry.name}


def resolve_entries(entries):
    """
    Find every entry on Scryfall (network: call it from a background thread).
    Return (found, problems): found is a list of (ListEntry, Card) and
    problems lists the cards that don't exist, with a suggestion if possible.
    Raise ScryfallError on connection problems.
    """

    results = get_cards_by_identifiers([_identifier(entry) for entry in entries])

    found = []
    problems = []
    suggestions_left = MAX_SUGGESTIONS

    for entry, (_, card) in zip(entries, results):

        if card is not None:
            found.append((entry, card))
            continue

        message = f"“{entry.describe()}” not found."

        if suggestions_left > 0:
            suggestions_left -= 1

            try:
                suggestion = search_card_by_name(entry.name)
            except ScryfallError:
                suggestion = None

            if suggestion and suggestion.name.lower() != entry.name.lower():
                message += f" Did you mean “{suggestion.name}”?"
            elif suggestion and entry.set_code:
                message += " The card exists, but not with that edition."

        problems.append(ListProblem(entry.line, message))

    return found, problems


def add_found_cards(found, collection_id=None):
    """
    Add the resolved cards to a collection (None = the first one, "Main
    collection"). Return how many copies were added.
    """

    copies = 0

    for entry, card in found:
        card.quantity = entry.quantity
        card.foil = entry.foil
        card.collection_id = collection_id
        add_card(card)
        copies += entry.quantity

    return copies


# ==================================
# EXPORT
# ==================================

CSV_HEADER = [
    "Quantity", "Name", "Set", "Set Code", "Collector Number", "Rarity", "Foil",
    "Price EUR", "Price USD", "Value EUR", "Value USD", "Scryfall ID",
]


def _money(value):
    return f"{value:.2f}" if value is not None else ""


def card_line(card, quantity):
    """
    "3 Sol Ring (CMM) 410": quantity, name and exact edition, plus "*F*"
    for foil copies (the marker Moxfield / Arena lists use).
    """

    line = f"{quantity} {card.name}"

    if card.set_code:
        line += f" ({card.set_code.upper()})"
        if card.collector_number:
            line += f" {card.collector_number}"

    if card.foil:
        line += " *F*"

    return line


def deck_as_text(deck_name, deck_cards):
    """
    MTG Arena / Moxfield style list with sections. It can be imported again
    here or on deck sites, keeping exact editions.
    """

    blocks = [f"About\nName {deck_name}"]

    for section, title in DECK_TEXT_SECTIONS:
        lines = [
            card_line(entry.card, entry.quantity)
            for entry in sorted(deck_cards, key=lambda e: e.name.lower())
            if entry.section == section
        ]
        if lines:
            blocks.append("\n".join([title] + lines))

    return "\n\n".join(blocks) + "\n"


def export_deck(path, deck_name, deck_cards):
    """
    Save a deck as a text list (.txt). Return the number of card lines.
    """

    with open(path, "w", encoding="utf-8", newline="") as file:
        file.write(deck_as_text(deck_name, deck_cards))

    return len(deck_cards)


def export_shopping_list(path, missing, currency="EUR"):
    """
    Save the cards a deck still needs (list of deck_service.MissingCard).
    .csv -> spreadsheet with prices; anything else -> text list that deck
    and shopping sites can import ("2 Sol Ring (CMM) 410").
    Return the number of copies.
    """

    if str(path).lower().endswith(".csv"):
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow([
            "Quantity", "Name", "Set", "Set Code", "Collector Number",
            f"Price {currency}", f"Total {currency}",
        ])

        for item in missing:
            card = item.entry.card
            writer.writerow([
                item.missing, card.name, card.set_name or "",
                (card.set_code or "").upper(), card.collector_number or "",
                _money(card.price(currency)), _money(item.cost(currency)),
            ])

        content, encoding = output.getvalue(), "utf-8-sig"
    else:
        lines = [card_line(item.entry.card, item.missing) for item in missing]
        content, encoding = "\n".join(lines) + "\n", "utf-8"

    with open(path, "w", encoding=encoding, newline="") as file:
        file.write(content)

    return sum(item.missing for item in missing)


def collection_as_text(cards):
    """
    "3 Sol Ring (TMC) 59" per line: can be imported again keeping the edition.
    """

    return "\n".join(card_line(card, card.quantity) for card in cards) + "\n"


def collection_as_csv(cards, collection_names=None):
    """
    collection_names ({id: name}) adds a "Collection" column (used when
    exporting several collections at once).
    """

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow((["Collection"] if collection_names else []) + CSV_HEADER)

    for card in cards:
        prefix = [collection_names.get(card.collection_id, "")] if collection_names else []
        writer.writerow(prefix + [
            card.quantity,
            card.name,
            card.set_name or "",
            (card.set_code or "").upper(),
            card.collector_number or "",
            (card.rarity or "").capitalize(),
            "Foil" if card.foil else "",
            _money(card.price("EUR")),
            _money(card.price("USD")),
            _money(card.value("EUR")),
            _money(card.value("USD")),
            card.scryfall_id or "",
        ])

    return output.getvalue()


def export_collection(path, collection_ids=None, collection_names=None):
    """
    Save cards to path: every collection (None) or these collection ids.
    The format depends on the extension: .csv -> spreadsheet with prices
    (with a "Collection" column if collection_names is given), anything
    else -> text list. Return the number of printings exported.
    """

    cards = get_all_cards(collection_ids)

    if str(path).lower().endswith(".csv"):
        # utf-8-sig: Excel needs the BOM to show accents correctly
        content, encoding = collection_as_csv(cards, collection_names), "utf-8-sig"
    else:
        content, encoding = collection_as_text(cards), "utf-8"

    with open(path, "w", encoding=encoding, newline="") as file:
        file.write(content)

    return len(cards)
