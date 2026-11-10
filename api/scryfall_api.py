import time

import requests

from models.card import Card
from src.config import REQUEST_TIMEOUT, HTTP_HEADERS

SCRYFALL_NAMED_URL = "https://api.scryfall.com/cards/named"


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


def _card_from_json(data):

    return Card(
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


def _get_json(url, params=None):
    """
    GET a Scryfall URL and return the decoded JSON, or None on 404.
    Raise ScryfallError if the request fails.
    """

    try:
        response = requests.get(
            url,
            params=params,
            headers=HTTP_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as error:
        raise ScryfallError(f"Could not connect to Scryfall: {error}") from error

    if response.status_code == 404:
        return None

    if response.status_code != 200:
        raise ScryfallError(f"Scryfall answered with status {response.status_code}")

    try:
        return response.json()
    except ValueError as error:
        raise ScryfallError("Scryfall returned an invalid response") from error


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


def get_card_printings(card):
    """
    Return a list of Cards, one per printing (edition) of the given card,
    newest first. Raise ScryfallError if a request fails.
    """

    if not card.prints_search_uri:
        return [card]

    printings = []
    url = card.prints_search_uri

    while url:
        data = _get_json(url)

        if data is None:
            break

        printings.extend(_card_from_json(item) for item in data.get("data", []))

        url = data.get("next_page") if data.get("has_more") else None

        if url:
            # Scryfall asks for 50-100 ms between requests
            time.sleep(0.1)

    return printings or [card]
