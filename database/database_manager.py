import sqlite3

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
        image_url TEXT
    )
    """)

    conn.commit()
    conn.close()


def add_card(card):
    """
    Save a card in the database
    """

    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO cards (name, set_name, type_line, mana_cost, rarity, image_url)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        card.name,
        card.set_name,
        card.type_line,
        card.mana_cost,
        card.rarity,
        card.image_url
    ))

    conn.commit()
    conn.close()


def get_all_cards():
    """
    Return all cards from the database
    """

    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM cards")

    cards = cursor.fetchall()

    conn.close()

    return cards