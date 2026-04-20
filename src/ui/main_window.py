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

from PySide6.QtCore import Qt

from services.card_service import search_card, save_card, get_collection
from services.image_service import get_card_pixmap
from database.database_manager import create_database


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

        # SEARCH BAR
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search card...")
        self.search_input.returnPressed.connect(self.search_card)

        search_button = QPushButton("Search")
        search_button.clicked.connect(self.search_card)

        top_layout.addWidget(self.search_input)
        top_layout.addWidget(search_button)

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

        quantity_label = QLabel("Quantity")

        self.quantity_input = QSpinBox()
        self.quantity_input.setMinimum(1)
        self.quantity_input.setMaximum(100)

        card_panel.addWidget(quantity_label)
        card_panel.addWidget(self.quantity_input)

        save_button = QPushButton("Add to Collection")
        save_button.clicked.connect(self.save_card)

        card_panel.addWidget(save_button)
        card_panel.addStretch()

        card_panel_widget = QWidget()
        card_panel_widget.setLayout(card_panel)
        card_panel_widget.setFixedWidth(360)

        card_container = QWidget()
        card_container_layout = QVBoxLayout()
        card_container_layout.setContentsMargins(15, 15, 15, 15)
        card_container_layout.addWidget(card_panel_widget)
        card_container.setLayout(card_container_layout)

        dashboard_layout.addWidget(card_container)

        # =============================
        # COLLECTION PANEL
        # =============================

        collection_panel = QVBoxLayout()
        collection_panel.setSpacing(10)

        collection_button = QPushButton("Refresh")
        collection_button.clicked.connect(self.show_collection)

        header_layout = QHBoxLayout()

        collection_title = QLabel("My Collection")
        collection_title.setObjectName("sectionTitle")

        header_layout.addWidget(collection_title)
        header_layout.addStretch()
        header_layout.addWidget(collection_button)

        collection_panel.addLayout(header_layout)

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

        collection_container = QWidget()
        collection_container_layout = QVBoxLayout()
        collection_container_layout.setContentsMargins(15, 15, 15, 15)
        collection_container_layout.addWidget(collection_panel_widget)
        collection_container.setLayout(collection_container_layout)

        dashboard_layout.addWidget(collection_container)

        # =============================
        # FINALIZE
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

        card = search_card(card_name)

        if card:
            self.current_card = card

            pixmap = get_card_pixmap(card.image_url, width=200)
            if pixmap:
                self.card_image.setPixmap(pixmap)

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

        self.search_input.clear()

    # ==================================
    # SAVE CARD
    # ==================================

    def save_card(self):

        if not self.current_card:
            self.result_area.setText("No card selected")
            return

        quantity = self.quantity_input.value()
        self.current_card.quantity = quantity

        save_card(self.current_card)

        self.result_area.append("\nCard added to collection!")
        self.show_collection()

    # ==================================
    # SHOW COLLECTION
    # ==================================

    def show_collection(self):

        cards = get_collection()

        if not cards:
            self.collection_table.setRowCount(0)
            return

        self.collection_table.setRowCount(len(cards))

        for row, card in enumerate(cards):

            pixmap = get_card_pixmap(card.image_url, width=100, height=140)

            if pixmap:
                label = QLabel()
                label.setPixmap(pixmap)
                self.collection_table.setCellWidget(row, 0, label)

            self.collection_table.setItem(row, 1, QTableWidgetItem(card.name))
            self.collection_table.setItem(row, 2, QTableWidgetItem(card.set_name))
            self.collection_table.setItem(row, 3, QTableWidgetItem(str(card.quantity)))