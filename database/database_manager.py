import sqlite3
from contextlib import closing

from models.card import Card
from src.config import DB_PATH

# Columns added after the first version of the table. Existing databases
# get them through a small migration in create_database().
PRINTING_COLUMNS = {
    "scryfall_id": "TEXT",
    "set_code": "TEXT",
    "collector_number": "TEXT",
}


def _connect():
    """
    Open the database. Use as:

        with _connect() as conn, conn:

    The first "with" closes the connection at the end; the second one
    commits (or rolls back on error) the transaction.
    """

    return closing(sqlite3.connect(DB_PATH))


def create_database():
    """
    Create the database and cards table, and upgrade old databases
    """

    with _connect() as conn, conn:

        conn.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            set_name TEXT,
            type_line TEXT,
            mana_cost TEXT,
            rarity TEXT,
            image_url TEXT,
            quantity INTEGER,
            scryfall_id TEXT,
            set_code TEXT,
            collector_number TEXT
        )
        """)

        # Migration: add the new columns to databases created before they existed
        existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(cards)")}

        for column, column_type in PRINTING_COLUMNS.items():
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE cards ADD COLUMN {column} {column_type}")

        # One row per printing. Old rows without scryfall_id are allowed.
        conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_cards_scryfall_id
        ON cards (scryfall_id)
        WHERE scryfall_id IS NOT NULL
        """)


def _find_existing_card(conn, card):
    """
    Return (id, quantity) of the row that represents this exact printing, or None.

    Rows saved before scryfall_id existed only have name + set_name. If one of
    them matches, it is upgraded with the printing data so it isn't duplicated.
    """

    if card.scryfall_id:

        row = conn.execute(
            "SELECT id, quantity FROM cards WHERE scryfall_id = ?",
            (card.scryfall_id,),
        ).fetchone()

        if row:
            return row

    legacy_row = conn.execute("""
    SELECT id, quantity FROM cards
    WHERE scryfall_id IS NULL
      AND LOWER(name) = LOWER(?)
      AND set_name = ?
    """, (card.name, card.set_name)).fetchone()

    if legacy_row and card.scryfall_id:

        conn.execute("""
        UPDATE cards
        SET scryfall_id = ?, set_code = ?, collector_number = ?, image_url = ?
        WHERE id = ?
        """, (
            card.scryfall_id,
            card.set_code,
            card.collector_number,
            card.image_url,
            legacy_row[0],
        ))

    return legacy_row


def add_card(card):
    """
    Add card.quantity copies of this printing to the collection.
    Same printing -> quantities merge. Different edition -> its own row.
    """

    with _connect() as conn, conn:

        existing = _find_existing_card(conn, card)

        if existing:

            card_id, current_quantity = existing

            conn.execute(
                "UPDATE cards SET quantity = ? WHERE id = ?",
                ((current_quantity or 0) + card.quantity, card_id),
            )

        else:

            conn.execute("""
            INSERT INTO cards (
                name, set_name, type_line, mana_cost, rarity, image_url, quantity,
                scryfall_id, set_code, collector_number
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                card.name,
                card.set_name,
                card.type_line,
                card.mana_cost,
                card.rarity,
                card.image_url,
                card.quantity,
                card.scryfall_id,
                card.set_code,
                card.collector_number,
            ))


def get_all_cards():
    """
    Return all cards from the database as Card objects, sorted by name
    """

    with _connect() as conn:

        rows = conn.execute("""
        SELECT name, set_name, type_line, mana_cost, rarity, image_url, quantity,
               scryfall_id, set_code, collector_number
        FROM cards
        ORDER BY name COLLATE NOCASE, set_name
        """).fetchall()

    return [
        Card(
            name=row[0],
            set_name=row[1],
            type_line=row[2],
            mana_cost=row[3],
            rarity=row[4],
            image_url=row[5],
            quantity=row[6],
            scryfall_id=row[7],
            set_code=row[8],
            collector_number=row[9],
        )
        for row in rows
    ]
