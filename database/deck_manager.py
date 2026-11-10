"""
SQLite storage of decks and their cards.

Each deck_cards row is one printing in one section of a deck. It keeps the
card data needed to show and validate the deck (type, mana value, colors,
legalities...) so a deck can be displayed without asking Scryfall again.
"""

import json
from datetime import datetime

from database.database_manager import _connect
from models.card import Card
from models.deck import SECTIONS, Deck, DeckCard

# Columns copied from a Card into deck_cards (and read back), in this order
DECK_CARD_FIELDS = (
    "name", "set_name", "type_line", "mana_cost", "rarity", "image_url",
    "scryfall_id", "set_code", "collector_number",
    "price_eur", "price_eur_foil", "price_usd", "price_usd_foil",
    "cmc", "colors", "color_identity", "legalities", "oracle_text",
)

# Stored as JSON text
JSON_FIELDS = {"colors", "color_identity", "legalities"}


def create_deck_tables(conn):
    """
    Create the deck tables if they don't exist (called from create_database).
    """

    conn.execute("""
    CREATE TABLE IF NOT EXISTS decks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        format TEXT NOT NULL,
        notes TEXT DEFAULT '',
        created_at TEXT,
        updated_at TEXT
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS deck_cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
        section TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        name TEXT,
        set_name TEXT,
        type_line TEXT,
        mana_cost TEXT,
        rarity TEXT,
        image_url TEXT,
        scryfall_id TEXT NOT NULL,
        set_code TEXT,
        collector_number TEXT,
        price_eur REAL,
        price_eur_foil REAL,
        price_usd REAL,
        price_usd_foil REAL,
        cmc REAL,
        colors TEXT,
        color_identity TEXT,
        legalities TEXT,
        oracle_text TEXT
    )
    """)

    # One row per printing and section: adding it again adds copies
    conn.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_deck_cards_unique
    ON deck_cards (deck_id, scryfall_id, section)
    """)


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _touch(conn, deck_id):
    """Remember that the deck changed (used to sort the deck list)."""
    conn.execute("UPDATE decks SET updated_at = ? WHERE id = ?", (_now(), deck_id))


def _card_values(card):
    """Values of DECK_CARD_FIELDS for this card, ready for SQL."""

    values = []
    for name in DECK_CARD_FIELDS:
        value = getattr(card, name)
        values.append(json.dumps(value) if name in JSON_FIELDS else value)
    return values


# ==================================
# DECKS
# ==================================

def create_deck(name, deck_format):
    """Create an empty deck and return its id."""

    with _connect() as conn, conn:
        cursor = conn.execute(
            "INSERT INTO decks (name, format, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (name, deck_format, _now(), _now()),
        )
        return cursor.lastrowid


def update_deck(deck_id, name=None, deck_format=None, notes=None):
    """Change the name, format and/or notes of a deck."""

    changes = {"name": name, "format": deck_format, "notes": notes}
    changes = {column: value for column, value in changes.items() if value is not None}

    if not changes:
        return

    assignments = ", ".join(f"{column} = ?" for column in changes)

    with _connect() as conn, conn:
        conn.execute(
            f"UPDATE decks SET {assignments} WHERE id = ?",
            (*changes.values(), deck_id),
        )
        _touch(conn, deck_id)


def delete_deck(deck_id):
    """Delete a deck and (by cascade) all its cards."""

    with _connect() as conn, conn:
        conn.execute("DELETE FROM decks WHERE id = ?", (deck_id,))


def get_decks():
    """
    All decks, most recently changed first, with card_count = copies in
    commander + main (the cards that count for the deck size).
    """

    with _connect() as conn:
        rows = conn.execute("""
        SELECT d.id, d.name, d.format, d.notes, d.created_at, d.updated_at,
               COALESCE(SUM(CASE WHEN c.section IN ('commander', 'main')
                                 THEN c.quantity END), 0)
        FROM decks d
        LEFT JOIN deck_cards c ON c.deck_id = d.id
        GROUP BY d.id
        ORDER BY d.updated_at DESC, d.id DESC
        """).fetchall()

    return [Deck(*row[:6], card_count=row[6]) for row in rows]


def get_deck(deck_id):
    """One deck (without cards), or None."""

    with _connect() as conn:
        row = conn.execute(
            "SELECT id, name, format, notes, created_at, updated_at FROM decks WHERE id = ?",
            (deck_id,),
        ).fetchone()

    return Deck(*row) if row else None


# ==================================
# DECK CARDS
# ==================================

def get_deck_cards(deck_id):
    """All the card lines of a deck as DeckCard objects."""

    columns = ", ".join(DECK_CARD_FIELDS)

    with _connect() as conn:
        rows = conn.execute(f"""
        SELECT id, section, quantity, {columns}
        FROM deck_cards
        WHERE deck_id = ?
        ORDER BY name COLLATE NOCASE
        """, (deck_id,)).fetchall()

    deck_cards = []

    for row in rows:
        row_id, section, quantity, *values = row
        data = dict(zip(DECK_CARD_FIELDS, values))

        for name in JSON_FIELDS:
            data[name] = json.loads(data[name]) if data[name] else None

        card = Card(quantity=quantity, **data)
        deck_cards.append(DeckCard(id=row_id, section=section, card=card))

    return deck_cards


def add_card_to_deck(deck_id, card, quantity, section):
    """
    Add copies of a printing to a section of the deck. If it is already
    there, the copies are added up. Return the deck_cards row id.
    """

    if section not in SECTIONS:
        raise ValueError(f"Unknown section: {section}")

    with _connect() as conn, conn:

        existing = conn.execute(
            "SELECT id FROM deck_cards WHERE deck_id = ? AND scryfall_id = ? AND section = ?",
            (deck_id, card.scryfall_id, section),
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE deck_cards SET quantity = quantity + ? WHERE id = ?",
                (quantity, existing[0]),
            )
            row_id = existing[0]
        else:
            columns = ", ".join(DECK_CARD_FIELDS)
            marks = ", ".join("?" for _ in DECK_CARD_FIELDS)
            cursor = conn.execute(
                f"INSERT INTO deck_cards (deck_id, section, quantity, {columns}) "
                f"VALUES (?, ?, ?, {marks})",
                (deck_id, section, quantity, *_card_values(card)),
            )
            row_id = cursor.lastrowid

        _touch(conn, deck_id)

    return row_id


def _deck_of(conn, deck_card_id):

    row = conn.execute("SELECT deck_id FROM deck_cards WHERE id = ?", (deck_card_id,)).fetchone()

    if row is None:
        raise ValueError(f"Deck card {deck_card_id} does not exist")

    return row[0]


def set_deck_card_quantity(deck_card_id, quantity):
    """Set the copies of one card line (at least 1; remove it instead)."""

    if quantity < 1:
        raise ValueError("Quantity must be at least 1 (remove the card instead)")

    with _connect() as conn, conn:
        deck_id = _deck_of(conn, deck_card_id)
        conn.execute("UPDATE deck_cards SET quantity = ? WHERE id = ?", (quantity, deck_card_id))
        _touch(conn, deck_id)


def remove_deck_cards(deck_card_ids):
    """Remove card lines from their deck."""

    with _connect() as conn, conn:
        for deck_card_id in deck_card_ids:
            row = conn.execute(
                "SELECT deck_id FROM deck_cards WHERE id = ?", (deck_card_id,)
            ).fetchone()
            if row:
                conn.execute("DELETE FROM deck_cards WHERE id = ?", (deck_card_id,))
                _touch(conn, row[0])


def _merge_into(conn, deck_card_id, deck_id, scryfall_id, section):
    """
    If another line of the deck already has this printing in this section,
    add our copies to it, delete our line and return the other line's id.
    Return None when there is nothing to merge with.
    """

    other = conn.execute(
        "SELECT id FROM deck_cards WHERE deck_id = ? AND scryfall_id = ? AND section = ? AND id != ?",
        (deck_id, scryfall_id, section, deck_card_id),
    ).fetchone()

    if not other:
        return None

    conn.execute("""
    UPDATE deck_cards
    SET quantity = quantity + (SELECT quantity FROM deck_cards WHERE id = ?)
    WHERE id = ?
    """, (deck_card_id, other[0]))
    conn.execute("DELETE FROM deck_cards WHERE id = ?", (deck_card_id,))

    return other[0]


def move_deck_card(deck_card_id, section):
    """
    Move a card line to another section (merging with the same printing if
    it is already there). Return the id of the line that holds the copies.
    """

    if section not in SECTIONS:
        raise ValueError(f"Unknown section: {section}")

    with _connect() as conn, conn:
        deck_id = _deck_of(conn, deck_card_id)
        scryfall_id = conn.execute(
            "SELECT scryfall_id FROM deck_cards WHERE id = ?", (deck_card_id,)
        ).fetchone()[0]

        merged = _merge_into(conn, deck_card_id, deck_id, scryfall_id, section)

        if merged is None:
            conn.execute("UPDATE deck_cards SET section = ? WHERE id = ?", (section, deck_card_id))

        _touch(conn, deck_id)

        return merged or deck_card_id


def change_deck_card_printing(deck_card_id, new_card):
    """
    Use another printing (edition) for a card line, merging if the deck
    already has that printing in the same section. Return the line's id.
    """

    with _connect() as conn, conn:
        deck_id = _deck_of(conn, deck_card_id)
        section = conn.execute(
            "SELECT section FROM deck_cards WHERE id = ?", (deck_card_id,)
        ).fetchone()[0]

        merged = _merge_into(conn, deck_card_id, deck_id, new_card.scryfall_id, section)

        if merged is None:
            assignments = ", ".join(f"{name} = ?" for name in DECK_CARD_FIELDS)
            conn.execute(
                f"UPDATE deck_cards SET {assignments} WHERE id = ?",
                (*_card_values(new_card), deck_card_id),
            )

        _touch(conn, deck_id)

        return merged or deck_card_id
