from api.scryfall_api import search_card_by_name


def main():

    print("Magic Inventory started")

    card_name = input("Enter card name: ")

    card = search_card_by_name(card_name)

    if card:

        print("\nCard found:")
        print(card)

    else:
        print("Card not found")


if __name__ == "__main__":
    main()