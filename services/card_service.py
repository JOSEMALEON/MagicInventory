from api.scryfall_api import search_card_by_name, get_card_printings, ScryfallError
from database.database_manager import add_card, get_all_cards


def search_card(name):
    """
    Return the Card found, or None. Raise ScryfallError on connection problems.
    """
    return search_card_by_name(name)


def get_printings(card):
    """
    Return every printing (edition) of the card as a list of Cards.
    Raise ScryfallError on connection problems.
    """
    return get_card_printings(card)


def save_card(card):
    add_card(card)


def get_collection():
    return get_all_cards()
