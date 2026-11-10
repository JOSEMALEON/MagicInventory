"""
Life counter page: up to 6 player panels with life, commander damage
(split in two for players with Partner), counters and markers.
"""

import random

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services import life_service as life
from src.ui.widgets import set_status

# The last life change ("-7") disappears after this long
CHANGE_VISIBLE_MS = 2000

# "Who starts?" animation: the green light goes round the table this many
# times, each step slower than the one before (like a roulette wheel)
SPIN_LAPS = 3
SPIN_FIRST_STEP_MS = 45      # first steps: very fast
SPIN_SLOWDOWN_MS = 520       # extra time added, growing towards the last step
SPIN_HOLD_MS = 3000          # the chosen player stays lit this long

SPOTLIGHT_COLOR = "#4ADE80"

LAYOUT_COLUMNS = {2: 2, 3: 3, 4: 2, 5: 3, 6: 3}


def _rgba(color, alpha):
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


class ClickBox(QLabel):
    """
    A value you change by clicking: left click +1, right click -1.
    Used for commander damage and counters.
    """

    changed = Signal(int)   # +1 / -1

    def __init__(self, object_name):
        super().__init__()
        self.setObjectName(object_name)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.changed.emit(1)
        elif event.button() == Qt.MouseButton.RightButton:
            self.changed.emit(-1)


class PlayerPanel(QWidget):
    """
    One player. The page rebuilds the panels when the number of players or
    a Partner changes, and calls refresh() after any other change.
    """

    def __init__(self, page, index):
        super().__init__()

        self.page = page
        self.index = index
        self._pending_change = 0

        player = self.player
        self.setObjectName("lifePanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # The player's color: a tinted background and a top bar
        self._spotlight = None
        self.set_spotlight(False)

        # ---------- Header: name, markers, partner ----------

        self.name_input = QLineEdit(player.name)
        self.name_input.setObjectName("playerName")
        self.name_input.setMaxLength(24)
        self.name_input.editingFinished.connect(
            lambda: self.page.counter_action(lambda c: c.rename(self.index, self.name_input.text()))
        )

        self.starts_label = QLabel("Starts")
        self.starts_label.setObjectName("startsBadge")

        self.monarch_button = self._toggle("👑", "Monarch (only one player)")
        self.monarch_button.clicked.connect(
            lambda: self.page.counter_action(lambda c: c.toggle_marker("monarch", self.index))
        )
        self.initiative_button = self._toggle("⚑", "Initiative (only one player)")
        self.initiative_button.clicked.connect(
            lambda: self.page.counter_action(lambda c: c.toggle_marker("initiative", self.index))
        )
        self.blessing_button = self._toggle("✦", "City's blessing")
        self.blessing_button.clicked.connect(
            lambda: self.page.counter_action(lambda c: c.toggle_city_blessing(self.index))
        )

        self.partner_button = QPushButton("Partner")
        self.partner_button.setObjectName("partnerButton")
        self.partner_button.setCheckable(True)
        self.partner_button.setChecked(player.partner)
        self.partner_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.partner_button.setToolTip(
            "Two commanders (Partner, Background, Friends forever…): the other players\n"
            "track the damage of each one separately"
        )
        self.partner_button.clicked.connect(
            lambda checked: self.page.set_partner(self.index, checked)
        )

        header = QHBoxLayout()
        header.setSpacing(6)
        header.addWidget(self.name_input, 1)
        header.addWidget(self.starts_label)
        header.addWidget(self.monarch_button)
        header.addWidget(self.initiative_button)
        header.addWidget(self.blessing_button)
        header.addWidget(self.partner_button)

        # ---------- Life ----------

        self.life_label = QLabel()
        self.life_label.setObjectName("lifeTotal")
        self.life_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.change_label = QLabel()
        self.change_label.setObjectName("lifeChange")
        self.change_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.change_label.setFixedWidth(56)

        self._change_timer = QTimer(self)
        self._change_timer.setSingleShot(True)
        self._change_timer.timeout.connect(self._clear_change)

        life_row = QHBoxLayout()
        life_row.setSpacing(6)
        for delta in (-5, -1):
            life_row.addWidget(self._life_button(delta))
        life_row.addStretch()
        life_row.addWidget(self.change_label)
        life_row.addWidget(self.life_label)
        life_row.addSpacing(56)
        life_row.addStretch()
        for delta in (1, 5):
            life_row.addWidget(self._life_button(delta))

        # ---------- Commander damage ----------

        damage_caption = QLabel("COMMANDER DAMAGE  ·  click +1, right click −1")
        damage_caption.setObjectName("fieldLabel")

        self.damage_boxes = {}   # {(source, commander): ClickBox}
        damage_row = QHBoxLayout()
        damage_row.setSpacing(6)

        for source, other in enumerate(self.page.counter.game.players):
            if source == self.index:
                continue
            damage_row.addWidget(self._damage_group(source, other), 1)

        # ---------- Counters ----------

        self.counter_boxes = {}
        counters_row = QHBoxLayout()
        counters_row.setSpacing(6)

        for key, label in life.COUNTERS.items():
            box = ClickBox("counterBox")
            box.setToolTip(f"{label}: click +1, right click −1")
            box.changed.connect(
                lambda delta, k=key: self.page.counter_action(lambda c: c.change_counter(self.index, k, delta))
            )
            self.counter_boxes[key] = (box, label)
            counters_row.addWidget(box, 1)

        # Commander tax: one per commander
        self.tax_boxes = []
        for commander in range(2 if player.partner else 1):
            box = ClickBox("counterBox")
            box.setToolTip("Commander tax: click when the commander is cast (+2 each time), right click −1 cast")
            box.changed.connect(
                lambda delta, cm=commander: self.page.counter_action(
                    lambda c: c.change_casts(self.index, cm, delta)
                )
            )
            self.tax_boxes.append(box)
            counters_row.addWidget(box, 1)

        # ---------- Eliminated ----------

        self.eliminated_label = QLabel()
        self.eliminated_label.setObjectName("eliminatedLabel")
        self.eliminated_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.eliminated_label.setWordWrap(True)

        # Everything below the header fades out when the player is eliminated
        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(8)
        body.addLayout(life_row)
        body.addWidget(damage_caption)
        body.addLayout(damage_row)
        body.addLayout(counters_row)

        self.body = QWidget()
        self.body.setLayout(body)
        self._fade = QGraphicsOpacityEffect(self.body)
        self._fade.setOpacity(1.0)
        self.body.setGraphicsEffect(self._fade)

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)
        layout.addLayout(header)
        layout.addWidget(self.eliminated_label)
        layout.addWidget(self.body, 1)
        self.setLayout(layout)

        self.refresh()

    @property
    def player(self):
        return self.page.counter.game.players[self.index]

    def set_spotlight(self, on):
        """
        Green highlight used by the "Who starts?" animation; off = the
        player's own colors.
        """

        if on == self._spotlight:
            return
        self._spotlight = on

        if on:
            top, tint, border = SPOTLIGHT_COLOR, _rgba(SPOTLIGHT_COLOR, 0.30), SPOTLIGHT_COLOR
            border_width = 2
        else:
            color = self.player.color
            top, tint, border = color, _rgba(color, 0.20), "#2C313D"
            border_width = 1

        self.setStyleSheet(f"""
            QWidget#lifePanel {{
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {tint}, stop:0.45 #1B1E26, stop:1 #1B1E26);
                border: {border_width}px solid {border};
                border-top: 4px solid {top};
                border-radius: 14px;
            }}
        """)

    def set_starts_glow(self, on):
        """The "Starts" badge shines for a few seconds after the animation."""
        self.starts_label.setProperty("glow", on)
        _repolish(self.starts_label)

    # ---------- Building blocks ----------

    def _toggle(self, text, tooltip):
        button = QPushButton(text)
        button.setObjectName("markerButton")
        button.setCheckable(True)
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedWidth(34)
        return button

    def _life_button(self, delta):
        button = QPushButton(f"{delta:+d}".replace("-", "−"))
        button.setObjectName("lifeButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedWidth(46)
        button.clicked.connect(lambda: self.change_life(delta))
        return button

    def _damage_group(self, source, other):
        """
        Damage received from one opponent: one box, or two halves (A | B)
        when that opponent has Partner.
        """

        # Partner: "Luis  A | B" above the two halves
        name = QLabel(f"{other.name}  A | B" if other.partner else other.name)
        name.setObjectName("damageSource")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet(f"color: {other.color};")

        boxes = QHBoxLayout()
        boxes.setSpacing(2)

        for commander in range(2 if other.partner else 1):
            box = ClickBox("damageBox")
            box.setStyleSheet(f"QLabel#damageBox {{ border: 1px solid {_rgba(other.color, 0.6)}; }}")
            suffix = (" (commander A)", " (commander B)")[commander] if other.partner else ""
            box.setToolTip(f"Damage from {other.name}{suffix}: click +1, right click −1")
            box.changed.connect(
                lambda delta, s=source, cm=commander: self.page.counter_action(
                    lambda c: c.change_commander_damage(self.index, s, cm, delta)
                )
            )
            self.damage_boxes[(source, commander)] = box
            boxes.addWidget(box)

        group = QVBoxLayout()
        group.setSpacing(3)
        group.addWidget(name)
        group.addLayout(boxes)

        widget = QWidget()
        widget.setLayout(group)
        return widget

    # ---------- Life changes ----------

    def change_life(self, delta):
        self.page.counter_action(lambda c: c.change_life(self.index, delta))

        # "−7": the sum of the recent changes, hidden after a moment
        self._pending_change += delta
        self.change_label.setText(f"{self._pending_change:+d}".replace("-", "−"))
        self._change_timer.start(CHANGE_VISIBLE_MS)

    def _clear_change(self):
        self._pending_change = 0
        self.change_label.setText("")

    # ---------- Refresh ----------

    def refresh(self):

        game = self.page.counter.game
        player = self.player

        self.life_label.setText(str(player.life))

        if self.name_input.text() != player.name and not self.name_input.hasFocus():
            self.name_input.setText(player.name)

        for (source, commander), box in self.damage_boxes.items():
            damage = player.damage_from(source, commander)
            box.setText(str(damage))
            box.setProperty("lethal", damage >= life.LETHAL_COMMANDER_DAMAGE)
            _repolish(box)

        for key, (box, label) in self.counter_boxes.items():
            value = player.counters[key]
            box.setText(f"{label}\n{value}")
            lethal = key == "poison" and value >= life.LETHAL_POISON
            box.setProperty("active", value > 0)
            box.setProperty("lethal", lethal)
            _repolish(box)

        for commander, box in enumerate(self.tax_boxes):
            name = f"Tax {'AB'[commander]}" if len(self.tax_boxes) == 2 else "Tax"
            box.setText(f"{name}\n+{player.tax(commander)}")
            box.setProperty("active", player.casts[commander] > 0)
            _repolish(box)

        self.monarch_button.setChecked(game.monarch == self.index)
        self.initiative_button.setChecked(game.initiative == self.index)
        self.blessing_button.setChecked(player.city_blessing)
        self.partner_button.setChecked(player.partner)
        self.starts_label.setVisible(game.first_player == self.index)

        reason = self.page.counter.elimination_reason(self.index)
        self.eliminated_label.setVisible(reason is not None)
        self.eliminated_label.setText(f"✗ Eliminated: {reason}" if reason else "")
        self._fade.setOpacity(0.4 if reason else 1.0)


def _repolish(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class LifePage(QWidget):
    """The life counter page."""

    def __init__(self):
        super().__init__()

        # Continue the saved game, if any
        saved = life.load_game()
        self.counter = life.LifeCounter(saved or life.new_game(4, life.DEFAULT_STARTING_LIFE))
        self.panels = []

        # Each "Who starts?" animation gets an id: a newer one (or new panels) stops the old
        self._spin_id = 0

        title = QLabel("Life counter")
        title.setObjectName("pageTitle")

        # ---------- Top bar ----------

        players_label = QLabel("Players")
        players_label.setObjectName("mutedLabel")

        self.players_input = QComboBox()
        for count in range(life.MIN_PLAYERS, life.MAX_PLAYERS + 1):
            self.players_input.addItem(str(count), count)

        life_label = QLabel("Starting life")
        life_label.setObjectName("mutedLabel")

        self.life_input = QComboBox()
        for value in life.STARTING_LIFE_OPTIONS:
            self.life_input.addItem(str(value), value)

        new_game_button = QPushButton("New game")
        new_game_button.setObjectName("primaryButton")
        new_game_button.setCursor(Qt.CursorShape.PointingHandCursor)
        new_game_button.clicked.connect(self.new_game)

        self.first_button = QPushButton("Who starts?")
        first_button = self.first_button
        first_button.setCursor(Qt.CursorShape.PointingHandCursor)
        first_button.clicked.connect(self.choose_first_player)

        self.undo_button = QPushButton("Undo")
        self.undo_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.undo_button.setToolTip("Undo the last change (Ctrl+Z)")
        self.undo_button.clicked.connect(self.undo)

        self.status_label = QLabel()
        self.status_label.setObjectName("statusLabel")

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(title)
        top.addSpacing(20)
        top.addWidget(players_label)
        top.addWidget(self.players_input)
        top.addWidget(life_label)
        top.addWidget(self.life_input)
        top.addWidget(new_game_button)
        top.addStretch()
        top.addWidget(self.status_label)
        top.addWidget(first_button)
        top.addWidget(self.undo_button)

        # ---------- Panels ----------

        self.grid = QGridLayout()
        self.grid.setSpacing(14)

        grid_widget = QWidget()
        grid_widget.setLayout(self.grid)

        layout = QVBoxLayout()
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        layout.addLayout(top)
        layout.addWidget(grid_widget, 1)
        self.setLayout(layout)

        undo_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Undo), self)
        undo_shortcut.activated.connect(self.undo)

        self._sync_setup_inputs()
        self.rebuild()

    # ---------- Panels ----------

    def rebuild(self):
        """Create the panels again (number of players or a Partner changed)."""

        for panel in self.panels:
            self.grid.removeWidget(panel)
            # Hide and detach now: deleteLater() only removes it later, and
            # until then it would still be drawn under the new panels
            panel.hide()
            panel.setParent(None)
            panel.deleteLater()

        self.panels = []

        # A "Who starts?" animation running on the old panels stops here
        self._spin_id += 1
        self.first_button.setEnabled(True)

        players = self.counter.game.players
        columns = LAYOUT_COLUMNS.get(len(players), 3)

        for column in range(3):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)
        for row in range(2):
            self.grid.setRowStretch(row, 1)

        for index in range(len(players)):
            panel = PlayerPanel(self, index)
            self.grid.addWidget(panel, index // columns, index % columns)
            self.panels.append(panel)

        self.undo_button.setEnabled(self.counter.can_undo())

    def refresh(self):
        for panel in self.panels:
            panel.refresh()
        self.undo_button.setEnabled(self.counter.can_undo())

    def counter_action(self, action):
        """Run a change on the game and redraw the values."""
        action(self.counter)
        self.refresh()

    # ---------- Actions ----------

    def set_partner(self, index, partner):
        # The opponents' damage boxes change shape: rebuild the panels
        self.counter.set_partner(index, partner)
        self.rebuild()

    def new_game(self):

        count = self.players_input.currentData()
        starting_life = self.life_input.currentData()

        answer = QMessageBox.question(
            self,
            "New game",
            f"Start a new game for {count} players with {starting_life} life?\n\n"
            "Life, commander damage and counters go back to the start "
            "(names and Partner are kept). You can undo it.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        self.counter.new_game(count, starting_life)
        self.rebuild()
        set_status(self.status_label, "New game started.", "success")

    # ---------- "Who starts?" animation ----------

    def choose_first_player(self):
        """
        Pick the first player at random, then show it with a green light
        that goes round the table, slowing down until it stops on them.
        """

        chosen = self.counter.choose_first_player()

        # Hide the badge until the light arrives
        for panel in self.panels:
            panel.starts_label.setVisible(False)

        self._spin_id += 1
        spin_id = self._spin_id

        count = len(self.panels)
        start = random.randrange(count)
        total = SPIN_LAPS * count + (chosen - start) % count
        seats = [(start + step) % count for step in range(total + 1)]

        self.first_button.setEnabled(False)
        set_status(self.status_label, "Choosing who starts…")
        self._spin_step(spin_id, seats, 0)

    def _spin_step(self, spin_id, seats, step):

        # Panels were rebuilt (new game, Partner…): stop quietly
        if spin_id != self._spin_id or not self.panels:
            return

        for index, panel in enumerate(self.panels):
            panel.set_spotlight(index == seats[step])

        if step == len(seats) - 1:
            self._spin_finished(spin_id, seats[step])
            return

        # Ease-in: the delay grows slowly at first and fast near the end
        progress = step / (len(seats) - 1)
        delay = int(SPIN_FIRST_STEP_MS + SPIN_SLOWDOWN_MS * progress ** 3)

        QTimer.singleShot(delay, lambda: self._spin_step(spin_id, seats, step + 1))

    def _spin_finished(self, spin_id, chosen):

        panel = self.panels[chosen]
        panel.starts_label.setVisible(True)
        panel.set_starts_glow(True)

        self.first_button.setEnabled(True)
        set_status(self.status_label, f"{panel.player.name} starts!", "success")

        QTimer.singleShot(SPIN_HOLD_MS, lambda: self._spin_hold_over(spin_id, chosen))

    def _spin_hold_over(self, spin_id, chosen):

        if spin_id != self._spin_id or chosen >= len(self.panels):
            return

        self.panels[chosen].set_spotlight(False)
        self.panels[chosen].set_starts_glow(False)

    def undo(self):

        if not self.counter.can_undo():
            return

        before = (len(self.counter.game.players), [p.partner for p in self.counter.game.players])
        self.counter.undo()
        after = (len(self.counter.game.players), [p.partner for p in self.counter.game.players])

        # Undoing a new game or a Partner change needs new panels
        if before != after:
            self._sync_setup_inputs()
            self.rebuild()
        else:
            self.refresh()

        set_status(self.status_label, "Undone.")

    def _sync_setup_inputs(self):
        game = self.counter.game
        self.players_input.setCurrentIndex(self.players_input.findData(len(game.players)))
        index = self.life_input.findData(game.starting_life)
        if index >= 0:
            self.life_input.setCurrentIndex(index)
