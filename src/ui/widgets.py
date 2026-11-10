"""
Small reusable widgets and helpers shared by the windows and dialogs.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSpinBox, QWidget

from services.price_service import format_money


def printing_text(card, currency):
    """
    Text of an edition in a combo box: "Commander Masters (CMM #410) — €4.66".
    """

    price = card.price(currency)

    if price is None:
        return card.printing_label

    return f"{card.printing_label}  —  {format_money(price, currency)}"


def styled_panel(name, layout):
    """
    A plain QWidget that the stylesheet can target by name (e.g. #sidebar)
    and that actually paints its background.
    """

    panel = QWidget()
    panel.setObjectName(name)
    panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    panel.setLayout(layout)
    return panel


def set_status(label, text, state="info"):
    """
    Show a feedback message in a #statusLabel. state: "info", "success"
    or "error" (each one has its own color in styles.qss).
    """

    label.setText(text)
    label.setProperty("state", state)

    # Re-apply the stylesheet so the new property value takes effect
    label.style().unpolish(label)
    label.style().polish(label)


class QuantitySpinBox(QSpinBox):
    """
    Spin box for the collection table. It ignores the mouse wheel unless it
    has focus, so scrolling the table never changes quantities by accident.
    """

    def __init__(self, value=1, parent=None):
        super().__init__(parent)

        self.setRange(1, 999)
        self.setValue(value)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def wheelEvent(self, event):

        if self.hasFocus():
            super().wheelEvent(event)
        else:
            # Let the table scroll instead
            event.ignore()
