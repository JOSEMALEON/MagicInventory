import threading
import time

import requests

from models.card import Card
from src.config import REQUEST_TIMEOUT, HTTP_HEADERS

# Scryfall's rate limits: about 10 requests/second in general, but only
# 2/second for the card search endpoints. Several background threads can ask
# at the same time, so every request waits its turn here.
MIN_SECONDS_BETWEEN_REQUESTS = 0.1
MIN_SECONDS_BETWEEN_SEARCHES = 0.5
SEARCH_ENDPOINTS = ("/cards/search", "/cards/named", "/cards/collection", "/cards/random")

_rate_lock = threading.Lock()
_last_request_at = {"search": 0.0, "other": 0.0}

# Answer to "Too Many Requests": wait and try once more
TOO_MANY_REQUESTS = 429
DEFAULT_RETRY_SECONDS = 2.0

SCRYFALL_NAMED_URL = "https://api.scryfall.com/cards/named"
SCRYFALL_SEARCH_URL = "https://api.scryfall.com/cards/search"
SCRYFALL_COLLECTION_URL = "https://api.scryfall.com/cards/collection"
SCRYFALL_SETS_URL = "https://api.scryfall.com/sets"
SCRYFALL_SYMBOLOGY_URL = "https://api.scryfall.com/symbology"

# /cards/collection accepts at most 75 identifiers per request
COLLECTION_BATCH_SIZE = 75


class ScryfallError(Exception):
    """
    Raised when Scryfall can't be reached or answers with an unexpected error
    (as opposed to simply not finding the card).
    """


def _extract_image_url(data, size="normal"):
    """
    Normal cards have "image_uris" at the top level. Double-faced cards
    (transform, MDFC...) only have them inside "card_faces", so use the front face.
    """

    if "image_uris" in data:
        return data["image_uris"].get(size)

    faces = data.get("card_faces") or []

    if faces and "image_uris" in faces[0]:
        return faces[0]["image_uris"].get(size)

    return None


def _extract_mana_cost(data):
    """
    Double-faced cards have no top-level mana cost: join the faces' costs.
    """

    if data.get("mana_cost") is not None:
        return data["mana_cost"]

    faces = data.get("card_faces") or []
    costs = [face.get("mana_cost", "") for face in faces]

    return " // ".join(cost for cost in costs if cost)


def _parse_price(value):
    """
    Scryfall sends prices as strings ("4.66") or null.
    """

    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _extract_colors(data):
    """
    Double-faced cards keep their colors in each face: join them.
    """

    if data.get("colors") is not None:
        return data["colors"]

    colors = []
    for face in data.get("card_faces") or []:
        for color in face.get("colors") or []:
            if color not in colors:
                colors.append(color)

    return colors


def _extract_oracle_text(data):
    """
    Rules text. Double-faced cards: "front text\n//\nback text".
    """

    if data.get("oracle_text") is not None:
        return data["oracle_text"]

    faces = data.get("card_faces") or []
    return "\n//\n".join(face.get("oracle_text", "") for face in faces)


def _card_from_json(data):

    prices = data.get("prices") or {}

    return Card(
        cmc=data.get("cmc"),
        colors=_extract_colors(data),
        color_identity=data.get("color_identity") or [],
        legalities=data.get("legalities") or {},
        oracle_text=_extract_oracle_text(data),
        finishes=data.get("finishes") or [],
        price_eur=_parse_price(prices.get("eur")),
        price_eur_foil=_parse_price(prices.get("eur_foil")),
        price_usd=_parse_price(prices.get("usd")),
        price_usd_foil=_parse_price(prices.get("usd_foil")),
        name=data.get("name"),
        set_name=data.get("set_name"),
        type_line=data.get("type_line"),
        mana_cost=_extract_mana_cost(data),
        rarity=data.get("rarity"),
        image_url=_extract_image_url(data),
        scryfall_id=data.get("id"),
        set_code=data.get("set"),
        collector_number=data.get("collector_number"),
        prints_search_uri=data.get("prints_search_uri"),
    )


def _wait_for_turn(url):
    """
    Keep the minimum time between two requests of the same kind (search
    endpoints or the rest), whatever thread they come from.
    """

    is_search = any(endpoint in url for endpoint in SEARCH_ENDPOINTS)
    kind = "search" if is_search else "other"
    interval = MIN_SECONDS_BETWEEN_SEARCHES if is_search else MIN_SECONDS_BETWEEN_REQUESTS

    with _rate_lock:
        wait = _last_request_at[kind] + interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request_at[kind] = time.monotonic()


def _request(method, url, **kwargs):
    """
    Send a request to the Scryfall API respecting its rate limit.
    On 429 (too many requests) wait as Scryfall says and retry once.
    Raise ScryfallError if Scryfall can't be reached.
    """

    for attempt in range(2):

        _wait_for_turn(url)

        try:
            response = requests.request(
                method,
                url,
                headers=HTTP_HEADERS,
                timeout=REQUEST_TIMEOUT,
                **kwargs,
            )
        except requests.RequestException as error:
            raise ScryfallError(f"Could not connect to Scryfall: {error}") from error

        if response.status_code != TOO_MANY_REQUESTS or attempt == 1:
            return response

        try:
            retry_after = float(response.headers.get("Retry-After", DEFAULT_RETRY_SECONDS))
        except ValueError:
            retry_after = DEFAULT_RETRY_SECONDS

        time.sleep(retry_after)

    return response


def _get_json(url, params=None):
    """
    GET a Scryfall URL and return the decoded JSON, or None on 404.
    Raise ScryfallError if the request fails.
    """

    response = _request("GET", url, params=params)

    if response.status_code == 404:
        return None

    if response.status_code != 200:
        raise ScryfallError(f"Scryfall answered with status {response.status_code}")

    try:
        return response.json()
    except ValueError as error:
        raise ScryfallError("Scryfall returned an invalid response") from error


def _post_json(url, payload):
    """
    POST JSON to Scryfall and return the decoded answer.
    Raise ScryfallError if the request fails.
    """

    response = _request("POST", url, json=payload)

    if response.status_code != 200:
        raise ScryfallError(f"Scryfall answered with status {response.status_code}")

    try:
        return response.json()
    except ValueError as error:
        raise ScryfallError("Scryfall returned an invalid response") from error


def get_cards_by_identifiers(identifiers):
    """
    Fetch many cards at once with /cards/collection. Each identifier is a
    dict like {"id": "<scryfall id>"} or {"name": "Sol Ring", "set": "cmm"}.

    Return a list of (identifier, Card or None) in the same order.
    Raise ScryfallError if a request fails.
    """

    results = []

    for start in range(0, len(identifiers), COLLECTION_BATCH_SIZE):

        batch = identifiers[start:start + COLLECTION_BATCH_SIZE]
        data = _post_json(SCRYFALL_COLLECTION_URL, {"identifiers": batch})

        # The answer only lists the cards found, in order; "not_found" lists the rest
        found = iter(data.get("data", []))
        not_found = data.get("not_found", [])

        for identifier in batch:
            if identifier in not_found:
                results.append((identifier, None))
            else:
                results.append((identifier, _card_from_json(next(found))))

    return results


def search_card_names(query):
    """
    Names of every card matching a Scryfall search (one per card, not per
    printing), e.g. "is:gamechanger". Empty list if nothing matches.
    Raise ScryfallError if a request fails.
    """

    names = []
    url, params = SCRYFALL_SEARCH_URL, {"q": query, "unique": "cards"}

    while url:
        data = _get_json(url, params=params)
        if data is None:
            break

        names.extend(item["name"] for item in data.get("data", []) if item.get("name"))

        url = data.get("next_page") if data.get("has_more") else None
        params = None

    return names


def get_symbology():
    """
    Return {"{W}": "https://svgs.scryfall.io/card-symbols/W.svg", ...} with
    every symbol Scryfall knows (mana, tap, energy...).
    """

    data = _get_json(SCRYFALL_SYMBOLOGY_URL) or {}

    return {
        item["symbol"]: item["svg_uri"]
        for item in data.get("data", [])
        if item.get("symbol") and item.get("svg_uri")
    }


def get_set_codes():
    """
    Return a dict {set name: set code} with every set Scryfall knows.
    """

    data = _get_json(SCRYFALL_SETS_URL) or {}

    return {item["name"]: item["code"] for item in data.get("data", [])}


def search_card_by_name(card_name):
    """
    Return a Card for the best match of card_name, or None if Scryfall
    doesn't find it. Raise ScryfallError if the request itself fails.
    """

    # 404 = no card found, or the name was too ambiguous
    data = _get_json(SCRYFALL_NAMED_URL, params={"fuzzy": card_name})

    if data is None:
        return None

    return _card_from_json(data)


def get_card_printings(card, max_pages=None):
    """
    Return a list of Cards, one per printing (edition) of the given card,
    newest first. Raise ScryfallError if a request fails.

    Each page has up to 175 printings. max_pages=1 gets only the newest ones
    with a single request (basic lands have ~1000 printings = 6+ pages).
    """

    if card.prints_search_uri:
        url, params = card.prints_search_uri, None

    elif card.name:
        # Cards loaded from the database don't keep prints_search_uri:
        # search every printing by exact name instead (same options Scryfall uses)
        url = SCRYFALL_SEARCH_URL
        params = {
            "q": f'!"{card.name}"',
            "unique": "prints",
            "order": "released",
            "include_extras": "true",
            "include_variations": "true",
        }

    else:
        return [card]

    printings = []
    pages = 0

    while url and (max_pages is None or pages < max_pages):
        pages += 1

        # 404 = the search found nothing
        data = _get_json(url, params=params)

        # "next_page" already contains every parameter
        params = None

        if data is None:
            break

        printings.extend(_card_from_json(item) for item in data.get("data", []))

        url = data.get("next_page") if data.get("has_more") else None

    return printings or [card]
