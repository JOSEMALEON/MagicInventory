from datetime import datetime, timedelta

from api.scryfall_api import get_cards_by_identifiers, get_set_codes
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
    with_id = [card for card in cards if card.scryfall_id]

    results = get_cards_by_identifiers([{"id": card.scryfall_id} for card in with_id])
    fresh = [found for _, found in results if found]

    save_prices(fresh)

    return {
        "updated": len(fresh),
        "upgraded": upgraded,
        "missing": len(cards) - len(fresh),
    }


def get_price_changes(currency="EUR"):
    """
    Return {scryfall_id: (date, previous price of one copy)} using the last
    price recorded before today, with the same normal/foil rule as Card.price().
    """

    changes = {}

    for scryfall_id, entry in get_previous_prices().items():

        normal = entry[_HISTORY_INDEX[(currency, False)]]
        foil = entry[_HISTORY_INDEX[(currency, True)]]
        previous = normal if normal is not None else foil

        if previous is not None:
            changes[scryfall_id] = (entry[0], previous)

    return changes
