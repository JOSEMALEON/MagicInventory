from api.scryfall_api import search_card_by_name


def main():

    print("Magic Inventory started")

    card_name = input("Enter card name: ")

    card = search_card_by_name(card_name)

    if card:

        print("\nCard found:\n")

        for key, value in card.items():
            print(f"{key}: {value}")

    else:
        print("Card not found")


if __name__ == "__main__":
    main()