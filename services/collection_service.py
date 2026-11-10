"""
Named collections: the UI talks to this module (it talks to the database).
"""

from database import collection_manager
from database.collection_manager import KINDS, MAIN_COLLECTION_NAME, Collection

KIND_LABELS = {"normal": "Collection", "wishlist": "Wishlist (doesn't count as owned)"}


def get_collections():
    return collection_manager.get_collections()


def get_collection_by_id(collection_id):
    return collection_manager.get_collection_by_id(collection_id)


def owned_collection_ids():
    """Collections whose cards count as owned (wishlists don't)."""
    return collection_manager.owned_collection_ids()


def create_collection(name, kind="normal"):
    return collection_manager.create_collection(name, kind)


def rename_collection(collection_id, name):
    collection_manager.update_collection(collection_id, name=name)


def set_collection_kind(collection_id, kind):
    collection_manager.update_collection(collection_id, kind=kind)


def delete_collection(collection_id, move_to=None):
    collection_manager.delete_collection(collection_id, move_to)


def move_cards(card_ids, target_collection, quantity=None):
    collection_manager.move_cards(card_ids, target_collection, quantity)


def collection_label(collection):
    """ "Trade binder (12)" / "Wishlist ★ (3)" for selectors."""

    star = " ★" if collection.kind == "wishlist" else ""
    return f"{collection.name}{star}  ({collection.copies})"


__all__ = [
    "Collection", "KINDS", "KIND_LABELS", "MAIN_COLLECTION_NAME",
    "get_collections", "get_collection_by_id", "owned_collection_ids",
    "create_collection", "rename_collection", "set_collection_kind",
    "delete_collection", "move_cards", "collection_label",
]
