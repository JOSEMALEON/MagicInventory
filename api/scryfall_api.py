import requests
from models.card import Card

SCRYFALL_API_URL = "https://api.scryfall.com/cards/named"


def search_card_by_name(card_name):

    params = {
        "fuzzy": card_name
    }

    response = requests.get(SCRYFALL_API_URL, params=params)

    if response.status_code == 200:

        data = response.json()

        card = Card(
            name=data.get("name"),
            set_name=data.get("set_name"),
            type_line=data.get("type_line"),
            mana_cost=data.get("mana_cost"),
            rarity=data.get("rarity"),
            image_url=data.get("image_uris", {}).get("normal")
        )

        return card

    else:
        return None