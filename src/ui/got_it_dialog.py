from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from services.card_service import get_printings
from services.collection_service import get_collections
from services.image_service import load_card_image, to_pixmap
from src.ui.widgets import printing_text, set_status

PREVIEW_WIDTH = 200
PREVIEW_HEIGHT = 279


class GotItDialog(QDialog):
    """
    "How many copies of Sol Ring did you get?": quantity (default = the
    missing copies) and edition (default = the deck's). After Accepted,
    selected_card and quantity say what to add to the collection.
    """

    def __init__(self, missing_card, background, parent=None, currency="EUR"):
        super().__init__(parent)

        self.missing_card = missing_card
        self.deck_card = missing_card.entry.card
        self.background = background
        self.currency = currency

        self.printings = [self.deck_card]
        self.selected_card = self.deck_card
        self._closed = False
        self._image_id = 0

        self.setWindowTitle("Got it")
        self.setModal(True)

        self.preview = QLabel("Loading image…")
        self.preview.setObjectName("cardImage")
        self.preview.setFixedSize(PREVIEW_WIDTH, PREVIEW_HEIGHT)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel(f"How many copies of {missing_card.name} did you get?")
        title.setObjectName("dialogTitle")
        title.setWordWrap(True)

        info = QLabel(
            f"The deck needs {missing_card.needed}, you have {missing_card.owned}: "
            f"{missing_card.missing} missing."
        )
        info.setObjectName("mutedLabel")
        info.setWordWrap(True)

        quantity_label = QLabel("COPIES")
        quantity_label.setObjectName("fieldLabel")

        self.quantity_input = QSpinBox()
        self.quantity_input.setRange(1, 999)
        self.quantity_input.setValue(missing_card.missing)
        self.quantity_input.setFixedWidth(100)

        self.foil_input = QCheckBox("Foil")
        self.foil_input.setToolTip("The copies you got are foil")

        quantity_row = QHBoxLayout()
        quantity_row.setSpacing(14)
        quantity_row.addWidget(self.quantity_input)
        quantity_row.addWidget(self.foil_input)
        quantity_row.addStretch()

        edition_label = QLabel("EDITION")
        edition_label.setObjectName("fieldLabel")

        self.edition_input = QComboBox()
        self.edition_input.setMaxVisibleItems(15)
        self.edition_input.addItem(printing_text(self.deck_card, currency))
        self.edition_input.currentIndexChanged.connect(self._on_edition_changed)

        self.status_label = QLabel("Loading other editions…")
        self.status_label.setObjectName("statusLabel")

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)

        add_button = QPushButton("Add to Collection")
        add_button.setObjectName("primaryButton")
        add_button.setDefault(True)
        add_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(add_button)

        details = QVBoxLayout()
        details.setSpacing(8)
        details.addWidget(title)
        details.addWidget(info)
        details.addSpacing(10)
        details.addWidget(quantity_label)
        details.addLayout(quantity_row)

        # Collection the bought copies go to (wishlists last: you own them now)
        collection_label = QLabel("ADD TO")
        collection_label.setObjectName("fieldLabel")

        self.collection_input = QComboBox()
        owned_first = sorted(get_collections(), key=lambda c: (c.kind == "wishlist", c.id))
        for collection in owned_first:
            star = " ★" if collection.kind == "wishlist" else ""
            self.collection_input.addItem(f"{collection.name}{star}", collection.id)

        details.addSpacing(6)
        details.addWidget(collection_label)
        details.addWidget(self.collection_input)
        details.addSpacing(6)
        details.addWidget(edition_label)
        details.addWidget(self.edition_input)
        details.addWidget(self.status_label)
        details.addStretch()
        details.addLayout(buttons)

        layout = QHBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(22)
        layout.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(details, 1)
        self.setLayout(layout)
        self.setMinimumWidth(680)

        self._load_image(self.deck_card)

        self.background.run(
            lambda: get_printings(self.deck_card),
            on_success=self._on_printings_loaded,
            on_error=lambda error: self._finish_loading(""),
        )

    @property
    def quantity(self):
        return self.quantity_input.value()

    @property
    def foil(self):
        return self.foil_input.isChecked()

    @property
    def collection_id(self):
        return self.collection_input.currentData()

    def _update_foil_input(self):
        """Disabled when the chosen edition has no foil; locked if only foil."""

        card = self.selected_card

        if card.only_foil:
            self.foil_input.setChecked(True)
            self.foil_input.setEnabled(False)
        elif not card.can_be_foil:
            self.foil_input.setChecked(False)
            self.foil_input.setEnabled(False)
        else:
            self.foil_input.setEnabled(True)

    def _on_printings_loaded(self, printings):

        if self._closed or not printings:
            return

        self.printings = printings

        self.edition_input.blockSignals(True)
        self.edition_input.clear()
        selected = 0
        for index, printing in enumerate(printings):
            self.edition_input.addItem(printing_text(printing, self.currency))
            if printing.scryfall_id == self.deck_card.scryfall_id:
                selected = index
        self.edition_input.setCurrentIndex(selected)
        self.edition_input.blockSignals(False)

        self.selected_card = printings[selected]
        self._update_foil_input()
        self._finish_loading(
            f"{len(printings)} edition{'s' if len(printings) != 1 else ''}: "
            "choose the one you got (default: the deck's)."
        )

    def _finish_loading(self, text):
        if not self._closed:
            set_status(self.status_label, text)

    def _on_edition_changed(self, index):

        if 0 <= index < len(self.printings):
            self.selected_card = self.printings[index]
            self._update_foil_input()
            self._load_image(self.selected_card)

    def _load_image(self, card):

        self._image_id += 1
        image_id = self._image_id

        self.background.run(
            lambda: load_card_image(card.image_url, width=PREVIEW_WIDTH, height=PREVIEW_HEIGHT),
            on_success=lambda image: self._on_image_loaded(image_id, image),
        )

    def _on_image_loaded(self, image_id, image):

        if self._closed or image_id != self._image_id:
            return

        if image is None:
            self.preview.setText("Image not available")
        else:
            self.preview.setPixmap(to_pixmap(image))

    def done(self, result):
        self._closed = True
        super().done(result)
