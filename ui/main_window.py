from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTextEdit,
    QSpinBox
)

from api.scryfall_api import search_card_by_name
from database.database_manager import add_card, get_all_cards, create_database

import sys


class MainWindow(QWidget):

    def __init__(self):
        super().__init__()

        # Asegura que la base de datos exista
        create_database()

        self.setWindowTitle("Magic Inventory")
        self.setMinimumSize(400, 450)

        layout = QVBoxLayout()

        title = QLabel("Magic Inventory")
        layout.addWidget(title)

        # Campo de búsqueda
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter card name")
        layout.addWidget(self.search_input)

        # Botón buscar
        search_button = QPushButton("Search Card")
        search_button.clicked.connect(self.search_card)
        layout.addWidget(search_button)

        # Área de resultados
        self.result_area = QTextEdit()
        self.result_area.setReadOnly(True)
        layout.addWidget(self.result_area)

        # Selector de cantidad
        quantity_label = QLabel("Quantity")
        layout.addWidget(quantity_label)

        self.quantity_input = QSpinBox()
        self.quantity_input.setMinimum(1)
        self.quantity_input.setMaximum(100)
        layout.addWidget(self.quantity_input)

        # Botón añadir a colección
        save_button = QPushButton("Add to Collection")
        save_button.clicked.connect(self.save_card)
        layout.addWidget(save_button)

        # Botón mostrar colección
        collection_button = QPushButton("Show Collection")
        collection_button.clicked.connect(self.show_collection)
        layout.addWidget(collection_button)

        # Botón salir
        exit_button = QPushButton("Exit")
        exit_button.clicked.connect(self.close)
        layout.addWidget(exit_button)

        self.setLayout(layout)

        self.current_card = None


    def search_card(self):

        card_name = self.search_input.text()

        if not card_name:
            self.result_area.setText("Please enter a card name")
            return

        card = search_card_by_name(card_name)

        if card:

            self.current_card = card

            result_text = f"""
Name: {card.name}
Set: {card.set_name}
Type: {card.type_line}
Mana Cost: {card.mana_cost}
Rarity: {card.rarity}
"""

            self.result_area.setText(result_text)

        else:
            self.result_area.setText("Card not found")


    def save_card(self):

        if not self.current_card:
            self.result_area.setText("No card selected")
            return

        quantity = self.quantity_input.value()

        self.current_card.quantity = quantity

        add_card(self.current_card)

        self.result_area.append("\nCard added to collection!")


    def show_collection(self):

        cards = get_all_cards()

        if not cards:
            self.result_area.setText("Collection is empty")
            return

        text = "Your Collection:\n\n"

        for card in cards:
            text += f"{card.name} × {card.quantity}\n"

        self.result_area.setText(text)


def run_app():

    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())