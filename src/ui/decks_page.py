import re
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services import deck_service as decks
from services.card_service import ScryfallError, get_printings, is_basic_land, search_card
from services.image_service import art_crop_url, load_card_image, to_pixmap
from services.price_service import format_money
from services.bracket_service import estimate_bracket
from services.list_service import export_deck
from src.ui.edition_dialog import EditionDialog
from src.ui.import_deck_dialog import ImportDeckDialog
from src.ui.widgets import (
    QuantitySpinBox,
    format_mana_cost,
    mana_pixmap,
    printing_text,
    set_status,
    styled_panel,
)

# Deck tree columns
COL_QTY, COL_NAME, COL_MANA, COL_EDITION, COL_PRICE = range(5)

# Height of the mana symbols in the deck list
MANA_ICON_SIZE = 17


def _price_key(entry, currency, descending):
    """Cards without price always go last."""
    price = entry.card.price(currency)
    return (price is None, -(price or 0) if descending else (price or 0), entry.name.lower())


# Order of the cards inside each group: label -> key(entry, currency)
DECK_SORTS = {
    "Mana value ↑": lambda e, cur: (e.card.cmc or 0, e.name.lower()),
    "Mana value ↓": lambda e, cur: (-(e.card.cmc or 0), e.name.lower()),
    "Price ↑": lambda e, cur: _price_key(e, cur, descending=False),
    "Price ↓": lambda e, cur: _price_key(e, cur, descending=True),
    "Name (A–Z)": lambda e, cur: e.name.lower(),
}
DEFAULT_DECK_SORT = "Mana value ↑"

PREVIEW_WIDTH = 230
PREVIEW_HEIGHT = 320

# Mana colors for the deck selector, tuned for the dark background.
# Black uses a soft violet: a real black/grey would be invisible here.
MANA_COLORS = {
    "W": "#F4E4B0",
    "U": "#3B82F6",
    "B": "#A78BFA",
    "R": "#F87171",
    "G": "#4ADE80",
}
COLORLESS_COLOR = "#94A3B8"
DEFAULT_SELECTION_COLORS = ["#3B82F6", "#38BDF8"]   # theme blue (decks without commander)
WUBRG = "WUBRG"

ERROR_COLOR = "#F87171"
WARNING_COLOR = "#FBBF24"
OK_COLOR = "#4ADE80"


def plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


class DeckListCard(QWidget):
    """
    One deck in the deck list: name and "Format · 87/100 ✓/⚠" on the left,
    and the commander's illustration on the right, fading into the
    background so the text stays readable.
    """

    HEIGHT = 62
    ART_WIDTH_RATIO = 0.62   # part of the row covered by the illustration
    RADIUS = 8               # same as QListWidget#deckList::item

    def __init__(self):
        super().__init__()

        # Transparent: the list's hover/selection background shows through
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._art = None      # original illustration (QImage)
        self._faded = None    # illustration cropped to the row with the fade

        # Selection look: painted here so it can use the commander's colors
        self._selected = False
        self._colors = DEFAULT_SELECTION_COLORS
        self._has_deck_colors = False

        self.name_label = QLabel()
        self.name_label.setObjectName("deckCardName")

        self.info_label = QLabel()
        self.info_label.setObjectName("deckCardInfo")

        layout = QVBoxLayout()
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(2)
        layout.addWidget(self.name_label)
        layout.addWidget(self.info_label)
        self.setLayout(layout)

        self.setFixedHeight(self.HEIGHT)

    def set_texts(self, name, info):
        self.name_label.setText(name)
        self.info_label.setText(info)

    def set_art(self, image):
        self._art = image
        self._prepare_art()
        self.update()

    def set_selected(self, selected):
        if selected != self._selected:
            self._selected = selected
            self.update()

    def set_colors(self, colors):
        """
        Hex colors of the commander's identity (WUBRG order), or the theme
        blue when the deck has no commander.
        """
        self._colors = colors or DEFAULT_SELECTION_COLORS

        # Decks without commander art show their colors there instead
        self._has_deck_colors = bool(colors)
        self.update()

    def _paint_color_band(self, painter):
        """
        Where the commander's illustration would be: the deck's colors,
        fading into the background towards the left.
        """

        colors = [QColor(color) for color in self._colors]
        width = int(self.width() * self.ART_WIDTH_RATIO)
        left = self.width() - width

        band = QLinearGradient(left, 0, self.width(), 0)
        band.setColorAt(0.0, _with_alpha(colors[0], 0))

        last = len(colors) - 1
        for index, color in enumerate(colors):
            stop = 0.45 if last == 0 else 0.35 + 0.65 * index / last
            band.setColorAt(stop, _with_alpha(color, 70))

        band.setColorAt(1.0, _with_alpha(colors[-1], 95))
        painter.fillRect(left, 0, width, self.height(), band)

    def _paint_selection(self, painter):
        """
        Glow in the commander's colors fading to the right, plus an accent
        bar on the left (like the active sidebar button).
        """

        colors = [QColor(color) for color in self._colors]
        width = self.width()

        glow = QLinearGradient(0, 0, width, 0)
        last = len(colors) - 1

        for index, color in enumerate(colors):
            stop = 0.0 if last == 0 else 0.55 * index / last
            glow.setColorAt(stop, _with_alpha(color, 90))

        glow.setColorAt(1.0, _with_alpha(colors[-1], 8))
        painter.fillRect(self.rect(), glow)

        # Accent bar: the colors from top to bottom
        bar = QLinearGradient(0, 0, 0, self.height())
        for index, color in enumerate(colors):
            bar.setColorAt(0.0 if last == 0 else index / last, color)
        painter.fillRect(0, 0, 3, self.height(), bar)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._prepare_art()

    def _prepare_art(self):
        """
        Crop the illustration to the right part of the row and fade it to
        transparent towards the left (done once per size, not on every paint).
        """

        if self._art is None or self.width() <= 0:
            self._faded = None
            return

        width = max(1, int(self.width() * self.ART_WIDTH_RATIO))
        height = self.height()

        # Cover the area keeping the proportions, then take the middle
        scaled = self._art.scaled(
            width, height,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (scaled.width() - width) // 2
        y = (scaled.height() - height) // 3   # illustrations focus a bit above the middle
        faded = scaled.copy(x, y, width, height).convertToFormat(
            QImage.Format.Format_ARGB32_Premultiplied
        )

        # Keep only as much of each pixel as the gradient says (0 = invisible)
        fade = QLinearGradient(0, 0, width, 0)
        fade.setColorAt(0.0, QColor(0, 0, 0, 0))
        fade.setColorAt(0.45, QColor(0, 0, 0, 120))
        fade.setColorAt(1.0, QColor(0, 0, 0, 215))

        painter = QPainter(faded)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.fillRect(faded.rect(), fade)
        painter.end()

        self._faded = faded

    def paintEvent(self, event):

        color_band = self._faded is None and self._has_deck_colors

        if self._selected or self._faded is not None or color_band:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Rounded corners, like the list item under it
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(self.rect()), self.RADIUS, self.RADIUS)
            painter.setClipPath(clip)

            if self._selected:
                self._paint_selection(painter)

            if self._faded is not None:
                painter.drawImage(self.width() - self._faded.width(), 0, self._faded)
            elif color_band:
                self._paint_color_band(painter)

            painter.end()

        super().paintEvent(event)


def _with_alpha(color, alpha):
    result = QColor(color)
    result.setAlpha(alpha)
    return result


def deck_colors(entries):
    """
    Selector colors for decks without commander: the colors of the cards in
    the main deck and sideboard (a land that taps for red doesn't make the
    deck red). Only colorless cards -> grey; empty deck -> None (theme blue).
    """

    playing = [entry for entry in entries if entry.section in ("main", "sideboard")]

    if not playing:
        return None

    colors = set()
    for entry in playing:
        colors.update(_mana_colors(entry.card))

    return identity_colors(colors)


def _mana_colors(card):
    """
    Colors you need mana of to cast the card. Phyrexian symbols ({G/P}) can
    be paid with life, so they don't count: Mutagenic Growth doesn't make an
    Izzet deck green. Hybrid symbols ({W/U}) count both colors. Cards with
    no mana cost (Ancestral Vision...) keep their colors.
    """

    if not card.mana_cost:
        return set(card.colors or [])

    colors = set()

    for symbol in re.findall(r"\{([^}]+)\}", card.mana_cost):
        parts = symbol.split("/")
        if "P" in parts:
            continue
        colors.update(part for part in parts if part in WUBRG)

    return colors


def identity_colors(color_identity):
    """
    ["G", "W"] -> hex colors in WUBRG order: [white, green].
    An empty identity (colorless commander) -> grey.
    """

    letters = [letter for letter in WUBRG if letter in (color_identity or [])]

    if not letters:
        return [COLORLESS_COLOR]

    return [MANA_COLORS[letter] for letter in letters]


class NewDeckDialog(QDialog):
    """Ask for the name and format of a new deck."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("New deck")
        self.setModal(True)
        self.setMinimumWidth(420)

        title = QLabel("New deck")
        title.setObjectName("dialogTitle")

        name_label = QLabel("NAME")
        name_label.setObjectName("fieldLabel")

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Golbez artifacts")
        self.name_input.textChanged.connect(self._update_button)

        format_label = QLabel("FORMAT")
        format_label.setObjectName("fieldLabel")

        self.format_input = QComboBox()
        for key, rules in decks.FORMATS.items():
            self.format_input.addItem(rules["label"], key)

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)

        self.create_button = QPushButton("Create")
        self.create_button.setObjectName("primaryButton")
        self.create_button.setEnabled(False)
        self.create_button.setDefault(True)
        self.create_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(self.create_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addWidget(name_label)
        layout.addWidget(self.name_input)
        layout.addSpacing(6)
        layout.addWidget(format_label)
        layout.addWidget(self.format_input)
        layout.addSpacing(14)
        layout.addLayout(buttons)
        self.setLayout(layout)

    def _update_button(self):
        self.create_button.setEnabled(bool(self.name_input.text().strip()))

    @property
    def deck_name(self):
        return self.name_input.text().strip()

    @property
    def deck_format(self):
        return self.format_input.currentData()


class DecksPage(QWidget):
    """
    Deck builder: list of decks on the left, the open deck on the right
    (add cards, cards grouped by type, preview and format checks).
    """

    def __init__(self, background, get_currency, settings=None):
        super().__init__()

        self.background = background
        self.get_currency = get_currency

        # Remembers the chosen card order between sessions (QSettings)
        self.settings = settings

        self.deck = None          # open Deck
        self.entries = []         # its DeckCard lines
        self.issues = []          # its validation messages
        self.found_printings = [] # editions of the card being added

        # Commander illustrations for the deck list: {art url: QImage}
        self._deck_art = {}

        # Ignore answers that arrive after a newer request
        self._search_id = 0
        self._preview_id = 0

        columns = QHBoxLayout()
        columns.setSpacing(20)
        columns.addWidget(self._build_deck_list())

        self.right_stack = QStackedWidget()
        self.right_stack.addWidget(self._build_empty_state())
        self.right_stack.addWidget(self._build_deck_view())
        columns.addWidget(self.right_stack, 1)

        page_layout = QVBoxLayout()
        page_layout.setContentsMargins(32, 28, 32, 28)
        page_layout.setSpacing(14)

        title = QLabel("Decks")
        title.setObjectName("pageTitle")

        page_layout.addWidget(title)
        page_layout.addLayout(columns, 1)
        self.setLayout(page_layout)

        self.load_decks()

    # ==================================
    # LAYOUT
    # ==================================

    def _build_deck_list(self):

        caption = QLabel("MY DECKS")
        caption.setObjectName("fieldLabel")

        self.deck_list = QListWidget()
        self.deck_list.setObjectName("deckList")
        self.deck_list.currentItemChanged.connect(self._on_deck_selected)

        new_button = QPushButton("New deck")
        new_button.setObjectName("primaryButton")
        new_button.setCursor(Qt.CursorShape.PointingHandCursor)
        new_button.clicked.connect(self.new_deck)

        import_button = QPushButton("Import deck…")
        import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        import_button.setToolTip("Create a deck from a Moxfield / Archidekt / Arena list or a .txt/.csv file")
        import_button.clicked.connect(self.import_deck)

        self.rename_button = QPushButton("Rename")
        self.rename_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rename_button.clicked.connect(self.rename_deck)

        self.delete_deck_button = QPushButton("Delete")
        self.delete_deck_button.setObjectName("dangerButton")
        self.delete_deck_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_deck_button.clicked.connect(self.delete_deck)

        small_buttons = QHBoxLayout()
        small_buttons.setSpacing(8)
        small_buttons.addWidget(self.rename_button)
        small_buttons.addWidget(self.delete_deck_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(caption)
        layout.addWidget(self.deck_list, 1)
        layout.addWidget(new_button)
        layout.addWidget(import_button)
        layout.addLayout(small_buttons)

        panel = styled_panel("cardPanel", layout)
        panel.setFixedWidth(270)
        return panel

    def _build_empty_state(self):

        message = QLabel("Create your first deck with “New deck”.")
        message.setObjectName("mutedLabel")
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout()
        layout.addWidget(message)
        return styled_panel("cardPanel", layout)

    def _build_deck_view(self):

        # ---------- Header ----------

        self.deck_title = QLabel()
        self.deck_title.setObjectName("deckTitle")

        self.format_input = QComboBox()
        for key, rules in decks.FORMATS.items():
            self.format_input.addItem(rules["label"], key)
        self.format_input.currentIndexChanged.connect(self._on_format_changed)

        # "53 / 100 cards"
        self.count_label = QLabel()
        self.count_label.setObjectName("deckCount")

        # "✓ Legal" / "⚠ 6 problems"
        self.validity_label = QLabel()
        self.validity_label.setObjectName("validityBadge")

        self.deck_value_label = QLabel()
        self.deck_value_label.setObjectName("mutedLabel")

        # "Bracket 3 · Upgraded" (Commander decks only)
        self.bracket_label = QLabel()
        self.bracket_label.setObjectName("bracketBadge")

        export_button = QPushButton("Export…")
        export_button.setCursor(Qt.CursorShape.PointingHandCursor)
        export_button.setToolTip("Save this deck as a text list (Moxfield / Arena format)")
        export_button.clicked.connect(self.export_deck)

        header = QHBoxLayout()
        header.setSpacing(14)
        header.addWidget(self.deck_title)
        header.addWidget(self.format_input)
        header.addWidget(export_button)
        header.addStretch()
        header.addWidget(self.deck_value_label)
        header.addWidget(self.bracket_label)
        header.addWidget(self.count_label)
        header.addWidget(self.validity_label)

        # ---------- Add a card ----------

        self.add_input = QLineEdit()
        self.add_input.setPlaceholderText("Add a card by name…")
        self.add_input.returnPressed.connect(self.search_card_to_add)

        find_button = QPushButton("Find")
        find_button.setCursor(Qt.CursorShape.PointingHandCursor)
        find_button.clicked.connect(self.search_card_to_add)

        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        search_row.addWidget(self.add_input, 1)
        search_row.addWidget(find_button)

        # Shown once a card is found
        self.found_name = QLabel()
        self.found_name.setObjectName("foundName")

        self.found_edition = QComboBox()
        self.found_edition.setMaxVisibleItems(15)
        self.found_edition.setMinimumWidth(320)

        self.found_quantity = QSpinBox()
        self.found_quantity.setRange(1, 99)
        self.found_quantity.setFixedWidth(80)

        self.found_section = QComboBox()
        for section in decks.SECTIONS:
            self.found_section.addItem(decks.SECTION_LABELS[section], section)

        add_button = QPushButton("Add to deck")
        add_button.setObjectName("primaryButton")
        add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        add_button.clicked.connect(self.add_found_card)

        found_row = QHBoxLayout()
        found_row.setSpacing(10)
        found_row.addWidget(self.found_name)
        found_row.addWidget(self.found_edition, 1)
        found_row.addWidget(self.found_quantity)
        found_row.addWidget(self.found_section)
        found_row.addWidget(add_button)

        self.found_box = QWidget()
        self.found_box.setLayout(found_row)
        self.found_box.hide()

        self.status_label = QLabel()
        self.status_label.setObjectName("statusLabel")

        add_layout = QVBoxLayout()
        add_layout.setContentsMargins(16, 14, 16, 14)
        add_layout.setSpacing(8)
        add_layout.addLayout(search_row)
        add_layout.addWidget(self.found_box)
        add_layout.addWidget(self.status_label)

        add_panel = styled_panel("cardPanel", add_layout)

        # ---------- Cards grouped by type ----------

        tree = QTreeWidget()
        self.tree = tree
        tree.setObjectName("deckTree")
        tree.setColumnCount(5)
        tree.setHeaderLabels(["Qty", "Name", "Mana", "Edition", "Price"])
        tree.setRootIsDecorated(False)
        tree.setIndentation(0)
        tree.setUniformRowHeights(True)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._show_card_menu)
        tree.currentItemChanged.connect(self._on_card_selected)
        tree.itemDoubleClicked.connect(lambda item, column: self.change_edition())

        tree_header = tree.header()
        tree_header.setStretchLastSection(False)
        tree_header.setSectionResizeMode(COL_QTY, QHeaderView.ResizeMode.Fixed)
        tree_header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        tree_header.setSectionResizeMode(COL_MANA, QHeaderView.ResizeMode.Fixed)
        # The name gets all the free space; full type/edition are in the tooltip
        tree_header.setSectionResizeMode(COL_EDITION, QHeaderView.ResizeMode.Interactive)
        tree_header.setSectionResizeMode(COL_PRICE, QHeaderView.ResizeMode.Fixed)
        tree.setColumnWidth(COL_QTY, 90)
        tree.setColumnWidth(COL_MANA, 130)
        tree.setColumnWidth(COL_EDITION, 150)
        tree.setColumnWidth(COL_PRICE, 75)

        delete_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Delete), tree)
        delete_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        delete_shortcut.activated.connect(self.remove_selected_cards)

        # ---------- Side panel: preview + checks ----------

        self.preview = QLabel("Select a card")
        self.preview.setObjectName("cardImage")
        self.preview.setFixedSize(PREVIEW_WIDTH, PREVIEW_HEIGHT)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)

        checks_caption = QLabel("FORMAT CHECKS")
        checks_caption.setObjectName("fieldLabel")

        self.issue_list = QListWidget()
        self.issue_list.setObjectName("issueList")
        self.issue_list.setWordWrap(True)
        self.issue_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.issue_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        side = QVBoxLayout()
        side.setContentsMargins(16, 16, 16, 16)
        side.setSpacing(10)
        side.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignHCenter)
        side.addWidget(checks_caption)
        side.addWidget(self.issue_list, 1)

        # Why the deck is in its bracket (Commander decks only)
        self.bracket_caption = QLabel("BRACKET")
        self.bracket_caption.setObjectName("fieldLabel")

        self.bracket_details = QLabel()
        self.bracket_details.setObjectName("bracketDetails")
        self.bracket_details.setWordWrap(True)
        self.bracket_details.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        side.addWidget(self.bracket_caption)
        side.addWidget(self.bracket_details)

        side_panel = styled_panel("cardPanel", side)
        side_panel.setFixedWidth(PREVIEW_WIDTH + 32)

        # ---------- Card order ----------

        sort_label = QLabel("Sort by")
        sort_label.setObjectName("mutedLabel")

        self.sort_input = QComboBox()
        self.sort_input.addItems(list(DECK_SORTS))

        saved_sort = self.settings.value("deck_sort", DEFAULT_DECK_SORT) if self.settings else DEFAULT_DECK_SORT
        if saved_sort in DECK_SORTS:
            self.sort_input.setCurrentText(saved_sort)

        self.sort_input.currentTextChanged.connect(self._on_sort_changed)

        grouped_label = QLabel("Cards grouped by type")
        grouped_label.setObjectName("mutedLabel")

        sort_row = QHBoxLayout()
        sort_row.setSpacing(10)
        sort_row.addWidget(grouped_label)
        sort_row.addStretch()
        sort_row.addWidget(sort_label)
        sort_row.addWidget(self.sort_input)

        tree_column = QVBoxLayout()
        tree_column.setSpacing(8)
        tree_column.addLayout(sort_row)
        tree_column.addWidget(tree, 1)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addLayout(tree_column, 1)
        body.addWidget(side_panel)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addLayout(header)
        layout.addWidget(add_panel)
        layout.addLayout(body, 1)

        view = QWidget()
        view.setLayout(layout)
        return view

    # ==================================
    # DECK LIST
    # ==================================

    def load_decks(self, select_id=None):
        """
        Reload the deck list and open select_id (or keep the open deck).
        """

        if select_id is None and self.deck is not None:
            select_id = self.deck.id

        self.deck_list.blockSignals(True)
        self.deck_list.clear()

        selected_row = 0

        for row, deck in enumerate(decks.get_decks()):

            entries = decks.get_deck_cards(deck.id)
            issues = decks.validate_deck(deck.format, entries)

            # The item only holds the deck id; DeckListCard draws its content
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, deck.id)
            item.setSizeHint(QSize(0, DeckListCard.HEIGHT))
            self.deck_list.addItem(item)

            card_widget = DeckListCard()
            self.deck_list.setItemWidget(item, card_widget)
            self._fill_deck_item(item, deck, entries, issues)

            if deck.id == select_id:
                selected_row = row

        self.deck_list.blockSignals(False)

        has_decks = self.deck_list.count() > 0
        self.rename_button.setEnabled(has_decks)
        self.delete_deck_button.setEnabled(has_decks)

        if has_decks:
            # The list was cleared, so this always emits currentItemChanged,
            # which opens the deck (_on_deck_selected)
            self.deck_list.setCurrentRow(selected_row)
        else:
            self.deck = None
            self.right_stack.setCurrentIndex(0)

    def _on_deck_selected(self, current, previous):

        # The selection glow is painted by each DeckListCard
        for row in range(self.deck_list.count()):
            item = self.deck_list.item(row)
            card_widget = self.deck_list.itemWidget(item)
            if card_widget is not None:
                card_widget.set_selected(item is current)

        if current is not None:
            self._open_deck(current.data(Qt.ItemDataRole.UserRole))

    def _update_deck_list_item(self):
        """Refresh the open deck in the list (count, ✓/⚠ and commander art)."""

        item = self.deck_list.currentItem()
        if item is None or self.deck is None:
            return

        self._fill_deck_item(item, self.deck, self.entries, self.issues)

    def _fill_deck_item(self, item, deck, entries, issues):
        """
        Texts, tooltip and commander illustration of one deck in the list.
        """

        card_widget = self.deck_list.itemWidget(item)
        if card_widget is None:
            return

        count = sum(e.quantity for e in entries if e.section in ("commander", "main"))
        errors = sum(issue.level == "error" for issue in issues)
        mark = "✓" if not errors else "⚠"

        card_widget.set_texts(
            deck.name,
            f"{decks.format_label(deck.format)} · {count}/{decks.deck_size(deck.format)}  {mark}",
        )
        item.setToolTip("Legal" if not errors else plural(errors, "problem"))

        # Selection colors: the commanders' color identity (partners add theirs)
        commanders = [e.card for e in entries if e.section == "commander"]

        if commanders:
            identity = set()
            for commander_card in commanders:
                identity.update(commander_card.color_identity)
            card_widget.set_colors(identity_colors(identity))
        else:
            card_widget.set_colors(deck_colors(entries))

        card_widget.set_selected(item is self.deck_list.currentItem())

        # Illustration of the (first) commander; nothing for decks without one
        commander = commanders[0] if commanders else None
        url = art_crop_url(commander.image_url) if commander else None

        if url == getattr(card_widget, "art_url", None):
            return

        card_widget.art_url = url

        if url is None:
            card_widget.set_art(None)
        elif url in self._deck_art:
            card_widget.set_art(self._deck_art[url])
        else:
            self.background.run(
                lambda: load_card_image(url, width=420, rounded=False),
                on_success=lambda image: self._on_deck_art_loaded(url, image),
            )

    def _on_deck_art_loaded(self, url, image):

        if image is None:
            return

        self._deck_art[url] = image

        # The list may have been redrawn meanwhile: find every row using this art
        for row in range(self.deck_list.count()):
            card_widget = self.deck_list.itemWidget(self.deck_list.item(row))
            if card_widget is not None and getattr(card_widget, "art_url", None) == url:
                card_widget.set_art(image)

    def new_deck(self):

        dialog = NewDeckDialog(self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        deck_id = decks.create_deck(dialog.deck_name, dialog.deck_format)
        self.load_decks(select_id=deck_id)
        set_status(self.status_label, f"Deck “{dialog.deck_name}” created. Add cards with the search bar.")
        self.add_input.setFocus()

    def import_deck(self):

        dialog = ImportDeckDialog(self.background, self)

        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.created_deck_id is None:
            return

        self.load_decks(select_id=dialog.created_deck_id)

        count = self._main_count()
        set_status(
            self.status_label,
            f"Deck “{self.deck.name}” imported with {plural(count, 'card')}.",
            "success",
        )

    def export_deck(self):

        if self.deck is None:
            return

        safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in self.deck.name).strip()
        suggested = str(Path.home() / "Documents" / f"{safe_name or 'deck'}.txt")

        path, _ = QFileDialog.getSaveFileName(
            self, "Export deck", suggested, "Text list (*.txt)"
        )

        if not path:
            return

        path = Path(path)
        if path.suffix.lower() != ".txt":
            path = path.with_suffix(".txt")

        try:
            export_deck(path, self.deck.name, self.entries)
        except OSError as error:
            set_status(self.status_label, f"Could not save the file: {error}", "error")
            return

        set_status(self.status_label, f"Deck exported to {path}.", "success")

    def rename_deck(self):

        if self.deck is None:
            return

        name, ok = QInputDialog.getText(self, "Rename deck", "New name:", text=self.deck.name)

        if ok and name.strip():
            decks.rename_deck(self.deck.id, name)
            self.load_decks()

    def delete_deck(self):

        if self.deck is None:
            return

        answer = QMessageBox.question(
            self,
            "Delete deck",
            f"Delete the deck “{self.deck.name}”?\n\n"
            "Its card list will be lost. Your collection doesn't change.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )

        if answer == QMessageBox.StandardButton.Yes:
            decks.delete_deck(self.deck.id)
            self.deck = None
            self.load_decks()

    # ==================================
    # OPEN DECK
    # ==================================

    def _open_deck(self, deck_id):

        changed_deck = self.deck is None or self.deck.id != deck_id
        self.deck = decks.get_deck(deck_id)

        if self.deck is None:
            return

        self.right_stack.setCurrentIndex(1)
        self.deck_title.setText(self.deck.name)

        self.format_input.blockSignals(True)
        self.format_input.setCurrentIndex(self.format_input.findData(self.deck.format))
        self.format_input.blockSignals(False)

        if changed_deck:
            self._clear_found()
            set_status(self.status_label, "")
            self.tree.clearSelection()

        self.refresh_deck()

        if changed_deck:
            self._show_default_preview()

    def refresh_deck(self):
        """
        Reload the open deck's cards and redraw everything (tree, header, checks).
        """

        if self.deck is None:
            return

        self.entries = decks.get_deck_cards(self.deck.id)
        self.issues = decks.validate_deck(self.deck.format, self.entries)

        self._fill_tree()
        self._update_header()
        self._fill_issues()
        self._update_deck_list_item()

    def _main_count(self):
        return sum(entry.quantity for entry in self.entries if entry.section in ("commander", "main"))

    def _update_header(self):

        currency = self.get_currency()
        count = self._main_count()
        size = decks.deck_size(self.deck.format)

        self.count_label.setText(f"{count} / {size} cards")

        errors = [issue for issue in self.issues if issue.level == "error"]

        if errors:
            set_status(self.validity_label, f"⚠ {plural(len(errors), 'problem')}", "error")
        else:
            set_status(self.validity_label, "✓ Legal", "success")

        playing = [e for e in self.entries if e.section in ("commander", "main")]
        value = sum(e.card.value(currency) or 0 for e in playing)
        self.deck_value_label.setText(f"Value {format_money(value, currency)}")

        self._update_bracket()

    def _update_bracket(self):
        """
        Commander Bracket estimate next to the deck value, with the reasons
        in the side panel. Hidden for 60-card formats.
        """

        is_commander = decks.is_commander_format(self.deck.format)

        for widget in (self.bracket_label, self.bracket_caption, self.bracket_details):
            widget.setVisible(is_commander)

        if not is_commander:
            return

        estimate = estimate_bracket(self.entries)

        if estimate is None:
            # The Game Changers list is still downloading
            self.bracket_label.setText("Bracket …")
            self.bracket_label.setProperty("bracket", "")
            self.bracket_label.setToolTip("Downloading the Game Changers list…")
            self.bracket_details.setText("Downloading the Game Changers list…")
        else:
            self.bracket_label.setText(estimate.label)
            self.bracket_label.setProperty("bracket", str(estimate.bracket))
            details = "\n".join(f"• {reason}" for reason in estimate.reasons)
            self.bracket_label.setToolTip(details)
            self.bracket_details.setText(details)

        # Re-apply the stylesheet: the color depends on the "bracket" property
        self.bracket_label.style().unpolish(self.bracket_label)
        self.bracket_label.style().polish(self.bracket_label)

    def _on_sort_changed(self, text):

        if self.settings is not None:
            self.settings.setValue("deck_sort", text)

        self._fill_tree()

    def _fill_issues(self):

        self.issue_list.clear()

        if not self.issues:
            item = QListWidgetItem(f"✓ The deck is legal in {decks.format_label(self.deck.format)}.")
            item.setForeground(QColor(OK_COLOR))
            self.issue_list.addItem(item)
            return

        for issue in self.issues:
            symbol = "✗" if issue.level == "error" else "⚠"
            item = QListWidgetItem(f"{symbol} {issue.message}")
            item.setForeground(QColor(ERROR_COLOR if issue.level == "error" else WARNING_COLOR))
            self.issue_list.addItem(item)

    def _fill_tree(self):

        currency = self.get_currency()
        tree = self.tree

        # Remember the current and selected lines to restore them after
        # redrawing (the current one must not replace the selection)
        current = tree.currentItem()
        current_id = current.data(COL_NAME, Qt.ItemDataRole.UserRole) if current else None
        selected_ids = {
            item.data(COL_NAME, Qt.ItemDataRole.UserRole) for item in tree.selectedItems()
        }

        tree.clear()

        if not self.entries:
            placeholder = QTreeWidgetItem(["This deck is empty: add cards with the search bar above."])
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            tree.addTopLevelItem(placeholder)
            placeholder.setFirstColumnSpanned(True)
            return

        group_font = QFont()
        group_font.setBold(True)

        for title, entries in decks.group_deck_cards(self.entries):

            copies = sum(entry.quantity for entry in entries)
            # The group title uses the whole row (first column spanned)
            group = QTreeWidgetItem([f"{title}  ({copies})"])
            group.setFlags(Qt.ItemFlag.ItemIsEnabled)
            group.setFont(0, group_font)
            tree.addTopLevelItem(group)
            group.setFirstColumnSpanned(True)

            sort_key = DECK_SORTS.get(self.sort_input.currentText(), DECK_SORTS[DEFAULT_DECK_SORT])

            for entry in sorted(entries, key=lambda e: sort_key(e, currency)):
                card = entry.card

                item = QTreeWidgetItem([
                    "",
                    card.name,
                    format_mana_cost(card.mana_cost, empty=""),
                    card.printing_label,
                    format_money(card.price(currency), currency),
                ])
                item.setData(COL_NAME, Qt.ItemDataRole.UserRole, entry.id)
                item.setToolTip(COL_NAME, f"{card.name}\n{card.type_line or ''}")
                item.setToolTip(COL_EDITION, card.printing_label)
                item.setTextAlignment(COL_PRICE, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                group.addChild(item)

                tree.setItemWidget(item, COL_QTY, self._quantity_cell(entry))

                # Mana symbols instead of "2 W U" when they are downloaded
                symbols = mana_pixmap(card.mana_cost, height=MANA_ICON_SIZE)
                if symbols is not None:
                    item.setText(COL_MANA, "")
                    item.setToolTip(COL_MANA, format_mana_cost(card.mana_cost, empty=""))
                    tree.setItemWidget(item, COL_MANA, self._mana_cell(symbols))

                if entry.id == current_id:
                    tree.setCurrentItem(item, COL_NAME, QItemSelectionModel.SelectionFlag.NoUpdate)

                if entry.id in selected_ids:
                    item.setSelected(True)

            group.setExpanded(True)

    def _mana_cell(self, pixmap):

        label = QLabel()
        label.setPixmap(pixmap)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        # Let clicks reach the row (select / context menu / double click)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        label.setContentsMargins(4, 0, 0, 0)
        return label

    def _quantity_cell(self, entry):

        spin = QuantitySpinBox(entry.quantity)
        spin.setRange(1, 999)
        spin.setFixedWidth(70)
        spin.valueChanged.connect(
            lambda value, line_id=entry.id: self._on_quantity_changed(line_id, value)
        )

        layout = QHBoxLayout()
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addWidget(spin)

        cell = QWidget()
        cell.setLayout(layout)
        return cell

    def _on_quantity_changed(self, line_id, quantity):

        decks.set_deck_card_quantity(line_id, quantity)

        # Update counts and checks without rebuilding the tree (keeps focus)
        for entry in self.entries:
            if entry.id == line_id:
                entry.card.quantity = quantity

        self.issues = decks.validate_deck(self.deck.format, self.entries)
        self._update_header()
        self._fill_issues()
        self._update_group_titles()
        self._update_deck_list_item()

    def _update_group_titles(self):

        entries_by_id = {entry.id: entry for entry in self.entries}

        for index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(index)
            copies = 0
            for child_index in range(group.childCount()):
                line_id = group.child(child_index).data(COL_NAME, Qt.ItemDataRole.UserRole)
                if line_id in entries_by_id:
                    copies += entries_by_id[line_id].quantity

            title = group.text(0).rsplit("  (", 1)[0]
            if group.childCount():
                group.setText(0, f"{title}  ({copies})")

    def _on_format_changed(self):

        if self.deck is None:
            return

        deck_format = self.format_input.currentData()
        decks.set_deck_format(self.deck.id, deck_format)
        self.deck.format = deck_format
        self.refresh_deck()

    # ==================================
    # SELECTED CARDS
    # ==================================

    def selected_entries(self):

        entries_by_id = {entry.id: entry for entry in self.entries}
        selected = []

        for item in self.tree.selectedItems():
            line_id = item.data(COL_NAME, Qt.ItemDataRole.UserRole)
            if line_id in entries_by_id:
                selected.append(entries_by_id[line_id])

        return selected

    def _on_card_selected(self, current, previous):

        if current is None:
            return

        line_id = current.data(COL_NAME, Qt.ItemDataRole.UserRole)
        entry = next((e for e in self.entries if e.id == line_id), None)

        if entry is not None:
            self._show_preview(entry)

    def _show_default_preview(self):
        """
        When a deck is opened: show its commander (Commander decks) or the
        first card of the list (other formats). The row is not selected, so
        pressing Delete can't remove it by accident.
        """

        commander = next((e for e in self.entries if e.section == "commander"), None)

        if commander is not None:
            self._show_preview(commander)
            return

        # First card as shown in the tree (groups and chosen order)
        for index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(index)
            if group.childCount():
                line_id = group.child(0).data(COL_NAME, Qt.ItemDataRole.UserRole)
                entry = next((e for e in self.entries if e.id == line_id), None)
                if entry is not None:
                    self._show_preview(entry)
                    return

        self._clear_preview()

    def _clear_preview(self):

        # Discard any image still loading (it belongs to another deck/card)
        self._preview_id += 1
        self.preview.clear()
        self.preview.setText("Select a card")

    def _preview_is_empty(self):
        pixmap = self.preview.pixmap()
        return pixmap is None or pixmap.isNull()

    def _show_preview(self, entry):

        self._preview_id += 1
        preview_id = self._preview_id
        url = entry.card.image_url

        self.background.run(
            lambda: load_card_image(url, width=PREVIEW_WIDTH, height=PREVIEW_HEIGHT),
            on_success=lambda image: self._on_preview_loaded(preview_id, image),
        )

    def _on_preview_loaded(self, preview_id, image):

        if preview_id != self._preview_id:
            return

        if image is None:
            self.preview.setText("Image not available")
        else:
            self.preview.setPixmap(to_pixmap(image))

    def _show_card_menu(self, position):

        item = self.tree.itemAt(position)
        if item is None or item.data(COL_NAME, Qt.ItemDataRole.UserRole) is None:
            return

        if not item.isSelected():
            self.tree.clearSelection()
            item.setSelected(True)
            self.tree.setCurrentItem(item)

        selected = self.selected_entries()
        menu = QMenu(self)

        move_menu = menu.addMenu("Move to")
        for section in decks.SECTIONS:
            action = move_menu.addAction(decks.SECTION_LABELS[section])
            action.setEnabled(any(entry.section != section for entry in selected))
            action.triggered.connect(lambda checked=False, s=section: self.move_selected(s))

        change_action = menu.addAction("Change edition…")
        change_action.setEnabled(len(selected) == 1)
        change_action.triggered.connect(self.change_edition)

        menu.addSeparator()

        remove_text = "Remove from deck" if len(selected) == 1 else f"Remove {len(selected)} cards from deck"
        remove_action = menu.addAction(remove_text)
        remove_action.triggered.connect(self.remove_selected_cards)

        menu.exec(self.tree.viewport().mapToGlobal(position))

    def move_selected(self, section):

        selected = self.selected_entries()

        for entry in selected:
            if entry.section != section:
                decks.move_deck_card(entry.id, section)

        self.refresh_deck()
        set_status(
            self.status_label,
            f"Moved {plural(len(selected), 'card')} to {decks.SECTION_LABELS[section]}.",
            "success",
        )

    def remove_selected_cards(self):

        selected = self.selected_entries()
        if not selected:
            return

        decks.remove_deck_cards([entry.id for entry in selected])
        self.refresh_deck()

        names = selected[0].name if len(selected) == 1 else plural(len(selected), "card")
        set_status(self.status_label, f"Removed {names} from the deck.", "success")

    def change_edition(self):

        selected = self.selected_entries()
        if len(selected) != 1:
            return

        entry = selected[0]
        dialog = EditionDialog(entry.card, self.background, self, currency=self.get_currency())

        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.selected_card is None:
            return

        decks.change_deck_card_printing(entry.id, dialog.selected_card)
        self.refresh_deck()
        set_status(
            self.status_label,
            f"{entry.name} changed to {dialog.selected_card.printing_label}.",
            "success",
        )

    # ==================================
    # ADD CARDS
    # ==================================

    def search_card_to_add(self):

        name = self.add_input.text().strip()

        if not name or self.deck is None:
            return

        self._search_id += 1
        search_id = self._search_id

        self._clear_found()
        set_status(self.status_label, f"Searching “{name}”…")

        self.background.run(
            lambda: search_card(name),
            on_success=lambda card: self._on_card_found(search_id, card),
            on_error=lambda error: self._on_search_error(search_id, error),
        )

    def _on_card_found(self, search_id, card):

        if search_id != self._search_id:
            return

        if card is None:
            set_status(self.status_label, "Card not found. Check the spelling and try again.", "error")
            return

        set_status(self.status_label, "Loading editions…")

        self.found_printings = [card]
        self._fill_found(card)

        self.background.run(
            lambda: get_printings(card),
            on_success=lambda printings: self._on_printings_loaded(search_id, card, printings),
            on_error=lambda error: set_status(self.status_label, ""),
        )

    def _on_search_error(self, search_id, error):

        if search_id != self._search_id:
            return

        if isinstance(error, ScryfallError):
            set_status(self.status_label, "Could not connect to Scryfall.", "error")
        else:
            set_status(self.status_label, f"Unexpected error: {error}", "error")

    def _on_printings_loaded(self, search_id, card, printings):

        if search_id != self._search_id:
            return

        self.found_printings = printings

        if is_basic_land(card) and printings:
            # Basic lands: use the newest printing (only the newest page was loaded)
            self._fill_found(printings[0], reset=False)
            set_status(
                self.status_label,
                f"Basic land: newest edition selected ({plural(len(printings), 'recent edition')} available).",
            )
        else:
            self._fill_found(card, reset=False)
            set_status(self.status_label, f"{plural(len(printings), 'edition')} available.")

    def _fill_found(self, card, reset=True):
        """
        Show the found card with its editions. reset=False keeps the quantity
        and section the user may have chosen while the editions were loading.
        """

        currency = self.get_currency()

        self.found_name.setText(card.name)

        self.found_edition.clear()
        selected = 0
        for index, printing in enumerate(self.found_printings):
            self.found_edition.addItem(printing_text(printing, currency))
            if printing.scryfall_id == card.scryfall_id:
                selected = index
        self.found_edition.setCurrentIndex(selected)

        if not reset:
            return

        # A commander deck without a commander: suggest the Commander section
        has_commander = any(entry.section == "commander" for entry in self.entries)
        if decks.is_commander_format(self.deck.format) and not has_commander and decks.can_be_commander(card):
            section = "commander"
        else:
            section = "main"
        self.found_section.setCurrentIndex(self.found_section.findData(section))

        self.found_quantity.setValue(1)
        self.found_box.show()

    def _clear_found(self):

        self.found_printings = []
        self.found_box.hide()

    def add_found_card(self):

        index = self.found_edition.currentIndex()
        if self.deck is None or not 0 <= index < len(self.found_printings):
            return

        card = self.found_printings[index]
        quantity = self.found_quantity.value()
        section = self.found_section.currentData()

        decks.add_card_to_deck(self.deck.id, card, quantity, section)

        self._clear_found()
        self.add_input.clear()
        self.add_input.setFocus()
        self.refresh_deck()

        # First card of an empty deck, or a new commander: show it
        if self._preview_is_empty() or section == "commander":
            self._show_default_preview()

        set_status(
            self.status_label,
            f"Added {quantity} × {card.name} to {decks.SECTION_LABELS[section]}.",
            "success",
        )
