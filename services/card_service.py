from api.scryfall_api import search_card_by_name
from database.database_manager import add_card, get_all_cards


def search_card(name):
    return search_card_by_name(name)


def save_card(card):
    add_card(card)


def get_collection():
    return get_all_cards()