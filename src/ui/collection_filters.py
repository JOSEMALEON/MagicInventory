"""
Field filters for the collection table: rarity, color, card type, edition,
foil, price range and minimum quantity. They are combined with the text
filter. The collection doesn't store card colors, so they come from the
mana cost (lands and most artifacts count as colorless).
"""

import re

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.config import RARITY_COLORS

RARITIES = ("common", "uncommon", "rare", "mythic")

COLOR_CHIPS = [
    ("W", "White"), ("U", "Blue"), ("B", "Black"), ("R", "Red"), ("G", "Green"),
    ("C", "Colorless"), ("M", "Multicolor"),
]

# Same mana colors as the deck pages
CHIP_COLORS = {
    "W": "#F4E4B0", "U": "#3B82F6", "B": "#A78BFA", "R": "#F87171", "G": "#4ADE80",
    "C": "#94A3B8", "M": "#FBBF24",
}

CARD_TYPES = [
    "Creature", "Instant", "Sorcery", "Artifact", "Enchantment",
    "Planeswalker", "Land", "Battle", "Legendary",
]

ANY = "Any"


def card_colors(card):
    """
    Colors of a collection card from its mana cost ({2}{W}{U} -> {"W", "U"}).
    Hybrid symbols count both colors; Phyrexian ones count too (the card is
    still that color).
    """

    colors = set()
    for symbol in re.findall(r"\{([^}]+)\}", card.mana_cost or ""):
        colors.update(part for part in symbol.split("/") if part in "WUBRG")
    return colors


class CollectionFilters(QWidget):
    """
    Panel with the field filters. `changed` is emitted on every change;
    matches(card, currency) tells if a card passes them.
    """

    changed = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("filterPanel")

        # ---------- Rarity and color chips ----------

        self.rarity_chips = {}
        rarity_row = QHBoxLayout()
        rarity_row.setSpacing(6)
        rarity_row.addWidget(self._caption("RARITY"))
        for rarity in RARITIES:
            chip = self._chip(rarity.capitalize(), RARITY_COLORS[rarity])
            self.rarity_chips[rarity] = chip
            rarity_row.addWidget(chip)
        rarity_row.addSpacing(18)

        rarity_row.addWidget(self._caption("COLOR"))
        self.color_chips = {}
        for key, label in COLOR_CHIPS:
            chip = self._chip(label, CHIP_COLORS[key])
            chip.setToolTip({
                "C": "No colored mana in its cost (lands, most artifacts)",
                "M": "Two or more colors",
            }.get(key, f"{label} cards (from the mana cost)"))
            self.color_chips[key] = chip
            rarity_row.addWidget(chip)
        rarity_row.addStretch()

        # ---------- Type, edition, foil, price, quantity ----------

        self.type_input = QComboBox()
        self.type_input.addItem(ANY)
        self.type_input.addItems(CARD_TYPES)
        self.type_input.currentIndexChanged.connect(self.changed)

        self.set_input = QComboBox()
        self.set_input.setMinimumWidth(200)
        self.set_input.setMaxVisibleItems(20)
        self.set_input.addItem(ANY)
        self.set_input.currentIndexChanged.connect(self.changed)

        self.foil_input = QComboBox()
        self.foil_input.addItems([ANY, "Foil only", "Non-foil only"])
        self.foil_input.currentIndexChanged.connect(self.changed)

        self.min_price = self._price_box()
        self.max_price = self._price_box()

        self.min_quantity = QSpinBox()
        self.min_quantity.setRange(1, 999)
        self.min_quantity.setFixedWidth(80)
        self.min_quantity.valueChanged.connect(self.changed)

        self.clear_button = QPushButton("Clear filters")
        self.clear_button.clicked.connect(self.clear)

        fields_row = QHBoxLayout()
        fields_row.setSpacing(8)
        for caption, widget in (
            ("TYPE", self.type_input), ("EDITION", self.set_input), ("FINISH", self.foil_input),
            ("PRICE FROM", self.min_price), ("TO", self.max_price), ("MIN. COPIES", self.min_quantity),
        ):
            fields_row.addWidget(self._caption(caption))
            fields_row.addWidget(widget)
            fields_row.addSpacing(6)
        fields_row.addStretch()
        fields_row.addWidget(self.clear_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)
        layout.addLayout(rarity_row)
        layout.addLayout(fields_row)
        self.setLayout(layout)

    # ---------- Building blocks ----------

    def _caption(self, text):
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def _chip(self, text, color):
        chip = QPushButton(text)
        chip.setObjectName("filterChip")
        chip.setCheckable(True)
        # Checked chips take the color of their rarity / mana
        chip.setStyleSheet(
            f"QPushButton#filterChip:checked {{ color: {color}; border: 1px solid {color}; }}"
        )
        chip.toggled.connect(self.changed)
        return chip

    def _price_box(self):
        box = QDoubleSpinBox()
        box.setRange(0, 100000)
        box.setDecimals(2)
        box.setSpecialValueText("—")      # 0 = no limit
        box.setFixedWidth(90)
        box.valueChanged.connect(self.changed)
        return box

    # ---------- State ----------

    def set_editions(self, set_names):
        """Fill the edition list with the sets in the shown collection."""

        current = self.set_input.currentText()

        self.set_input.blockSignals(True)
        self.set_input.clear()
        self.set_input.addItem(ANY)
        self.set_input.addItems(sorted(set(name for name in set_names if name)))
        index = self.set_input.findText(current)
        self.set_input.setCurrentIndex(index if index >= 0 else 0)
        self.set_input.blockSignals(False)

    def active_count(self):
        """How many filters are on (for the "Filters (3)" button)."""

        count = 0
        count += any(chip.isChecked() for chip in self.rarity_chips.values())
        count += any(chip.isChecked() for chip in self.color_chips.values())
        count += self.type_input.currentText() != ANY
        count += self.set_input.currentText() != ANY
        count += self.foil_input.currentIndex() != 0
        count += self.min_price.value() > 0 or self.max_price.value() > 0
        count += self.min_quantity.value() > 1
        return count

    def clear(self):

        widgets = list(self.rarity_chips.values()) + list(self.color_chips.values()) + [
            self.type_input, self.set_input, self.foil_input,
            self.min_price, self.max_price, self.min_quantity,
        ]
        for widget in widgets:
            widget.blockSignals(True)

        for chip in list(self.rarity_chips.values()) + list(self.color_chips.values()):
            chip.setChecked(False)
        self.type_input.setCurrentIndex(0)
        self.set_input.setCurrentIndex(0)
        self.foil_input.setCurrentIndex(0)
        self.min_price.setValue(0)
        self.max_price.setValue(0)
        self.min_quantity.setValue(1)

        for widget in widgets:
            widget.blockSignals(False)

        self.changed.emit()

    # ---------- Matching ----------

    def matches(self, card, currency):
        """True if the card passes every active filter."""

        rarities = {r for r, chip in self.rarity_chips.items() if chip.isChecked()}
        if rarities and card.rarity not in rarities:
            return False

        wanted_colors = {c for c, chip in self.color_chips.items() if chip.isChecked()}
        if wanted_colors:
            colors = card_colors(card)
            tags = set(colors)
            if not colors:
                tags.add("C")
            if len(colors) >= 2:
                tags.add("M")
            # A card passes if it has ANY of the chosen colors
            if not tags & wanted_colors:
                return False

        card_type = self.type_input.currentText()
        if card_type != ANY and card_type not in (card.type_line or ""):
            return False

        edition = self.set_input.currentText()
        if edition != ANY and card.set_name != edition:
            return False

        finish = self.foil_input.currentIndex()
        if finish == 1 and not card.foil:
            return False
        if finish == 2 and card.foil:
            return False

        low, high = self.min_price.value(), self.max_price.value()
        if low > 0 or high > 0:
            price = card.price(currency)
            if price is None:
                return False
            if low > 0 and price < low:
                return False
            if high > 0 and price > high:
                return False

        if (card.quantity or 0) < self.min_quantity.value():
            return False

        return True
