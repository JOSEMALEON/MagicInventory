import sqlite3
from contextlib import closing
from datetime import date, datetime

from models.card import Card
from src.config import DB_PATH

# Columns added after the first version of the table. Existing databases
# get them through a small migration in create_database().
PRINTING_COLUMNS = {
    "scryfall_id": "TEXT",
    "set_code": "TEXT",
    "collector_number": "TEXT",
    # Latest known prices of one copy (NULL = no price)
    "price_eur": "REAL",
    "price_eur_foil": "REAL",
    "price_usd": "REAL",
    "price_usd_foil": "REAL",
    # ISO date-time of the last price update
    "prices_updated_at": "TEXT",
}

# Columns read into Card objects, in this order
CARD_COLUMNS = (
    "name, set_name, type_line, mana_cost, rarity, image_url, quantity, "
    "scryfall_id, set_code, collector_number, id, "
    "price_eur, price_eur_foil, price_usd, price_usd_foil, prices_updated_at"
)


def _card_from_row(row):

    return Card(
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
        id=row[10],
        price_eur=row[11],
        price_eur_foil=row[12],
        price_usd=row[13],
        price_usd_foil=row[14],
        prices_updated_at=row[15],
    )


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

        # One row per printing and day: lets the app show how prices change
        conn.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            scryfall_id TEXT NOT NULL,
            date TEXT NOT NULL,
            price_eur REAL,
            price_eur_foil REAL,
            price_usd REAL,
            price_usd_foil REAL,
            PRIMARY KEY (scryfall_id, date)
        )
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

        # The card comes straight from Scryfall, so its prices are current
        _store_prices(conn, [card])


def get_all_cards():
    """
    Return all cards from the database as Card objects, sorted by name.
    Each Card has its row id in card.id (higher id = added more recently).
    """

    with _connect() as conn:

        rows = conn.execute(f"""
        SELECT {CARD_COLUMNS}
        FROM cards
        ORDER BY name COLLATE NOCASE, set_name
        """).fetchall()

    return [_card_from_row(row) for row in rows]


# ==================================
# PRICES
# ==================================

def _store_prices(conn, cards):
    """
    Save the prices of these Scryfall cards in their collection rows
    (matched by scryfall_id) and in today's price history.
    """

    now = datetime.now().isoformat(timespec="seconds")
    today = date.today().isoformat()

    for card in cards:

        if not card.scryfall_id:
            continue

        prices = (card.price_eur, card.price_eur_foil, card.price_usd, card.price_usd_foil)

        conn.execute("""
        UPDATE cards
        SET price_eur = ?, price_eur_foil = ?, price_usd = ?, price_usd_foil = ?,
            prices_updated_at = ?
        WHERE scryfall_id = ?
        """, (*prices, now, card.scryfall_id))

        # Same day again -> replace (Scryfall updates prices once a day)
        conn.execute("""
        INSERT OR REPLACE INTO price_history (
            scryfall_id, date, price_eur, price_eur_foil, price_usd, price_usd_foil
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (card.scryfall_id, today, *prices))


def save_prices(cards):
    """
    Store fresh prices for cards fetched from Scryfall.
    """

    with _connect() as conn, conn:
        _store_prices(conn, cards)


def get_previous_prices():
    """
    For every printing, return its most recent price history entry from
    BEFORE today: {scryfall_id: (date, price_eur, price_eur_foil,
    price_usd, price_usd_foil)}. Used to show how prices have changed.
    """

    today = date.today().isoformat()

    with _connect() as conn:

        rows = conn.execute("""
        SELECT h.scryfall_id, h.date, h.price_eur, h.price_eur_foil,
               h.price_usd, h.price_usd_foil
        FROM price_history h
        JOIN (
            SELECT scryfall_id, MAX(date) AS date
            FROM price_history
            WHERE date < ?
            GROUP BY scryfall_id
        ) latest
          ON latest.scryfall_id = h.scryfall_id AND latest.date = h.date
        """, (today,)).fetchall()

    return {row[0]: row[1:] for row in rows}


def delete_cards(card_ids):
    """
    Remove these rows (printings) from the collection.
    """

    with _connect() as conn, conn:

        conn.executemany(
            "DELETE FROM cards WHERE id = ?",
            [(card_id,) for card_id in card_ids],
        )


def update_quantity(card_id, quantity):
    """
    Set how many copies of this printing the collection has.
    """

    if quantity < 1:
        raise ValueError("Quantity must be at least 1 (delete the card instead)")

    with _connect() as conn, conn:

        conn.execute(
            "UPDATE cards SET quantity = ? WHERE id = ?",
            (quantity, card_id),
        )


def change_printing(card_id, new_card):
    """
    Move the row card_id to another printing (edition) of the same card.

    If the collection already has a row for that printing, the quantities
    are merged into it and card_id is deleted. Return the id of the row
    that holds the cards afterwards.
    """

    with _connect() as conn, conn:

        row = conn.execute(
            "SELECT quantity FROM cards WHERE id = ?", (card_id,)
        ).fetchone()

        if row is None:
            raise ValueError(f"Card {card_id} is not in the collection")

        quantity = row[0] or 0

        target = None
        if new_card.scryfall_id:
            target = conn.execute(
                "SELECT id, quantity FROM cards WHERE scryfall_id = ? AND id != ?",
                (new_card.scryfall_id, card_id),
            ).fetchone()

        if target:
            target_id, target_quantity = target

            conn.execute(
                "UPDATE cards SET quantity = ? WHERE id = ?",
                ((target_quantity or 0) + quantity, target_id),
            )
            conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))

            _store_prices(conn, [new_card])

            return target_id

        conn.execute("""
        UPDATE cards
        SET name = ?, set_name = ?, type_line = ?, mana_cost = ?, rarity = ?,
            image_url = ?, scryfall_id = ?, set_code = ?, collector_number = ?
        WHERE id = ?
        """, (
            new_card.name,
            new_card.set_name,
            new_card.type_line,
            new_card.mana_cost,
            new_card.rarity,
            new_card.image_url,
            new_card.scryfall_id,
            new_card.set_code,
            new_card.collector_number,
            card_id,
        ))

        _store_prices(conn, [new_card])

        return card_id
