from api.scryfall_api import search_card_by_name, get_card_printings, ScryfallError
from database.database_manager import (
    add_card,
    get_all_cards,
    delete_cards,
    update_quantity,
    change_printing,
)


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


def remove_cards(card_ids):
    """
    Delete these printings (database row ids) from the collection.
    """
    delete_cards(card_ids)


def set_quantity(card_id, quantity):
    """
    Set the number of copies of one printing (must be at least 1).
    """
    update_quantity(card_id, quantity)


def change_card_printing(card_id, new_card):
    """
    Move a collection row to another edition, merging quantities if that
    edition is already in the collection. Return the resulting row id.
    """
    return change_printing(card_id, new_card)
