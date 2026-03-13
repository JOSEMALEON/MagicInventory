from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton
)

from api.scryfall_api import search_card_by_name
from database.database_manager import add_card, get_all_cards

import sys


class MainWindow(QWidget):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Magic Inventory")
        self.setMinimumSize(400, 300)

        layout = QVBoxLayout()

        title = QLabel("Magic Inventory")
        layout.addWidget(title)

        search_button = QPushButton("Search Card")
        search_button.clicked.connect(self.search_card)
        layout.addWidget(search_button)

        collection_button = QPushButton("Show Collection")
        collection_button.clicked.connect(self.show_collection)
        layout.addWidget(collection_button)

        exit_button = QPushButton("Exit")
        exit_button.clicked.connect(self.close)
        layout.addWidget(exit_button)

        self.setLayout(layout)


    def search_card(self):

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
                    print("Invalid quantity, using 1")
                    quantity = 1

                card.quantity = quantity

                add_card(card)

                print("Card saved!")

        else:
            print("Card not found")


    def show_collection(self):

        cards = get_all_cards()

        if not cards:
            print("\nCollection is empty\n")
            return

        print("\nYour Collection:\n")

        for card in cards:
            print(card)


def run_app():

    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())