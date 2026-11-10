"""
FlowLayout: places widgets left to right and wraps to a new row when the
line is full (like words in a paragraph). Qt doesn't include one; this is
the classic version from Qt's examples, adapted to Python.
"""

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout


class FlowLayout(QLayout):

    def __init__(self, parent=None, spacing=10):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def __del__(self):
        while self.count():
            self.takeAt(0)

    # ---------- QLayout interface ----------

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    # ---------- Placement ----------

    def _arrange(self, rect, apply):
        """
        Place the items in rows inside rect. Return the height used.
        """

        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())

        x, y = area.x(), area.y()
        row_height = 0

        for item in self._items:
            size = item.sizeHint()

            # Next row when this item doesn't fit (unless it's the first in the row)
            if x + size.width() > area.right() + 1 and row_height > 0:
                x = area.x()
                y += row_height + self._spacing
                row_height = 0

            if apply:
                item.setGeometry(QRect(QPoint(x, y), size))

            x += size.width() + self._spacing
            row_height = max(row_height, size.height())

        return y + row_height - rect.y() + margins.bottom()
