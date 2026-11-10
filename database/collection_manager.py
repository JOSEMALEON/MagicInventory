"""
Named collections (Main collection, Trade binder, Wishlist...).

Every row of `cards` belongs to one collection. A "wishlist" collection
holds cards you want, so they don't count as owned (decks, search page).
"""

from dataclasses import dataclass
from datetime import datetime

from database.database_manager import _connect

MAIN_COLLECTION_NAME = "Main collection"

KINDS = ("normal", "wishlist")


@dataclass
class Collection:
    id: int
    name: str
    kind: str = "normal"
    created_at: str = None

    # Filled by get_collections(): rows (printings) and copies
    printings: int = 0
    copies: int = 0

    @property
    def counts_as_owned(self):
        return self.kind != "wishlist"


def ensure_collections(conn):
    """
    Create the collections table and move old databases to it: every card
    without collection goes to "Main collection". Called by create_database().
    """

    conn.execute("""
    CREATE TABLE IF NOT EXISTS collections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'normal',
        created_at TEXT
    )
    """)

    row = conn.execute("SELECT id FROM collections ORDER BY id LIMIT 1").fetchone()

    if row is None:
        cursor = conn.execute(
            "INSERT INTO collections (name, kind, created_at) VALUES (?, 'normal', ?)",
            (MAIN_COLLECTION_NAME, _now()),
        )
        main_id = cursor.lastrowid
    else:
        main_id = row[0]

    conn.execute("UPDATE cards SET collection_id = ? WHERE collection_id IS NULL", (main_id,))

    # One row per printing and finish *inside each collection*
    conn.execute("DROP INDEX IF EXISTS idx_cards_printing_finish")
    conn.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_cards_collection_printing
    ON cards (collection_id, scryfall_id, foil)
    WHERE scryfall_id IS NOT NULL
    """)


def _now():
    return datetime.now().isoformat(timespec="seconds")


def get_collections():
    """All collections, in creation order, with their printings and copies."""

    with _connect() as conn:
        rows = conn.execute("""
        SELECT c.id, c.name, c.kind, c.created_at,
               COUNT(k.id), COALESCE(SUM(k.quantity), 0)
        FROM collections c
        LEFT JOIN cards k ON k.collection_id = c.id
        GROUP BY c.id
        ORDER BY c.id
        """).fetchall()

    return [Collection(*row[:4], printings=row[4], copies=row[5]) for row in rows]


def get_collection_by_id(collection_id):

    return next((c for c in get_collections() if c.id == collection_id), None)


def owned_collection_ids():
    """Ids of the collections whose cards count as owned (not wishlists)."""
    return [c.id for c in get_collections() if c.counts_as_owned]


def create_collection(name, kind="normal"):

    if kind not in KINDS:
        raise ValueError(f"Unknown collection kind: {kind}")

    with _connect() as conn, conn:
        cursor = conn.execute(
            "INSERT INTO collections (name, kind, created_at) VALUES (?, ?, ?)",
            (name.strip(), kind, _now()),
        )
        return cursor.lastrowid


def update_collection(collection_id, name=None, kind=None):

    with _connect() as conn, conn:
        if name is not None:
            conn.execute("UPDATE collections SET name = ? WHERE id = ?", (name.strip(), collection_id))
        if kind is not None:
            if kind not in KINDS:
                raise ValueError(f"Unknown collection kind: {kind}")
            conn.execute("UPDATE collections SET kind = ? WHERE id = ?", (kind, collection_id))


def _merge_row_into(conn, card_id, target_collection, quantity=None):
    """
    Move `quantity` copies (all if None) of a row to another collection.
    Copies of the same printing and finish already there are added up.
    """

    row = conn.execute(
        "SELECT scryfall_id, foil, quantity, name, set_name, collection_id FROM cards WHERE id = ?",
        (card_id,),
    ).fetchone()

    if row is None or row[5] == target_collection:
        return

    scryfall_id, foil, current, name, set_name, _ = row
    current = current or 0
    moving = current if quantity is None else max(0, min(quantity, current))

    if moving == 0:
        return

    if scryfall_id:
        target = conn.execute(
            "SELECT id FROM cards WHERE collection_id = ? AND scryfall_id = ? AND foil = ?",
            (target_collection, scryfall_id, foil),
        ).fetchone()
    else:
        target = conn.execute("""
        SELECT id FROM cards
        WHERE collection_id = ? AND scryfall_id IS NULL AND LOWER(name) = LOWER(?)
          AND set_name = ? AND foil = ?
        """, (target_collection, name, set_name, foil)).fetchone()

    if target:
        conn.execute("UPDATE cards SET quantity = quantity + ? WHERE id = ?", (moving, target[0]))
    elif moving == current:
        # The whole row moves
        conn.execute("UPDATE cards SET collection_id = ? WHERE id = ?", (target_collection, card_id))
        return
    else:
        # Part of the copies: a copy of the row in the other collection
        conn.execute("""
        INSERT INTO cards (
            name, set_name, type_line, mana_cost, rarity, image_url, quantity,
            scryfall_id, set_code, collector_number, price_eur, price_eur_foil,
            price_usd, price_usd_foil, prices_updated_at, foil, collection_id
        )
        SELECT name, set_name, type_line, mana_cost, rarity, image_url, ?,
               scryfall_id, set_code, collector_number, price_eur, price_eur_foil,
               price_usd, price_usd_foil, prices_updated_at, foil, ?
        FROM cards WHERE id = ?
        """, (moving, target_collection, card_id))

    if moving == current:
        conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))
    else:
        conn.execute("UPDATE cards SET quantity = ? WHERE id = ?", (current - moving, card_id))


def move_cards(card_ids, target_collection, quantity=None):
    """
    Move rows to another collection (quantity = copies of each row; None =
    all of them), merging with the same printing and finish there.
    """

    with _connect() as conn, conn:
        for card_id in card_ids:
            _merge_row_into(conn, card_id, target_collection, quantity)


def delete_collection(collection_id, move_to=None):
    """
    Delete a collection. Its cards move to `move_to` (merging) or are
    deleted when move_to is None. The last collection can't be deleted.
    """

    with _connect() as conn, conn:

        count = conn.execute("SELECT COUNT(*) FROM collections").fetchone()[0]
        if count <= 1:
            raise ValueError("You need at least one collection")

        card_ids = [row[0] for row in conn.execute(
            "SELECT id FROM cards WHERE collection_id = ?", (collection_id,)
        )]

        if move_to is not None:
            for card_id in card_ids:
                _merge_row_into(conn, card_id, move_to)
        else:
            conn.execute("DELETE FROM cards WHERE collection_id = ?", (collection_id,))

        conn.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
