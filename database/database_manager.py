import sqlite3
from models.card import Card

DATABASE_NAME = "magic_inventory.db"


def create_database():
    """
    Create the database and cards table
    """

    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        set_name TEXT,
        type_line TEXT,
        mana_cost TEXT,
        rarity TEXT,
        image_url TEXT,
        quantity INTEGER
    )
    """)

    conn.commit()
    conn.close()


def add_card(card):

    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO cards (name, set_name, type_line, mana_cost, rarity, image_url, quantity)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        card.name,
        card.set_name,
        card.type_line,
        card.mana_cost,
        card.rarity,
        card.image_url,
        card.quantity
    ))

    conn.commit()
    conn.close()


def get_all_cards():
    """
    Return all cards from the database as Card objects
    """

    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT name, set_name, type_line, mana_cost, rarity, image_url, quantity
    FROM cards
    """)

    rows = cursor.fetchall()

    conn.close()

    cards = []

    for row in rows:

        card = Card(
            name=row[0],
            set_name=row[1],
            type_line=row[2],
            mana_cost=row[3],
            rarity=row[4],
            image_url=row[5],
            quantity=row[6]
        )

        cards.append(card)

    return cards