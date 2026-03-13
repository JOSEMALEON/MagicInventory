from api.scryfall_api import search_card_by_name
from database.database_manager import create_database, add_card, get_all_cards


def search_card():

    card_name = input("Enter card name: ")

    card = search_card_by_name(card_name)

    if card:

        print("\nCard found:")
        print(card)

        save = input("\nSave card to collection? (y/n): ")

        if save.lower() == "y":

            try:
                quantity = int(input("Enter quantity: "))
            except ValueError:
                print("Invalid quantity. Using quantity = 1")
                quantity = 1

            card.quantity = quantity

            add_card(card)

            print("Card saved!")

    else:
        print("Card not found")


def show_collection():

    cards = get_all_cards()

    if not cards:
        print("\nCollection is empty\n")
        return

    print("\nYour Collection:\n")

    for card in cards:
        print(card)


def main():

    create_database()

    while True:

        print("\nMagic Inventory\n")
        print("1 - Search card")
        print("2 - Show collection")
        print("3 - Exit")

        option = input("\nSelect option: ")

        if option == "1":
            search_card()

        elif option == "2":
            show_collection()

        elif option == "3":
            print("Goodbye!")
            break

        else:
            print("Invalid option")


if __name__ == "__main__":
    main()