"""
Small reusable widgets and helpers shared by the windows and dialogs.
"""

import re

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QSpinBox, QWidget

from services.price_service import format_money
from services.symbol_service import split_mana_cost, symbol_path


def format_mana_cost(mana_cost, empty="No mana cost"):
    """
    "{2}{U}{U}" -> "2 U U". Double-faced costs keep their " // " separator.
    """

    if not mana_cost:
        return empty

    faces = mana_cost.split(" // ")
    return "  //  ".join(" ".join(re.findall(r"\{([^}]+)\}", face)) for face in faces)


# {(mana cost, height, device pixel ratio): QPixmap}
_mana_pixmaps = {}

SYMBOL_SPACING = 2
FACE_SEPARATOR = "//"
SEPARATOR_COLOR = "#8B92A5"


def mana_pixmap(mana_cost, height=18):
    """
    The mana cost drawn with Scryfall's symbols ({2}{W}{U} -> three icons),
    or None if it's empty or a symbol isn't downloaded yet (show the text
    instead). Double-faced costs get "//" between the faces.
    Must be called in the GUI thread.
    """

    if not mana_cost:
        return None

    screen = QGuiApplication.primaryScreen()
    ratio = screen.devicePixelRatio() if screen else 1.0

    key = (mana_cost, height, ratio)
    if key in _mana_pixmaps:
        return _mana_pixmaps[key]

    faces = split_mana_cost(mana_cost)
    paths = [[symbol_path(symbol) for symbol in face] for face in faces]

    if not any(paths) or any(path is None for face in paths for path in face):
        return None

    separator_font = QFont()
    separator_font.setPixelSize(int(height * 0.8))
    separator_width = QFontMetrics(separator_font).horizontalAdvance(f" {FACE_SEPARATOR} ")

    symbol_count = sum(len(face) for face in paths)
    width = (
        symbol_count * height
        + max(0, symbol_count - len(paths)) * SYMBOL_SPACING
        + (len(paths) - 1) * separator_width
    )

    # Drawn at the screen's real resolution so the icons stay sharp
    pixmap = QPixmap(int(width * ratio), int(height * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    x = 0
    for face_index, face in enumerate(paths):

        if face_index:
            painter.setFont(separator_font)
            painter.setPen(QColor(SEPARATOR_COLOR))
            painter.drawText(
                QRectF(x, 0, separator_width, height),
                Qt.AlignmentFlag.AlignCenter,
                FACE_SEPARATOR,
            )
            x += separator_width

        for index, path in enumerate(face):
            QSvgRenderer(str(path)).render(painter, QRectF(x, 0, height, height))
            x += height + (SYMBOL_SPACING if index < len(face) - 1 else 0)

    painter.end()

    _mana_pixmaps[key] = pixmap
    return pixmap


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
