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

# Foil/etched markers some sites add at the end of a line: "*F*", "*E*"
FINISH_MARKER = re.compile(r"\s+\*[A-Za-z]+\*\s*$")

# Lines that are only section titles in exported decks
SECTION_HEADERS = {
    "deck", "main", "mainboard", "maindeck", "sideboard", "commander",
    "companion", "maybeboard", "considering", "tokens",
}

# Accepted CSV column names (lowercase) for each field
CSV_COLUMNS = {
    "quantity": ("quantity", "qty", "count", "amount"),
    "name": ("name", "card", "card name"),
    "set": ("set code", "set_code", "edition code", "set"),
    "number": ("collector number", "collector_number", "number", "cn"),
}

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

def parse_card_list(text):
    """
    Parse a text list. Return (entries, problems): the valid lines as
    ListEntry objects and the syntax errors as ListProblem objects.
    """

    entries = []
    problems = []

    for number, raw_line in enumerate(text.splitlines(), start=1):

        line = raw_line.strip()

        if not line or line.startswith(("#", "//")):
            continue

        if line.rstrip(":").strip().lower() in SECTION_HEADERS:
            continue

        line = FINISH_MARKER.sub("", line)
        match = LINE_PATTERN.match(line)

        if not match:
            problems.append(ListProblem(
                number,
                f"“{raw_line.strip()}” is not valid. Use “quantity name”, e.g. “1 Sol Ring”.",
            ))
            continue

        quantity = int(match["quantity"])

        if not 1 <= quantity <= MAX_QUANTITY:
            problems.append(ListProblem(
                number, f"quantity {quantity} must be between 1 and {MAX_QUANTITY}."
            ))
            continue

        entries.append(ListEntry(
            line=number,
            quantity=quantity,
            name=match["name"].strip(),
            set_code=match["set"].lower() if match["set"] else None,
            collector_number=match["number"],
        ))

    return entries, problems


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

    lines = []

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

        lines.append(line)

    return "\n".join(lines), problems


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


def add_found_cards(found):
    """
    Add the resolved cards to the collection. Return how many copies were added.
    """

    copies = 0

    for entry, card in found:
        card.quantity = entry.quantity
        add_card(card)
        copies += entry.quantity

    return copies


# ==================================
# EXPORT
# ==================================

CSV_HEADER = [
    "Quantity", "Name", "Set", "Set Code", "Collector Number", "Rarity",
    "Price EUR", "Price USD", "Value EUR", "Value USD", "Scryfall ID",
]


def _money(value):
    return f"{value:.2f}" if value is not None else ""


def collection_as_text(cards):
    """
    "3 Sol Ring (TMC) 59" per line: can be imported again keeping the edition.
    """

    lines = []

    for card in cards:
        line = f"{card.quantity} {card.name}"
        if card.set_code:
            line += f" ({card.set_code.upper()})"
            if card.collector_number:
                line += f" {card.collector_number}"
        lines.append(line)

    return "\n".join(lines) + "\n"


def collection_as_csv(cards):

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(CSV_HEADER)

    for card in cards:
        writer.writerow([
            card.quantity,
            card.name,
            card.set_name or "",
            (card.set_code or "").upper(),
            card.collector_number or "",
            (card.rarity or "").capitalize(),
            _money(card.price("EUR")),
            _money(card.price("USD")),
            _money(card.value("EUR")),
            _money(card.value("USD")),
            card.scryfall_id or "",
        ])

    return output.getvalue()


def export_collection(path):
    """
    Save the whole collection to path. The format depends on the extension:
    .csv -> spreadsheet with prices, anything else -> text list.
    Return the number of printings exported.
    """

    cards = get_all_cards()

    if str(path).lower().endswith(".csv"):
        # utf-8-sig: Excel needs the BOM to show accents correctly
        content, encoding = collection_as_csv(cards), "utf-8-sig"
    else:
        content, encoding = collection_as_text(cards), "utf-8"

    with open(path, "w", encoding=encoding, newline="") as file:
        file.write(content)

    return len(cards)
