from api.scryfall_api import search_card_by_name, get_card_printings, ScryfallError
from database.database_manager import (
    add_card,
    get_all_cards,
    delete_cards,
    update_quantity,
    change_printing,
    set_foil,
)


def search_card(name):
    """
    Return the Card found, or None. Raise ScryfallError on connection problems.
    """
    return search_card_by_name(name)


def is_basic_land(card):
    """
    Plains, Island, Swamp, Mountain, Forest, Wastes and their Snow-Covered versions.
    """
    type_line = (card.type_line or "").split(" // ")[0]
    return "Basic" in type_line and "Land" in type_line


def get_printings(card):
    """
    Return the printings (editions) of the card as a list of Cards, newest
    first. Basic lands have ~1000 printings: only the newest page (up to
    175, a single request) is loaded for them.
    Raise ScryfallError on connection problems.
    """
    return get_card_printings(card, max_pages=1 if is_basic_land(card) else None)


def get_all_printings(card):
    """
    Every printing of the card, also for basic lands (several requests).
    """
    return get_card_printings(card)


def save_card(card):
    add_card(card)


def get_collection(collection_ids=None):
    """
    Cards of every collection (None) or of these collection ids.
    """
    return get_all_cards(collection_ids)


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
    Move a collection row to another edition (keeping foil / non-foil),
    merging quantities if that edition is already in the collection.
    Return the resulting row id.
    """
    return change_printing(card_id, new_card)


def set_card_foil(card_id, foil):
    """
    Mark a collection row as foil or non-foil (merging with the other row of
    the same edition and finish if it exists). Return the resulting row id.
    """
    return set_foil(card_id, foil)
