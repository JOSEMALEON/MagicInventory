"""
Small charts drawn with QPainter (no extra dependencies), in the app's
dark theme: a vertical bar chart (mana curve) and horizontal bars
(colors, card types).
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

TEXT_COLOR = QColor("#E8EAF0")
MUTED_COLOR = QColor("#8B92A5")
TRACK_COLOR = QColor("#242833")

# Theme blue gradient (same as the primary buttons)
BAR_TOP = QColor("#38BDF8")
BAR_BOTTOM = QColor("#2563EB")


def _font(size, bold=False):
    font = QFont()
    font.setPixelSize(size)
    font.setBold(bold)
    return font


class BarChart(QWidget):
    """
    Vertical bars with their value on top and a label below, e.g. the
    mana curve: labels ["0", "1", ... "7+"], values [0, 8, 18, ...].
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.labels = []
        self.values = []
        self.setMinimumHeight(170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, labels, values):
        self.labels = list(labels)
        self.values = list(values)
        self.update()

    def paintEvent(self, event):

        if not self.values:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width, height = self.width(), self.height()
        label_height, value_height = 22, 20
        chart_top = value_height
        chart_bottom = height - label_height
        chart_height = max(1, chart_bottom - chart_top)

        count = len(self.values)
        slot = width / count
        bar_width = min(46, slot * 0.62)
        top_value = max(self.values) or 1

        for index, (label, value) in enumerate(zip(self.labels, self.values)):
            center = slot * index + slot / 2
            left = center - bar_width / 2

            # Empty track, so columns with 0 cards are still visible
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(TRACK_COLOR)
            painter.drawRoundedRect(QRectF(left, chart_top, bar_width, chart_height), 6, 6)

            if value:
                bar_height = chart_height * value / top_value
                bar_rect = QRectF(left, chart_bottom - bar_height, bar_width, bar_height)

                gradient = QLinearGradient(0, bar_rect.top(), 0, bar_rect.bottom())
                gradient.setColorAt(0.0, BAR_TOP)
                gradient.setColorAt(1.0, BAR_BOTTOM)
                painter.setBrush(gradient)
                painter.drawRoundedRect(bar_rect, 6, 6)

                painter.setPen(TEXT_COLOR)
                painter.setFont(_font(12, bold=True))
                painter.drawText(
                    QRectF(left - 10, bar_rect.top() - value_height, bar_width + 20, value_height),
                    Qt.AlignmentFlag.AlignCenter,
                    str(value),
                )

            painter.setPen(MUTED_COLOR)
            painter.setFont(_font(12))
            painter.drawText(
                QRectF(left - 10, chart_bottom + 2, bar_width + 20, label_height),
                Qt.AlignmentFlag.AlignCenter,
                label,
            )

        painter.end()


class HorizontalBars(QWidget):
    """
    One row per item: label, a bar proportional to its value and the value.
    items: [(label, value, color hex or None for the theme blue)].
    """

    ROW_HEIGHT = 26
    LABEL_WIDTH = 104
    VALUE_WIDTH = 44

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_data(self, items):
        self.items = list(items)
        self.setFixedHeight(max(1, len(self.items)) * self.ROW_HEIGHT)
        self.update()

    def paintEvent(self, event):

        if not self.items:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        top_value = max(value for _, value, _ in self.items) or 1
        bar_left = self.LABEL_WIDTH
        bar_space = max(1, self.width() - self.LABEL_WIDTH - self.VALUE_WIDTH - 8)

        for row, (label, value, color) in enumerate(self.items):
            y = row * self.ROW_HEIGHT
            bar_rect = QRectF(bar_left, y + 7, bar_space, self.ROW_HEIGHT - 14)

            painter.setPen(TEXT_COLOR)
            painter.setFont(_font(13))
            painter.drawText(
                QRectF(0, y, self.LABEL_WIDTH - 8, self.ROW_HEIGHT),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                label,
            )

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(TRACK_COLOR)
            painter.drawRoundedRect(bar_rect, 5, 5)

            if value:
                filled = QRectF(bar_rect.left(), bar_rect.top(), bar_space * value / top_value, bar_rect.height())
                if color:
                    painter.setBrush(QColor(color))
                else:
                    gradient = QLinearGradient(filled.left(), 0, filled.right(), 0)
                    gradient.setColorAt(0.0, BAR_BOTTOM)
                    gradient.setColorAt(1.0, BAR_TOP)
                    painter.setBrush(gradient)
                painter.drawRoundedRect(filled, 5, 5)

            painter.setPen(MUTED_COLOR)
            painter.setFont(_font(12, bold=True))
            painter.drawText(
                QRectF(self.width() - self.VALUE_WIDTH, y, self.VALUE_WIDTH, self.ROW_HEIGHT),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                str(value),
            )

        painter.end()
