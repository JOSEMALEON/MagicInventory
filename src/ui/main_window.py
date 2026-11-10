from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTextEdit,
    QSpinBox,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QGroupBox
)

from PySide6.QtCore import Qt

from services.card_service import (
    search_card,
    get_printings,
    save_card,
    get_collection,
    ScryfallError,
)
from services.image_service import load_card_image, to_pixmap
from database.database_manager import create_database
from src.ui.background import BackgroundRunner


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

        # EDITION SELECTOR (filled after each search with every printing)
        edition_label = QLabel("Edition")

        self.edition_input = QComboBox()
        self.edition_input.setEnabled(False)
        self.edition_input.currentIndexChanged.connect(self.select_printing)

        card_panel.addWidget(edition_label)
        card_panel.addWidget(self.edition_input)

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
        self.printings = []

        # Network and disk work runs here so the window never freezes
        self.background = BackgroundRunner()

        # Each new request increases its counter; when an answer arrives,
        # it is ignored if a newer request has been made in the meantime
        self._search_id = 0
        self._image_id = 0
        self._collection_id = 0

        # Show the saved collection as soon as the app opens
        self.show_collection()

    # ==================================
    # SEARCH CARD
    # ==================================

    def search_card(self):

        card_name = self.search_input.text().strip()

        if not card_name:
            self.result_area.setText("Please enter a card name")
            return

        self._search_id += 1
        search_id = self._search_id

        # Forget the previous card so "Add to Collection" can't add it by mistake
        self.current_card = None
        self._set_printings([])
        self._image_id += 1
        self.card_image.clear()
        self.result_area.setText(f"Searching \"{card_name}\"...")
        self.search_input.clear()

        self.background.run(
            lambda: search_card(card_name),
            on_success=lambda card: self._on_card_found(search_id, card),
            on_error=lambda error: self._on_search_error(search_id, error),
        )

    def _on_card_found(self, search_id, card):

        if search_id != self._search_id:
            return

        if not card:
            self.result_area.setText("Card not found")
            return

        self._show_card(card)

        # Show the default edition now; the full list arrives later
        self._set_printings([card], selected=card)

        self.background.run(
            lambda: get_printings(card),
            on_success=lambda printings: self._on_printings_loaded(search_id, card, printings),
            # The card itself is fine; just keep offering the default edition
            on_error=lambda error: None,
        )

    def _on_search_error(self, search_id, error):

        if search_id != self._search_id:
            return

        if isinstance(error, ScryfallError):
            self.result_area.setText(
                "Could not connect to Scryfall.\nCheck your connection and try again."
            )
        else:
            self.result_area.setText(f"Unexpected error: {error}")

    def _on_printings_loaded(self, search_id, card, printings):

        if search_id != self._search_id:
            return

        # Keep whatever edition the user may have picked meanwhile
        self._set_printings(printings, selected=self.current_card or card)

    # ==================================
    # EDITION SELECTOR
    # ==================================

    def _set_printings(self, printings, selected=None):
        """
        Fill the edition combo box and select the given printing.
        """

        self.printings = printings

        # Avoid select_printing() firing (and downloading images) while filling
        self.edition_input.blockSignals(True)
        self.edition_input.clear()

        selected_index = 0

        for index, printing in enumerate(printings):
            self.edition_input.addItem(printing.printing_label)

            if selected and printing.scryfall_id == selected.scryfall_id:
                selected_index = index

        if printings:
            self.edition_input.setCurrentIndex(selected_index)

        self.edition_input.blockSignals(False)
        self.edition_input.setEnabled(len(printings) > 1)

    def select_printing(self, index):

        if 0 <= index < len(self.printings):
            self._show_card(self.printings[index])

    def _show_card(self, card):
        """
        Show the card's image and data, and make it the one that will be added.
        """

        self.current_card = card

        self._image_id += 1
        image_id = self._image_id
        self.card_image.clear()

        self.background.run(
            lambda: load_card_image(card.image_url, width=200),
            on_success=lambda image: self._on_card_image_loaded(image_id, image),
        )

        result_text = f"""
Name: {card.name}
Set: {card.printing_label}
Type: {card.type_line}
Mana Cost: {card.mana_cost}
Rarity: {card.rarity}
"""
        self.result_area.setText(result_text)

    def _on_card_image_loaded(self, image_id, image):

        # Ignore images of an edition the user has already moved away from
        if image_id != self._image_id or image is None:
            return

        self.card_image.setPixmap(to_pixmap(image))

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

        # Images still loading for the previous table must not land in this one
        self._collection_id += 1
        collection_id = self._collection_id

        # Remove old images/texts so a row never shows another card's data
        self.collection_table.clearContents()
        self.collection_table.setRowCount(len(cards))

        for row, card in enumerate(cards):

            self.collection_table.setItem(row, 1, QTableWidgetItem(card.name))
            self.collection_table.setItem(row, 2, QTableWidgetItem(card.printing_label))
            self.collection_table.setItem(row, 3, QTableWidgetItem(str(card.quantity)))

            # Default arguments freeze the current row/url for each lambda
            self.background.run(
                lambda url=card.image_url: load_card_image(url, width=100, height=140),
                on_success=lambda image, row=row: self._on_table_image_loaded(
                    collection_id, row, image
                ),
            )

    def _on_table_image_loaded(self, collection_id, row, image):

        if collection_id != self._collection_id or image is None:
            return

        label = QLabel()
        label.setPixmap(to_pixmap(image))
        self.collection_table.setCellWidget(row, 0, label)