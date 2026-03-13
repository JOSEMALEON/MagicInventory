from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTextEdit,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QGroupBox
)

from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt

import requests

from api.scryfall_api import search_card_by_name
from database.database_manager import add_card, get_all_cards, create_database


class MainWindow(QWidget):

    def __init__(self):
        super().__init__()

        create_database()

        self.setWindowTitle("Magic Inventory")
        self.setMinimumSize(1000, 700)

        # =============================
        # MAIN LAYOUT
        # =============================

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # =============================
        # TOP BAR
        # =============================

        top_bar = QWidget()
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(15, 10, 15, 10)

        title = QLabel("Magic Inventory")
        title.setObjectName("appTitle")

        top_layout.addWidget(title)
        top_layout.addStretch()

        top_bar.setLayout(top_layout)

        main_layout.addWidget(top_bar)

        # =============================
        # DASHBOARD LAYOUT
        # =============================

        dashboard_layout = QHBoxLayout()
        dashboard_layout.setContentsMargins(15, 15, 15, 15)
        dashboard_layout.setSpacing(20)

        # =============================
        # SIDEBAR
        # =============================

        sidebar_layout = QVBoxLayout()

        search_nav = QPushButton("Search")
        collection_nav = QPushButton("Collection")

        sidebar_layout.addWidget(search_nav)
        sidebar_layout.addWidget(collection_nav)
        sidebar_layout.addStretch()

        sidebar_widget = QWidget()
        sidebar_widget.setLayout(sidebar_layout)
        sidebar_widget.setFixedWidth(140)

        dashboard_layout.addWidget(sidebar_widget)

        # =============================
        # CARD PANEL
        # =============================

        card_panel = QVBoxLayout()
        card_panel.setSpacing(10)

        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter card name")

        search_button = QPushButton("Search Card")
        search_button.clicked.connect(self.search_card)

        card_panel.addWidget(self.search_input)
        card_panel.addWidget(search_button)

        # Card info
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

        card_panel.addWidget(card_group)

        # Quantity
        quantity_label = QLabel("Quantity")

        self.quantity_input = QSpinBox()
        self.quantity_input.setMinimum(1)
        self.quantity_input.setMaximum(100)

        card_panel.addWidget(quantity_label)
        card_panel.addWidget(self.quantity_input)

        # Add button
        save_button = QPushButton("Add to Collection")
        save_button.clicked.connect(self.save_card)

        card_panel.addWidget(save_button)
        card_panel.addStretch()

        card_panel_widget = QWidget()
        card_panel_widget.setLayout(card_panel)
        card_panel_widget.setFixedWidth(360)

        dashboard_layout.addWidget(card_panel_widget)

        # =============================
        # COLLECTION PANEL
        # =============================

        collection_panel = QVBoxLayout()
        collection_panel.setSpacing(10)

        collection_button = QPushButton("Show Collection")
        collection_button.clicked.connect(self.show_collection)

        collection_panel.addWidget(collection_button)

        self.collection_table = QTableWidget()
        self.collection_table.setColumnCount(4)
        self.collection_table.setHorizontalHeaderLabels(
            ["Image", "Name", "Set", "Quantity"]
        )

        self.collection_table.setColumnWidth(0, 120)
        self.collection_table.verticalHeader().setDefaultSectionSize(150)
        self.collection_table.horizontalHeader().setStretchLastSection(True)

        collection_panel.addWidget(self.collection_table)

        collection_panel_widget = QWidget()
        collection_panel_widget.setLayout(collection_panel)

        dashboard_layout.addWidget(collection_panel_widget)

        # =============================
        # ADD DASHBOARD
        # =============================

        main_layout.addLayout(dashboard_layout)

        self.setLayout(main_layout)

        self.current_card = None

    # ==================================
    # SEARCH CARD
    # ==================================

    def search_card(self):

        card_name = self.search_input.text()

        if not card_name:
            self.result_area.setText("Please enter a card name")
            return

        card = search_card_by_name(card_name)

        if card:

            self.current_card = card

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

    # ==================================
    # SAVE CARD
    # ==================================

    def save_card(self):

        if not self.current_card:
            self.result_area.setText("No card selected")
            return

        quantity = self.quantity_input.value()

        self.current_card.quantity = quantity

        add_card(self.current_card)

        self.result_area.append("\nCard added to collection!")

        # Actualizar tabla automáticamente
        self.show_collection()

    # ==================================
    # SHOW COLLECTION
    # ==================================

    def show_collection(self):

        cards = get_all_cards()

        if not cards:
            self.collection_table.setRowCount(0)
            return

        self.collection_table.setRowCount(len(cards))

        for row, card in enumerate(cards):

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

            self.collection_table.setItem(
                row, 1, QTableWidgetItem(card.name)
            )

            self.collection_table.setItem(
                row, 2, QTableWidgetItem(card.set_name)
            )

            self.collection_table.setItem(
                row, 3, QTableWidgetItem(str(card.quantity))
            )