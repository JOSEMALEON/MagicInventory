import requests

SCRYFALL_API_URL = "https://api.scryfall.com/cards/named"


def search_card_by_name(card_name):
    """
    Search a Magic card by name using Scryfall API
    """

    params = {
        "fuzzy": card_name
    }

    response = requests.get(SCRYFALL_API_URL, params=params)

    if response.status_code == 200:

        data = response.json()

        card_info = {
            "name": data.get("name"),
            "set": data.get("set_name"),
            "type": data.get("type_line"),
            "mana_cost": data.get("mana_cost"),
            "rarity": data.get("rarity"),
            "image": data.get("image_uris", {}).get("normal")
        }

        return card_info

    else:
        return None