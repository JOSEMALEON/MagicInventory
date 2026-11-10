import re

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QSpinBox,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QStackedWidget,
    QButtonGroup,
    QAbstractItemView,
    QHeaderView,
    QMenu,
    QMessageBox,
    QDialog,
)

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut

from services.card_service import (
    search_card,
    get_printings,
    save_card,
    get_collection,
    remove_cards,
    set_quantity,
    change_card_printing,
    ScryfallError,
)
from services.image_service import load_card_image, to_pixmap
from database.database_manager import create_database
from src.config import RARITY_COLORS
from src.ui.background import BackgroundRunner
from src.ui.edition_dialog import EditionDialog
from src.ui.widgets import QuantitySpinBox, set_status, styled_panel


# Size of the big card image on the search page (Scryfall "normal" ratio)
CARD_IMAGE_WIDTH = 320
CARD_IMAGE_HEIGHT = 446

# Size of the thumbnails in the collection table
THUMB_WIDTH = 90
THUMB_HEIGHT = 126

# Collection table columns
COL_IMAGE, COL_NAME, COL_EDITION, COL_RARITY, COL_QUANTITY = range(5)

# Rarity order used when sorting the collection (best first)
RARITY_ORDER = {"mythic": 0, "rare": 1, "uncommon": 2, "common": 3, "special": 4, "bonus": 5}

# Sort options of the collection: label -> (key function, reverse)
SORT_OPTIONS = {
    "Name (A–Z)": (lambda card: ((card.name or "").lower(), card.printing_label.lower()), False),
    "Recently added": (lambda card: card.id or 0, True),
    "Quantity (high–low)": (lambda card: (card.quantity or 0), True),
    "Edition": (lambda card: (card.printing_label.lower(), (card.name or "").lower()), False),
    "Rarity": (lambda card: (RARITY_ORDER.get(card.rarity, 9), (card.name or "").lower()), False),
}


def plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


def format_mana_cost(mana_cost):
    """
    "{2}{U}{U}" -> "2 U U". Double-faced costs keep their " // " separator.
    """

    if not mana_cost:
        return "No mana cost"

    faces = mana_cost.split(" // ")
    return "  //  ".join(" ".join(re.findall(r"\{([^}]+)\}", face)) for face in faces)


class MainWindow(QWidget):

    def __init__(self):
        super().__init__()

        create_database()

        self.setObjectName("mainWindow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Magic Inventory")
        self.setMinimumSize(1100, 720)

        self.current_card = None
        self.printings = []

        # Cards of the collection (from the database) and their thumbnails,
        # kept in memory so filtering/sorting never reloads anything
        self.collection_cards = []
        self._thumbnails = {}

        # Network and disk work runs here so the window never freezes
        self.background = BackgroundRunner()

        # Each new request increases its counter; when an answer arrives,
        # it is ignored if a newer request has been made in the meantime
        self._search_id = 0
        self._image_id = 0
        self._collection_id = 0

        # =============================
        # MAIN LAYOUT
        # =============================

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self._build_top_bar())

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # One page per sidebar button; only the current one is visible
        self.pages = QStackedWidget()
        self.search_page = self._build_search_page()
        self.collection_page = self._build_collection_page()
        self.pages.addWidget(self.search_page)
        self.pages.addWidget(self.collection_page)

        body_layout.addWidget(self._build_sidebar())
        body_layout.addWidget(self.pages)

        main_layout.addLayout(body_layout)
        self.setLayout(main_layout)

        self.show_page(self.search_page)
        self._show_empty_card()

        # Load the saved collection as soon as the app opens
        self.show_collection()

    # ==================================
    # LAYOUT BUILDERS
    # ==================================

    def _build_top_bar(self):

        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(24, 14, 24, 14)
        top_layout.setSpacing(10)

        logo = QLabel("◆")
        logo.setObjectName("appLogo")

        title = QLabel("Magic Inventory")
        title.setObjectName("appTitle")

        top_layout.addWidget(logo)
        top_layout.addWidget(title)
        top_layout.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("Search a card by name…")
        self.search_input.setFixedWidth(420)
        self.search_input.returnPressed.connect(self.search_card)

        search_button = QPushButton("Search")
        search_button.setObjectName("primaryButton")
        search_button.clicked.connect(self.search_card)

        top_layout.addWidget(self.search_input)
        top_layout.addWidget(search_button)

        return styled_panel("topBar", top_layout)

    def _build_sidebar(self):

        sidebar_layout = QVBoxLayout()
        sidebar_layout.setContentsMargins(12, 20, 12, 20)
        sidebar_layout.setSpacing(6)

        section = QLabel("LIBRARY")
        section.setObjectName("sidebarSection")
        sidebar_layout.addWidget(section)

        self.search_nav = QPushButton("Search")
        self.collection_nav = QPushButton("Collection")

        # Exclusive checkable buttons: the active page stays highlighted
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        for button in (self.search_nav, self.collection_nav):
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.nav_group.addButton(button)
            sidebar_layout.addWidget(button)

        self.search_nav.clicked.connect(lambda: self.show_page(self.search_page))
        self.collection_nav.clicked.connect(lambda: self.show_page(self.collection_page))

        sidebar_layout.addStretch()

        sidebar = styled_panel("sidebar", sidebar_layout)
        sidebar.setFixedWidth(190)

        return sidebar

    def _build_search_page(self):

        # ---------- Left: card image ----------

        self.card_image = QLabel()
        self.card_image.setObjectName("cardImage")
        self.card_image.setFixedSize(CARD_IMAGE_WIDTH, CARD_IMAGE_HEIGHT)
        self.card_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.card_image.setWordWrap(True)

        # ---------- Right: card details ----------

        self.card_name = QLabel()
        self.card_name.setObjectName("cardName")
        self.card_name.setWordWrap(True)

        self.card_type = QLabel()
        self.card_type.setObjectName("cardType")
        self.card_type.setWordWrap(True)

        self.card_mana = QLabel()
        self.card_mana.setObjectName("manaCost")

        self.card_rarity = QLabel()
        self.card_rarity.setObjectName("rarityBadge")

        meta_row = QHBoxLayout()
        meta_row.setSpacing(10)
        meta_row.addWidget(self.card_mana)
        meta_row.addWidget(self.card_rarity)
        meta_row.addStretch()

        self.card_set = QLabel()
        self.card_set.setObjectName("mutedLabel")
        self.card_set.setWordWrap(True)

        # "In your collection: 3 of this edition · 5 in total"
        self.owned_label = QLabel()
        self.owned_label.setObjectName("ownedLabel")
        self.owned_label.setWordWrap(True)

        edition_label = QLabel("EDITION")
        edition_label.setObjectName("fieldLabel")

        # Filled after each search with every printing of the card
        self.edition_input = QComboBox()
        self.edition_input.setEnabled(False)
        self.edition_input.setMaxVisibleItems(15)
        self.edition_input.currentIndexChanged.connect(self.select_printing)

        quantity_label = QLabel("QUANTITY")
        quantity_label.setObjectName("fieldLabel")

        self.quantity_input = QSpinBox()
        self.quantity_input.setMinimum(1)
        self.quantity_input.setMaximum(100)
        self.quantity_input.setFixedWidth(90)

        self.save_button = QPushButton("Add to Collection")
        self.save_button.setObjectName("primaryButton")
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.clicked.connect(self.save_card)

        add_row = QHBoxLayout()
        add_row.setSpacing(10)
        add_row.addWidget(self.quantity_input)
        add_row.addWidget(self.save_button, 1)

        # Feedback line: searching, not found, added...
        self.status_label = QLabel()
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)

        details = QVBoxLayout()
        details.setSpacing(8)
        details.addWidget(self.card_name)
        details.addWidget(self.card_type)
        details.addSpacing(4)
        details.addLayout(meta_row)
        details.addWidget(self.card_set)
        details.addWidget(self.owned_label)
        details.addSpacing(20)
        details.addWidget(edition_label)
        details.addWidget(self.edition_input)
        details.addSpacing(10)
        details.addWidget(quantity_label)
        details.addLayout(add_row)
        details.addSpacing(10)
        details.addWidget(self.status_label)
        details.addStretch()

        details_widget = QWidget()
        details_widget.setLayout(details)
        details_widget.setFixedWidth(420)

        # ---------- Card panel ----------

        card_layout = QHBoxLayout()
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(32)
        card_layout.addWidget(self.card_image, 0, Qt.AlignmentFlag.AlignTop)
        card_layout.addWidget(details_widget)

        card_panel = styled_panel("cardPanel", card_layout)

        page_layout = QVBoxLayout()
        page_layout.setContentsMargins(32, 28, 32, 28)
        page_layout.setSpacing(18)

        page_title = QLabel("Search")
        page_title.setObjectName("pageTitle")

        panel_row = QHBoxLayout()
        panel_row.addWidget(card_panel)
        panel_row.addStretch()

        page_layout.addWidget(page_title)
        page_layout.addLayout(panel_row)
        page_layout.addStretch()

        page = QWidget()
        page.setLayout(page_layout)

        return page

    def _build_collection_page(self):

        header_layout = QHBoxLayout()
        header_layout.setSpacing(14)

        collection_title = QLabel("My Collection")
        collection_title.setObjectName("pageTitle")

        self.collection_summary = QLabel()
        self.collection_summary.setObjectName("mutedLabel")

        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("secondaryButton")
        refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_button.clicked.connect(self.show_collection)

        header_layout.addWidget(collection_title)
        header_layout.addWidget(self.collection_summary, 0, Qt.AlignmentFlag.AlignBottom)
        header_layout.addStretch()
        header_layout.addWidget(refresh_button)

        # ---------- Toolbar: filter, sort and actions ----------

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter by name, edition, type or rarity…")
        self.filter_input.setClearButtonEnabled(True)
        self.filter_input.setFixedWidth(340)
        self.filter_input.textChanged.connect(self._apply_filter)

        sort_label = QLabel("Sort by")
        sort_label.setObjectName("mutedLabel")

        self.sort_input = QComboBox()
        self.sort_input.addItems(list(SORT_OPTIONS))
        self.sort_input.currentIndexChanged.connect(self._render_collection)

        self.selection_label = QLabel()
        self.selection_label.setObjectName("mutedLabel")

        self.change_edition_button = QPushButton("Change edition…")
        self.change_edition_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.change_edition_button.clicked.connect(self.change_selected_edition)

        self.delete_button = QPushButton("Delete")
        self.delete_button.setObjectName("dangerButton")
        self.delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_button.clicked.connect(self.delete_selected_cards)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        toolbar.addWidget(self.filter_input)
        toolbar.addSpacing(6)
        toolbar.addWidget(sort_label)
        toolbar.addWidget(self.sort_input)
        toolbar.addStretch()
        toolbar.addWidget(self.selection_label)
        toolbar.addWidget(self.change_edition_button)
        toolbar.addWidget(self.delete_button)

        # ---------- Table ----------

        table = QTableWidget()
        self.collection_table = table
        table.setObjectName("collectionTable")
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["", "Name", "Edition", "Rarity", "Qty"])

        table.setShowGrid(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # Click = select one, Ctrl+click = add/remove, Shift+click = range
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(THUMB_HEIGHT + 16)
        table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        header = table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)
        header.setSectionResizeMode(COL_IMAGE, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_EDITION, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_RARITY, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_QUANTITY, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(COL_IMAGE, THUMB_WIDTH + 30)
        table.setColumnWidth(COL_RARITY, 110)
        table.setColumnWidth(COL_QUANTITY, 120)

        table.itemSelectionChanged.connect(self._update_selection_actions)
        table.cellDoubleClicked.connect(lambda row, column: self.change_selected_edition())

        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._show_collection_menu)

        # Delete key removes the selected cards (only while the table has focus)
        delete_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Delete), table)
        delete_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        delete_shortcut.activated.connect(self.delete_selected_cards)

        self.collection_status = QLabel()
        self.collection_status.setObjectName("statusLabel")

        page_layout = QVBoxLayout()
        page_layout.setContentsMargins(32, 28, 32, 28)
        page_layout.setSpacing(14)
        page_layout.addLayout(header_layout)
        page_layout.addLayout(toolbar)
        page_layout.addWidget(table)
        page_layout.addWidget(self.collection_status)

        page = QWidget()
        page.setLayout(page_layout)

        return page

    # ==================================
    # NAVIGATION
    # ==================================

    def show_page(self, page):

        self.pages.setCurrentWidget(page)

        # Keep the sidebar in sync, also when the page changes from code
        nav_button = self.search_nav if page is self.search_page else self.collection_nav
        nav_button.setChecked(True)

    # ==================================
    # STATUS MESSAGES
    # ==================================

    def _set_status(self, text, state="info"):
        """
        Feedback message of the search page ("info", "success" or "error").
        """
        set_status(self.status_label, text, state)

    # ==================================
    # SEARCH CARD
    # ==================================

    def search_card(self):

        card_name = self.search_input.text().strip()

        # Searching from the top bar always shows the result
        self.show_page(self.search_page)

        if not card_name:
            self._set_status("Type a card name in the search bar.", "error")
            return

        self._search_id += 1
        search_id = self._search_id

        # Forget the previous card so "Add to Collection" can't add it by mistake
        self._show_empty_card(f"Searching “{card_name}”…")
        self._set_status("")
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
            self._show_empty_card()
            self._set_status("Card not found. Check the spelling and try again.", "error")
            return

        self._show_card(card)

        # Show the default edition now; the full list arrives later
        self._set_printings([card], selected=card)
        self._set_status("Loading editions…")

        self.background.run(
            lambda: get_printings(card),
            on_success=lambda printings: self._on_printings_loaded(search_id, card, printings),
            # The card itself is fine; just keep offering the default edition
            on_error=lambda error: self._on_printings_error(search_id),
        )

    def _on_search_error(self, search_id, error):

        if search_id != self._search_id:
            return

        self._show_empty_card()

        if isinstance(error, ScryfallError):
            self._set_status(
                "Could not connect to Scryfall. Check your connection and try again.",
                "error",
            )
        else:
            self._set_status(f"Unexpected error: {error}", "error")

    def _on_printings_loaded(self, search_id, card, printings):

        if search_id != self._search_id:
            return

        # Keep whatever edition the user may have picked meanwhile
        self._set_printings(printings, selected=self.current_card or card)

        count = len(printings)
        self._set_status(f"{count} edition{'s' if count != 1 else ''} available.")

    def _on_printings_error(self, search_id):

        if search_id == self._search_id:
            self._set_status("Could not load the other editions.", "error")

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

    # ==================================
    # CARD PANEL
    # ==================================

    def _show_empty_card(self, message="Search a card to see it here"):
        """
        Reset the card panel: no card selected, nothing can be added.
        """

        self.current_card = None
        self._set_printings([])

        # Discard any image that is still loading
        self._image_id += 1
        self.card_image.clear()
        self.card_image.setText(message)

        self.card_name.setText("No card selected")
        self.card_type.setText("")
        self.card_mana.hide()
        self.card_rarity.hide()
        self.card_set.setText("")
        self.owned_label.setText("")
        self.save_button.setEnabled(False)

    def _show_card(self, card):
        """
        Show the card's image and data, and make it the one that will be added.
        """

        self.current_card = card

        self._image_id += 1
        image_id = self._image_id
        self.card_image.clear()
        self.card_image.setText("Loading image…")

        self.background.run(
            lambda: load_card_image(
                card.image_url, width=CARD_IMAGE_WIDTH, height=CARD_IMAGE_HEIGHT
            ),
            on_success=lambda image: self._on_card_image_loaded(image_id, image),
        )

        self.card_name.setText(card.name)
        self.card_type.setText(card.type_line or "")
        self.card_mana.setText(format_mana_cost(card.mana_cost))
        self.card_mana.show()
        self.card_set.setText(card.printing_label)
        self._set_rarity(card.rarity)
        self._update_owned_label()
        self.save_button.setEnabled(True)

    def _set_rarity(self, rarity):

        if not rarity:
            self.card_rarity.hide()
            return

        color = RARITY_COLORS.get(rarity, RARITY_COLORS["common"])

        self.card_rarity.setText(rarity.capitalize())
        self.card_rarity.setStyleSheet(f"color: {color}; border-color: {color};")
        self.card_rarity.show()

    def _on_card_image_loaded(self, image_id, image):

        # Ignore images of an edition the user has already moved away from
        if image_id != self._image_id:
            return

        if image is None:
            self.card_image.setText("Image not available")
            return

        self.card_image.setPixmap(to_pixmap(image))

    # ==================================
    # SAVE CARD
    # ==================================

    def save_card(self):

        if not self.current_card:
            self._set_status("Search a card first.", "error")
            return

        quantity = self.quantity_input.value()
        self.current_card.quantity = quantity

        save_card(self.current_card)

        self._set_status(
            f"Added {quantity} × {self.current_card.name} "
            f"({self.current_card.printing_label}) to your collection.",
            "success",
        )
        self.show_collection()

    # ==================================
    # COLLECTION: LOAD AND DISPLAY
    # ==================================

    def show_collection(self):
        """
        Reload the collection from the database and redraw the table.
        """

        self.collection_cards = get_collection()

        self._update_collection_summary()
        self._render_collection()
        self._update_owned_label()

    def _update_collection_summary(self):

        total = sum(card.quantity or 0 for card in self.collection_cards)
        self.collection_summary.setText(
            f"{plural(len(self.collection_cards), 'printing')} · {plural(total, 'card')}"
        )

    def _render_collection(self):
        """
        Fill the table with self.collection_cards in the chosen order.
        """

        key, reverse = SORT_OPTIONS[self.sort_input.currentText()]
        cards = sorted(self.collection_cards, key=key, reverse=reverse)

        # Images still loading for the previous table must not land in this one
        self._collection_id += 1
        collection_id = self._collection_id

        table = self.collection_table

        # Remove old images/texts so a row never shows another card's data
        table.clearSelection()
        table.clearContents()
        table.setRowCount(len(cards))

        for row, card in enumerate(cards):

            name_item = QTableWidgetItem(card.name)
            # The row remembers which database row it shows
            name_item.setData(Qt.ItemDataRole.UserRole, card.id)

            edition_item = QTableWidgetItem(card.printing_label)

            rarity_item = QTableWidgetItem((card.rarity or "").capitalize())
            if card.rarity in RARITY_COLORS:
                rarity_item.setForeground(QColor(RARITY_COLORS[card.rarity]))

            table.setItem(row, COL_NAME, name_item)
            table.setItem(row, COL_EDITION, edition_item)
            table.setItem(row, COL_RARITY, rarity_item)
            table.setCellWidget(row, COL_QUANTITY, self._quantity_cell(card))

            self._set_thumbnail(collection_id, row, card.image_url)

        self._apply_filter()
        self._update_selection_actions()

    def _quantity_cell(self, card):
        """
        A centered spin box that saves the new quantity as soon as it changes.
        """

        spin = QuantitySpinBox(card.quantity or 1)
        spin.setFixedWidth(84)
        spin.valueChanged.connect(
            lambda value, card_id=card.id: self._on_quantity_changed(card_id, value)
        )

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(spin, 0, Qt.AlignmentFlag.AlignCenter)

        cell = QWidget()
        cell.setLayout(layout)
        return cell

    def _set_thumbnail(self, collection_id, row, url):

        # Already decoded once: no need to touch the disk again
        if url in self._thumbnails:
            self._put_thumbnail(row, self._thumbnails[url])
            return

        # Default arguments freeze the current row/url for each lambda
        self.background.run(
            lambda url=url: load_card_image(url, width=THUMB_WIDTH, height=THUMB_HEIGHT),
            on_success=lambda image, row=row, url=url: self._on_table_image_loaded(
                collection_id, row, url, image
            ),
        )

    def _on_table_image_loaded(self, collection_id, row, url, image):

        if image is None:
            return

        pixmap = to_pixmap(image)
        self._thumbnails[url] = pixmap

        if collection_id == self._collection_id:
            self._put_thumbnail(row, pixmap)

    def _put_thumbnail(self, row, pixmap):

        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setPixmap(pixmap)
        self.collection_table.setCellWidget(row, COL_IMAGE, label)

    # ==================================
    # COLLECTION: FILTER AND SELECTION
    # ==================================

    def _apply_filter(self):
        """
        Hide the rows that don't contain the filter text in their name,
        edition, type or rarity. Nothing is reloaded.
        """

        words = self.filter_input.text().lower().split()
        cards_by_id = {card.id: card for card in self.collection_cards}

        # Hidden rows must not stay selected (they could be deleted by mistake)
        self.collection_table.clearSelection()

        visible = 0

        for row in range(self.collection_table.rowCount()):

            card = cards_by_id.get(self._row_card_id(row))

            text = ""
            if card:
                fields = [card.name, card.printing_label, card.type_line, card.rarity]
                text = " ".join(field for field in fields if field).lower()

            matches = all(word in text for word in words)
            self.collection_table.setRowHidden(row, not matches)
            visible += matches

        if words:
            self._set_collection_status(
                f"Showing {visible} of {plural(len(self.collection_cards), 'printing')}."
            )
        else:
            self._set_collection_status("")

    def _row_card_id(self, row):

        item = self.collection_table.item(row, COL_NAME)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def selected_cards(self):
        """
        Return the Cards of the selected rows, in table order.
        """

        cards_by_id = {card.id: card for card in self.collection_cards}
        rows = sorted(
            index.row() for index in self.collection_table.selectionModel().selectedRows()
        )

        return [
            cards_by_id[card_id]
            for card_id in (self._row_card_id(row) for row in rows)
            if card_id in cards_by_id
        ]

    def _update_selection_actions(self):

        selected = self.selected_cards()

        self.selection_label.setText(f"{len(selected)} selected" if selected else "")
        self.delete_button.setEnabled(bool(selected))
        # Changing the edition only makes sense for one card at a time
        self.change_edition_button.setEnabled(len(selected) == 1)

    def _show_collection_menu(self, position):

        row = self.collection_table.rowAt(position.y())
        if row < 0:
            return

        # Right-clicking a row that isn't selected selects only that row
        if not self.collection_table.selectionModel().isRowSelected(row):
            self.collection_table.selectRow(row)

        selected = self.selected_cards()

        menu = QMenu(self)

        change_action = menu.addAction("Change edition…")
        change_action.setEnabled(len(selected) == 1)
        change_action.triggered.connect(self.change_selected_edition)

        menu.addSeparator()

        delete_text = "Delete" if len(selected) == 1 else f"Delete {plural(len(selected), 'printing')}"
        delete_action = menu.addAction(delete_text)
        delete_action.triggered.connect(self.delete_selected_cards)

        menu.exec(self.collection_table.viewport().mapToGlobal(position))

    def _set_collection_status(self, text, state="info"):
        set_status(self.collection_status, text, state)

    # ==================================
    # COLLECTION: EDIT
    # ==================================

    def _on_quantity_changed(self, card_id, quantity):

        set_quantity(card_id, quantity)

        # Update the in-memory copy and the totals without redrawing the table
        for card in self.collection_cards:
            if card.id == card_id:
                card.quantity = quantity

        self._update_collection_summary()
        self._update_owned_label()

    def delete_selected_cards(self):

        cards = self.selected_cards()
        if not cards:
            return

        copies = sum(card.quantity or 0 for card in cards)
        copies_text = "1 copy" if copies == 1 else f"{copies} copies"

        if len(cards) == 1:
            what = f"{cards[0].name} ({cards[0].printing_label})"
        else:
            what = plural(len(cards), "printing")

        answer = QMessageBox.question(
            self,
            "Delete cards",
            f"Delete {what} from your collection?\n\n{copies_text} will be removed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        remove_cards([card.id for card in cards])
        self.show_collection()

        deleted = cards[0].name if len(cards) == 1 else plural(len(cards), "printing")
        self._set_collection_status(f"Deleted {deleted} ({copies_text}).", "success")

    def change_selected_edition(self):

        cards = self.selected_cards()
        if len(cards) != 1:
            return

        card = cards[0]

        dialog = EditionDialog(card, self.background, self)

        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.selected_card is None:
            return

        new_card = dialog.selected_card
        kept_id = change_card_printing(card.id, new_card)

        self.show_collection()

        if kept_id != card.id:
            self._set_collection_status(
                f"{card.name} moved to {new_card.printing_label} "
                "and merged with the copies you already had.",
                "success",
            )
        else:
            self._set_collection_status(
                f"{card.name} changed to {new_card.printing_label}.", "success"
            )

    # ==================================
    # SEARCH PAGE: "ALREADY IN YOUR COLLECTION"
    # ==================================

    def _update_owned_label(self):
        """
        Tell how many copies of the card shown on the search page are
        already in the collection (this edition and all editions).
        """

        card = self.current_card

        if card is None:
            self.owned_label.setText("")
            return

        name = (card.name or "").lower()
        same_name = [c for c in self.collection_cards if (c.name or "").lower() == name]

        total = sum(c.quantity or 0 for c in same_name)
        this_edition = sum(
            c.quantity or 0
            for c in same_name
            if card.scryfall_id and c.scryfall_id == card.scryfall_id
        )

        if total == 0:
            self.owned_label.setText("Not in your collection yet")
        else:
            self.owned_label.setText(
                f"In your collection: {this_edition} of this edition · {total} in total"
            )
