from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from services import deck_service as decks

# Value of the "new deck" option in the deck combo box
NEW_DECK = -1


def plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


class AddToDeckDialog(QDialog):
    """
    Choose where to add collection cards: an existing deck or a new one,
    the section and how many copies of each card.

    After Accepted: deck_id (None = create new_deck_name / new_deck_format),
    section and quantity.
    """

    def __init__(self, cards, parent=None, last_deck_id=None):
        super().__init__(parent)

        self.cards = cards

        self.setWindowTitle("Add to deck")
        self.setModal(True)
        self.setMinimumWidth(480)

        if len(cards) == 1:
            title_text = f"Add {cards[0].name} to a deck"
        else:
            title_text = f"Add {plural(len(cards), 'card')} to a deck"

        title = QLabel(title_text)
        title.setObjectName("dialogTitle")
        title.setWordWrap(True)

        hint = QLabel("The edition you have in your collection is used.")
        hint.setObjectName("mutedLabel")

        # ---------- Deck ----------

        deck_label = QLabel("DECK")
        deck_label.setObjectName("fieldLabel")

        self.deck_input = QComboBox()
        self.deck_list = decks.get_decks()

        for deck in self.deck_list:
            self.deck_input.addItem(
                f"{deck.name}  ·  {decks.format_label(deck.format)} "
                f"{deck.card_count}/{decks.deck_size(deck.format)}",
                deck.id,
            )
        self.deck_input.addItem("＋ New deck…", NEW_DECK)

        if last_deck_id is not None:
            index = self.deck_input.findData(last_deck_id)
            if index >= 0:
                self.deck_input.setCurrentIndex(index)

        self.deck_input.currentIndexChanged.connect(self._on_deck_changed)

        # New deck: name and format (only shown for "New deck…")
        self.new_name_input = QLineEdit()
        self.new_name_input.setPlaceholderText("Name of the new deck")
        self.new_name_input.textChanged.connect(self._update_button)

        self.new_format_input = QComboBox()
        for key, rules in decks.FORMATS.items():
            self.new_format_input.addItem(rules["label"], key)
        self.new_format_input.currentIndexChanged.connect(self._suggest_section)

        new_row = QHBoxLayout()
        new_row.setContentsMargins(0, 0, 0, 0)
        new_row.setSpacing(10)
        new_row.addWidget(self.new_name_input, 2)
        new_row.addWidget(self.new_format_input, 1)

        self.new_deck_box = QWidget()
        self.new_deck_box.setLayout(new_row)

        # ---------- Section and copies ----------

        section_label = QLabel("SECTION")
        section_label.setObjectName("fieldLabel")

        self.section_input = QComboBox()
        for section in decks.SECTIONS:
            self.section_input.addItem(decks.SECTION_LABELS[section], section)

        quantity_label = QLabel("COPIES OF EACH CARD")
        quantity_label.setObjectName("fieldLabel")

        self.quantity_input = QSpinBox()
        self.quantity_input.setRange(1, 99)
        self.quantity_input.setFixedWidth(90)

        section_box = QVBoxLayout()
        section_box.setSpacing(6)
        section_box.addWidget(section_label)
        section_box.addWidget(self.section_input)

        quantity_box = QVBoxLayout()
        quantity_box.setSpacing(6)
        quantity_box.addWidget(quantity_label)
        quantity_box.addWidget(self.quantity_input)

        options_row = QHBoxLayout()
        options_row.setSpacing(14)
        options_row.addLayout(section_box, 2)
        options_row.addLayout(quantity_box, 1)

        # ---------- Buttons ----------

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)

        self.add_button = QPushButton("Add to deck")
        self.add_button.setObjectName("primaryButton")
        self.add_button.setDefault(True)
        self.add_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(self.add_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(10)
        layout.addWidget(deck_label)
        layout.addWidget(self.deck_input)
        layout.addWidget(self.new_deck_box)
        layout.addSpacing(6)
        layout.addLayout(options_row)
        layout.addSpacing(14)
        layout.addLayout(buttons)
        self.setLayout(layout)

        self._on_deck_changed()

    # ==================================
    # RESULT
    # ==================================

    @property
    def deck_id(self):
        """The chosen deck's id, or None for a new deck."""
        data = self.deck_input.currentData()
        return None if data == NEW_DECK else data

    @property
    def new_deck_name(self):
        return self.new_name_input.text().strip()

    @property
    def new_deck_format(self):
        return self.new_format_input.currentData()

    @property
    def section(self):
        return self.section_input.currentData()

    @property
    def quantity(self):
        return self.quantity_input.value()

    # ==================================
    # BEHAVIOUR
    # ==================================

    def _chosen_format(self):

        if self.deck_id is None:
            return self.new_deck_format

        deck = next((d for d in self.deck_list if d.id == self.deck_id), None)
        return deck.format if deck else None

    def _on_deck_changed(self):

        is_new = self.deck_id is None
        self.new_deck_box.setVisible(is_new)

        if is_new and not self.new_name_input.text():
            # A single legendary creature is likely the commander: name the deck after it
            if len(self.cards) == 1:
                self.new_name_input.setText(self.cards[0].name)

        self._suggest_section()
        self._update_button()

    def _suggest_section(self):
        """
        Commander deck without a commander + one card that can be one:
        suggest the Commander section. Otherwise the main deck.
        """

        section = "main"

        if decks.is_commander_format(self._chosen_format() or "") and len(self.cards) == 1:
            if decks.can_be_commander(self.cards[0]):
                has_commander = False
                if self.deck_id is not None:
                    has_commander = any(
                        entry.section == "commander" for entry in decks.get_deck_cards(self.deck_id)
                    )
                if not has_commander:
                    section = "commander"

        self.section_input.setCurrentIndex(self.section_input.findData(section))

    def _update_button(self):
        self.add_button.setEnabled(self.deck_id is not None or bool(self.new_deck_name))
