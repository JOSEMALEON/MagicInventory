from datetime import datetime, timedelta

from api.scryfall_api import get_cards_by_identifiers, get_set_codes
from database import deck_manager
from database.database_manager import (
    get_all_cards,
    save_prices,
    change_printing,
    get_previous_prices,
)

# Scryfall updates prices once a day; refresh automatically after this long
PRICES_MAX_AGE = timedelta(hours=20)

CURRENCY_SYMBOLS = {"EUR": "€", "USD": "$"}

# Position of each price inside the tuples returned by get_previous_prices()
_HISTORY_INDEX = {("EUR", False): 1, ("EUR", True): 2, ("USD", False): 3, ("USD", True): 4}


def format_money(amount, currency="EUR"):
    """
    1234.5 -> "€1,234.50". None -> "—".
    """

    if amount is None:
        return "—"

    return f"{CURRENCY_SYMBOLS.get(currency, '')}{amount:,.2f}"


def prices_need_update(cards):
    """
    True if any card with a Scryfall id has no prices yet or they are old.
    Rows saved before scryfall_id existed also count: refreshing upgrades them.
    """

    limit = datetime.now() - PRICES_MAX_AGE

    for card in cards:

        if not card.scryfall_id:
            return True

        if not card.prices_updated_at:
            return True

        try:
            if datetime.fromisoformat(card.prices_updated_at) < limit:
                return True
        except ValueError:
            return True

    return False


def last_price_update(cards):
    """
    Oldest update date among the cards that have prices, or None.
    """

    dates = []

    for card in cards:
        try:
            dates.append(datetime.fromisoformat(card.prices_updated_at))
        except (TypeError, ValueError):
            pass

    return min(dates) if dates else None


def _upgrade_legacy_cards(cards):
    """
    Rows saved before scryfall_id existed only have name + set name.
    Find their printing on Scryfall and fill in the missing data (this also
    stores their prices). Return how many rows were upgraded.
    """

    legacy = [card for card in cards if not card.scryfall_id and card.name and card.set_name]

    if not legacy:
        return 0

    set_codes = get_set_codes()

    lookups = []
    for card in legacy:
        code = set_codes.get(card.set_name)
        if code:
            lookups.append((card, {"name": card.name, "set": code}))

    results = get_cards_by_identifiers([identifier for _, identifier in lookups])

    upgraded = 0
    for (card, _), (_, found) in zip(lookups, results):
        if found:
            change_printing(card.id, found)
            upgraded += 1

    return upgraded


def refresh_prices():
    """
    Download current prices for the whole collection and save them.
    Runs network requests: call it from a background thread.

    Return a dict with "updated" (rows with fresh prices), "upgraded"
    (old rows completed with their printing data) and "missing" (rows
    that could not be found on Scryfall).
    Raise ScryfallError on connection problems.
    """

    upgraded = _upgrade_legacy_cards(get_all_cards())

    cards = get_all_cards()
    collection_ids = {card.scryfall_id for card in cards if card.scryfall_id}

    # Deck cards too (one request for up to 75 printings, shared with the collection)
    deck_ids = set(deck_manager.get_deck_scryfall_ids())
    all_ids = sorted(collection_ids | deck_ids)

    results = get_cards_by_identifiers([{"id": scryfall_id} for scryfall_id in all_ids])
    fresh = [found for _, found in results if found]

    save_prices([card for card in fresh if card.scryfall_id in collection_ids])
    deck_manager.update_deck_prices([card for card in fresh if card.scryfall_id in deck_ids])

    updated_collection = sum(card.scryfall_id in collection_ids for card in fresh)

    return {
        "updated": updated_collection,
        "upgraded": upgraded,
        "missing": len(cards) - updated_collection,
        "deck_printings": sum(card.scryfall_id in deck_ids for card in fresh),
    }


def deck_prices_need_update():
    """
    True if some deck card has no price date or it is older than PRICES_MAX_AGE.
    """

    oldest = deck_manager.oldest_deck_price_update()

    if oldest is None:
        return False

    try:
        return datetime.fromisoformat(oldest) < datetime.now() - PRICES_MAX_AGE
    except ValueError:
        return True


def get_price_changes(currency="EUR"):
    """
    Return {(scryfall_id, is_foil): (date, previous price of one copy)} using
    the last price recorded before today, for both finishes, with the same
    rule as Card.price() (the other finish's price if one is missing).
    Look it up with previous_price(changes, card).
    """

    changes = {}

    for scryfall_id, entry in get_previous_prices().items():

        normal = entry[_HISTORY_INDEX[(currency, False)]]
        foil = entry[_HISTORY_INDEX[(currency, True)]]

        for is_foil, first, second in ((False, normal, foil), (True, foil, normal)):
            previous = first if first is not None else second
            if previous is not None:
                changes[(scryfall_id, is_foil)] = (entry[0], previous)

    return changes


def previous_price(changes, card):
    """(date, previous price) of this card's printing and finish, or None."""
    return changes.get((card.scryfall_id, card.foil))
