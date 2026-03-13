from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTextEdit,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem
)

from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox

import requests
import sys

from api.scryfall_api import search_card_by_name
from database.database_manager import add_card, get_all_cards, create_database


class MainWindow(QWidget):

    def __init__(self):
        super().__init__()

        # Crear base de datos si no existe
        create_database()

        self.setWindowTitle("Magic Inventory")
        self.setMinimumSize(800, 600)

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

        # Layout horizontal para imagen + información
        card_group = QGroupBox("Card Information")

        card_layout = QHBoxLayout()

        self.card_image = QLabel()
        self.card_image.setFixedSize(200, 280)
        card_layout.addWidget(self.card_image)

        self.result_area = QTextEdit()
        self.result_area.setReadOnly(True)
        self.result_area.setFixedHeight(120)
        card_layout.addWidget(self.result_area)

        card_group.setLayout(card_layout)

        layout.addWidget(card_group)

        # Selector de cantidad
        quantity_label = QLabel("Quantity")
        layout.addWidget(quantity_label)

        self.quantity_input = QSpinBox()
        self.quantity_input.setMinimum(1)
        self.quantity_input.setMaximum(100)
        layout.addWidget(self.quantity_input)

        # Botón guardar
        save_button = QPushButton("Add to Collection")
        save_button.clicked.connect(self.save_card)
        layout.addWidget(save_button)

        # Botón mostrar colección
        collection_button = QPushButton("Show Collection")
        collection_button.clicked.connect(self.show_collection)
        layout.addWidget(collection_button)

        # Tabla colección
        self.collection_table = QTableWidget()
        self.collection_table.setColumnCount(4)
        self.collection_table.setHorizontalHeaderLabels(
            ["Image", "Name", "Set", "Quantity"]
        )

        self.collection_table.setColumnWidth(0, 120)
        self.collection_table.verticalHeader().setDefaultSectionSize(150)

        self.collection_table.setMinimumHeight(300)
        self.collection_table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(self.collection_table)

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

            # Mostrar imagen
            try:
                response = requests.get(card.image_url)

                if response.status_code == 200:
                    pixmap = QPixmap()
                    pixmap.loadFromData(response.content)
                    pixmap = pixmap.scaledToWidth(200)

                    self.card_image.setPixmap(pixmap)

            except Exception:
                pass

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

        # limpiar imagen de búsqueda
        self.card_image.clear()

        if not cards:
            self.collection_table.setRowCount(0)
            return

        self.collection_table.setRowCount(len(cards))

        for row, card in enumerate(cards):

            # Imagen
            try:
                response = requests.get(card.image_url)

                if response.status_code == 200:
                    pixmap = QPixmap()
                    pixmap.loadFromData(response.content)

                    pixmap = pixmap.scaled(
                        100,
                        140,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )

                    label = QLabel()
                    label.setPixmap(pixmap)

                    self.collection_table.setCellWidget(row, 0, label)

            except Exception:
                pass

            # Nombre
            self.collection_table.setItem(
                row, 1, QTableWidgetItem(card.name)
            )

            # Set
            self.collection_table.setItem(
                row, 2, QTableWidgetItem(card.set_name)
            )

            # Quantity
            self.collection_table.setItem(
                row, 3, QTableWidgetItem(str(card.quantity))
            )


def run_app():

    app = QApplication(sys.argv)

    window = MainWindow()
    window.showMaximized()
    
    sys.exit(app.exec())