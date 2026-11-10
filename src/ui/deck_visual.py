"""
Visual view of a deck: card thumbnails grouped like the list (Commander,
Creatures...), with the copies and a "Missing" badge on the cards you
don't own enough of.
"""

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from services.image_service import load_card_image, to_pixmap
from src.ui.flow_layout import FlowLayout

TILE_WIDTH = 146
TILE_HEIGHT = 204   # Scryfall "normal" ratio

BADGE_BACKGROUND = QColor(17, 19, 24, 215)
MISSING_COLOR = QColor("#F87171")
SELECTED_COLOR = QColor("#38BDF8")


class CardTile(QWidget):
    """
    One card: its image, "×4" when there are several copies, and a red
    "Missing 2" badge (with the image dimmed) when you don't own them.
    """

    clicked = Signal(object)          # DeckCard
    double_clicked = Signal(object)   # DeckCard
    menu_requested = Signal(object, object)   # DeckCard, global position

    def __init__(self, entry, missing=0):
        super().__init__()

        self.entry = entry
        self.missing = missing
        self.pixmap = None
        self.selected = False

        self.setFixedSize(TILE_WIDTH, TILE_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{entry.name}\n{entry.card.type_line or ''}\n{entry.card.printing_label}")

    def set_pixmap(self, pixmap):
        self.pixmap = pixmap
        self.update()

    def set_selected(self, selected):
        if selected != self.selected:
            self.selected = selected
            self.update()

    # ---------- Mouse ----------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.entry)
        elif event.button() == Qt.MouseButton.RightButton:
            self.clicked.emit(self.entry)
            self.menu_requested.emit(self.entry, event.globalPosition().toPoint())

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.entry)

    # ---------- Drawing ----------

    def paintEvent(self, event):

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = 9

        clip = QPainterPath()
        clip.addRoundedRect(rect, radius, radius)
        painter.setClipPath(clip)

        if self.pixmap is not None:
            painter.drawPixmap(self.rect(), self.pixmap)
        else:
            # Placeholder with the name while the image loads
            painter.fillRect(rect, QColor("#242833"))
            painter.setPen(QColor("#8B92A5"))
            painter.setFont(_font(12))
            painter.drawText(
                rect.adjusted(10, 10, -10, -10),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                self.entry.name,
            )

        # Cards you don't own enough copies of look dimmed
        if self.missing:
            painter.fillRect(rect, QColor(17, 19, 24, 110))

        painter.setClipping(False)

        # Below the card's name bar, so the name stays readable
        if self.entry.quantity > 1:
            self._badge(painter, f"×{self.entry.quantity}", QRectF(8, 30, 38, 22), QColor("#E8EAF0"))

        if self.missing:
            self._badge(
                painter, f"Missing {self.missing}",
                QRectF(6, TILE_HEIGHT - 30, TILE_WIDTH - 12, 24), MISSING_COLOR,
            )

        if self.selected:
            painter.setPen(SELECTED_COLOR)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            pen = painter.pen()
            pen.setWidth(3)
            painter.setPen(pen)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), radius, radius)

        painter.end()

    @staticmethod
    def _badge(painter, text, rect, color):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(BADGE_BACKGROUND)
        painter.drawRoundedRect(rect, 6, 6)
        painter.setPen(color)
        painter.setFont(_font(12, bold=True))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


def _font(size, bold=False):
    font = QFont()
    font.setPixelSize(size)
    font.setBold(bold)
    return font


class DeckVisualView(QScrollArea):
    """
    Scrollable view with one block per group: a title and its card tiles,
    wrapped to the available width.
    """

    card_clicked = Signal(object)
    card_double_clicked = Signal(object)
    card_menu_requested = Signal(object, object)

    def __init__(self, background):
        super().__init__()

        self.background = background
        self._pixmaps = {}      # {image url: QPixmap}
        self._tiles = []
        self._load_id = 0

        self.setObjectName("deckVisual")
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._content = QWidget()
        self._content.setObjectName("deckVisualContent")
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(16, 14, 16, 16)
        self._layout.setSpacing(10)
        self.setWidget(self._content)

    def set_groups(self, groups, empty_text=""):
        """
        groups: [(title, [(DeckCard, missing copies)], is_missing_group)].
        """

        self._load_id += 1
        load_id = self._load_id

        # Remove the previous blocks
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._tiles = []

        if not groups:
            label = QLabel(empty_text)
            label.setObjectName("mutedLabel")
            self._layout.addWidget(label)
            self._layout.addStretch()
            return

        for title, cards, is_missing in groups:

            title_label = QLabel(title)
            title_label.setObjectName("visualGroupTitleMissing" if is_missing else "visualGroupTitle")
            self._layout.addWidget(title_label)

            block = QWidget()
            block.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            flow = FlowLayout(block, spacing=10)

            for entry, missing in cards:
                tile = CardTile(entry, missing)
                tile.clicked.connect(self._on_tile_clicked)
                tile.double_clicked.connect(self.card_double_clicked)
                tile.menu_requested.connect(self.card_menu_requested)
                flow.addWidget(tile)
                self._tiles.append(tile)
                self._set_tile_image(tile, load_id)

            self._layout.addWidget(block)
            self._layout.addSpacing(6)

        self._layout.addStretch()

    def select_entry(self, entry_id):
        for tile in self._tiles:
            tile.set_selected(tile.entry.id == entry_id)

    def _on_tile_clicked(self, entry):
        self.select_entry(entry.id)
        self.card_clicked.emit(entry)

    def _set_tile_image(self, tile, load_id):

        url = tile.entry.card.image_url

        if url in self._pixmaps:
            tile.set_pixmap(self._pixmaps[url])
            return

        self.background.run(
            lambda: load_card_image(url, width=TILE_WIDTH, height=TILE_HEIGHT, rounded=False),
            on_success=lambda image: self._on_image_loaded(load_id, url, image),
        )

    def _on_image_loaded(self, load_id, url, image):

        if image is None:
            return

        pixmap = to_pixmap(image)
        self._pixmaps[url] = pixmap

        # The view may have been redrawn: update every tile with this image
        for tile in self._tiles:
            if tile.entry.card.image_url == url:
                tile.set_pixmap(pixmap)
