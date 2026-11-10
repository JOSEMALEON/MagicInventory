"""
Dice roller: d4, d6, d8, d10, d12 and d20, each drawn with its own shape.
Rolling one shows a short animation: the die spins and shuffles numbers,
slowing down until it lands on the result.
"""

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QListWidget, QVBoxLayout, QWidget

DICE = (4, 6, 8, 10, 12, 20)

# Animation: number changes, from fast to slow (ms)
ROLL_STEPS = 14
ROLL_FIRST_STEP_MS = 35
ROLL_SLOWDOWN_MS = 180

# The theme's blue gradient, and the result's green glow
FACE_TOP = QColor("#38BDF8")
FACE_BOTTOM = QColor("#2563EB")
EDGE = QColor("#BFDBFE")
RESULT_GLOW = QColor("#4ADE80")

# How many past rolls the history keeps
HISTORY_SIZE = 30


def die_polygon(sides, center, radius):
    """
    The outline of each die, as seen on the table:
    d4 triangle, d6 square, d8 diamond, d10 kite, d12 pentagon, d20 hexagon.
    """

    cx, cy = center.x(), center.y()

    def regular(count, rotation_degrees):
        return [
            QPointF(
                cx + radius * math.cos(math.radians(rotation_degrees + 360 * k / count)),
                cy + radius * math.sin(math.radians(rotation_degrees + 360 * k / count)),
            )
            for k in range(count)
        ]

    if sides == 4:
        points = regular(3, -90)
    elif sides == 6:
        points = regular(4, -45)
    elif sides == 8:
        points = regular(4, -90)
    elif sides == 10:
        # Kite: long top and bottom points, wide in the upper middle
        points = [
            QPointF(cx, cy - radius),
            QPointF(cx + radius * 0.82, cy - radius * 0.12),
            QPointF(cx, cy + radius),
            QPointF(cx - radius * 0.82, cy - radius * 0.12),
        ]
    elif sides == 12:
        points = regular(5, -90)
    else:
        points = regular(6, -90)

    return QPolygonF(points)


def _font(size, bold=True):
    font = QFont()
    font.setPixelSize(size)
    font.setBold(bold)
    return font


class DieWidget(QWidget):
    """
    One die. Click it to roll; `rolled` gives (sides, result) at the end of
    the animation.
    """

    rolled = Signal(int, int)

    def __init__(self, sides, size=96):
        super().__init__()

        self.sides = sides
        self.value = None          # number shown (None = just the "d20" label)
        self.angle = 0.0
        self.rolling = False
        self.landed = False        # glow when the result is shown

        self._result = None
        self._step = 0
        self._spin = 0.0

        self.setFixedSize(size, size + 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Roll a d{sides}")

    # ---------- Rolling ----------

    def roll(self):

        if self.rolling:
            return

        self.rolling = True
        self.landed = False
        self._result = random.randint(1, self.sides)
        self._step = 0
        # Spin direction and speed change on every roll
        self._spin = random.choice((-1, 1)) * random.uniform(38, 52)
        self._next_step()

    def _next_step(self):

        if self._step >= ROLL_STEPS:
            self.value = self._result
            self.angle = 0.0
            self.rolling = False
            self.landed = True
            self.update()
            self.rolled.emit(self.sides, self._result)
            return

        progress = self._step / ROLL_STEPS

        # Random numbers while it spins (never the same twice in a row)
        options = [n for n in range(1, self.sides + 1) if n != self.value] or [1]
        self.value = random.choice(options)

        # The spin slows down with the numbers
        self.angle = (self.angle + self._spin * (1 - progress)) % 360

        self.update()
        self._step += 1

        delay = int(ROLL_FIRST_STEP_MS + ROLL_SLOWDOWN_MS * progress ** 2)
        QTimer.singleShot(delay, self._next_step)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.roll()

    # ---------- Drawing ----------

    def paintEvent(self, event):

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        size = self.width()
        center = QPointF(size / 2, size / 2)
        radius = size * 0.42

        painter.save()
        painter.translate(center)
        painter.rotate(self.angle)
        painter.translate(-center)

        polygon = die_polygon(self.sides, center, radius)

        gradient = QLinearGradient(0, center.y() - radius, 0, center.y() + radius)
        gradient.setColorAt(0.0, FACE_TOP)
        gradient.setColorAt(1.0, FACE_BOTTOM)

        edge = QPen(RESULT_GLOW if self.landed else EDGE)
        edge.setWidthF(3.0 if self.landed else 1.6)
        edge.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        painter.setPen(edge)
        painter.setBrush(gradient)
        painter.drawPolygon(polygon)

        # Facet lines: the d20 shows its central triangle, the d8/d10 a middle line
        facet = QPen(QColor(255, 255, 255, 70))
        facet.setWidthF(1.2)
        painter.setPen(facet)
        if self.sides == 20:
            # The front triangle face of a d20, inside the hexagon
            triangle = QPolygonF([
                QPointF(center.x(), center.y() - radius * 0.55),
                QPointF(center.x() + radius * 0.52, center.y() + radius * 0.35),
                QPointF(center.x() - radius * 0.52, center.y() + radius * 0.35),
            ])
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(triangle)
        elif self.sides in (8, 10):
            painter.drawLine(polygon[1], polygon[3])

        painter.restore()

        # Number (upright, not rotated, so it stays readable)
        painter.setPen(QColor("#FFFFFF"))
        if self.value is None:
            painter.setFont(_font(int(size * 0.2)))
            painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, f"d{self.sides}")
        else:
            painter.setFont(_font(int(size * (0.3 if self.value < 10 else 0.26))))
            painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, str(self.value))

        # Die name under it
        painter.setPen(QColor("#8B92A5"))
        painter.setFont(_font(12, bold=False))
        painter.drawText(QRectF(0, size, size, 20), Qt.AlignmentFlag.AlignCenter, f"d{self.sides}")

        painter.end()


class DiceDialog(QDialog):
    """
    Small window with the six dice and the history of rolls. It isn't
    modal: it can stay open next to the life counter during the game.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Dice")
        self.setModal(False)

        title = QLabel("Dice")
        title.setObjectName("dialogTitle")

        hint = QLabel("Click a die to roll it.")
        hint.setObjectName("mutedLabel")

        self.result_label = QLabel(" ")
        self.result_label.setObjectName("diceResult")
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        dice_row = QHBoxLayout()
        dice_row.setSpacing(14)
        self.dice = []
        for sides in DICE:
            die = DieWidget(sides)
            die.rolled.connect(self._on_rolled)
            self.dice.append(die)
            dice_row.addWidget(die)

        history_label = QLabel("LAST ROLLS")
        history_label.setObjectName("fieldLabel")

        self.history = QListWidget()
        self.history.setObjectName("diceHistory")
        self.history.setMaximumHeight(130)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addLayout(dice_row)
        layout.addWidget(self.result_label)
        layout.addWidget(history_label)
        layout.addWidget(self.history)
        self.setLayout(layout)

    def _on_rolled(self, sides, result):

        # Only the last rolled die keeps the green glow
        for die in self.dice:
            if die.sides != sides and die.landed:
                die.landed = False
                die.update()

        best = "  (max!)" if result == sides else ("  (min)" if result == 1 else "")
        self.result_label.setText(f"d{sides}: {result}{best}")

        self.history.insertItem(0, f"d{sides}  →  {result}")
        while self.history.count() > HISTORY_SIZE:
            self.history.takeItem(self.history.count() - 1)
