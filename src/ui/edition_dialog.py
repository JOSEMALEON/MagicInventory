from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from services.card_service import get_printings
from services.image_service import load_card_image, to_pixmap
from src.ui.widgets import set_status

PREVIEW_WIDTH = 244
PREVIEW_HEIGHT = 340


class EditionDialog(QDialog):
    """
    Let the user pick another edition (printing) for a card of the collection.

    Usage:
        dialog = EditionDialog(card, background_runner, parent)
        if dialog.exec() == QDialog.Accepted:
            new_card = dialog.selected_card
    """

    def __init__(self, card, background, parent=None):
        super().__init__(parent)

        self.card = card
        self.background = background
        self.printings = []
        self.selected_card = None

        # Ignore answers that arrive after the dialog has been closed,
        # and images of an edition the user has already moved away from
        self._closed = False
        self._image_id = 0

        self.setWindowTitle("Change edition")
        self.setModal(True)

        # ---------- Preview ----------

        self.preview = QLabel("Loading image…")
        self.preview.setObjectName("cardImage")
        self.preview.setFixedSize(PREVIEW_WIDTH, PREVIEW_HEIGHT)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ---------- Details ----------

        name = QLabel(card.name)
        name.setObjectName("dialogTitle")
        name.setWordWrap(True)

        current = QLabel(f"Current: {card.printing_label} · {card.quantity} copies")
        current.setObjectName("mutedLabel")
        current.setWordWrap(True)

        edition_label = QLabel("NEW EDITION")
        edition_label.setObjectName("fieldLabel")

        self.edition_input = QComboBox()
        self.edition_input.addItem("Loading editions…")
        self.edition_input.setEnabled(False)
        self.edition_input.setMaxVisibleItems(15)
        self.edition_input.currentIndexChanged.connect(self._on_edition_changed)

        self.status_label = QLabel()
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("primaryButton")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel_button)
        buttons.addWidget(self.save_button)

        details = QVBoxLayout()
        details.setSpacing(8)
        details.addWidget(name)
        details.addWidget(current)
        details.addSpacing(16)
        details.addWidget(edition_label)
        details.addWidget(self.edition_input)
        details.addWidget(self.status_label)
        details.addStretch()
        details.addLayout(buttons)

        layout = QHBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)
        layout.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(details)

        self.setLayout(layout)
        self.setMinimumWidth(720)

        self._load_image(card)

        self.background.run(
            lambda: get_printings(card),
            on_success=self._on_printings_loaded,
            on_error=self._on_printings_error,
        )

    # ==================================
    # LOADING
    # ==================================

    def _on_printings_loaded(self, printings):

        if self._closed:
            return

        self.printings = printings

        self.edition_input.blockSignals(True)
        self.edition_input.clear()

        selected_index = 0

        for index, printing in enumerate(printings):
            self.edition_input.addItem(printing.printing_label)

            if self.card.scryfall_id and printing.scryfall_id == self.card.scryfall_id:
                selected_index = index

        self.edition_input.setCurrentIndex(selected_index)
        self.edition_input.blockSignals(False)
        self.edition_input.setEnabled(True)

        count = len(printings)
        set_status(self.status_label, f"{count} edition{'s' if count != 1 else ''} available.")

        self._on_edition_changed(selected_index)

    def _on_printings_error(self, error):

        if not self._closed:
            self.edition_input.setItemText(0, "Not available")
            set_status(
                self.status_label,
                "Could not load the editions. Check your connection and try again.",
                "error",
            )

    def _on_edition_changed(self, index):

        if not 0 <= index < len(self.printings):
            return

        printing = self.printings[index]
        self.selected_card = printing

        # Saving the same edition would do nothing
        same = bool(self.card.scryfall_id) and printing.scryfall_id == self.card.scryfall_id
        self.save_button.setEnabled(not same)

        self._load_image(printing)

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

    # ==================================
    # CLOSING
    # ==================================

    def done(self, result):

        self._closed = True
        super().done(result)
