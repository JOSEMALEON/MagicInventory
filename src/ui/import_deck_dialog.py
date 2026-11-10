from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services import deck_service as decks
from services.card_service import ScryfallError
from services.list_service import (
    parse_deck_list,
    read_list_file,
    resolve_entries,
    suggest_deck_format,
)
from src.ui.widgets import set_status

EXAMPLE_DECK = """About
Name Krenko goblins

Commander
1 Krenko, Mob Boss

Deck
1 Sol Ring (CMM) 410
4 Lightning Bolt
30 Mountain

Sideboard
1 Smash to Smithereens"""

MAX_PROBLEMS_IN_DIALOG = 12


def plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


class ImportDeckDialog(QDialog):
    """
    Create a new deck from a list (pasted or loaded from .txt/.csv) in the
    formats used by Moxfield, Archidekt, MTG Arena... Sections (Commander,
    Deck, Sideboard, Maybeboard) are kept.

    After exec() == Accepted, created_deck_id holds the new deck's id.
    """

    def __init__(self, background, parent=None):
        super().__init__(parent)

        self.background = background
        self.found = []                # [(ListEntry, Card)] of the last check
        self.created_deck_id = None
        self._check_id = 0

        self.setWindowTitle("Import deck")
        self.setModal(True)
        self.resize(980, 680)

        title = QLabel("Import deck")
        title.setObjectName("dialogTitle")

        hint = QLabel(
            "Paste a deck exported from Moxfield, Archidekt, MTG Arena… or load a .txt / .csv. "
            "Titles like “Commander”, “Deck”, “Sideboard” and “Maybeboard” keep each card in its section."
        )
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)

        # ---------- Name and format ----------

        name_label = QLabel("DECK NAME")
        name_label.setObjectName("fieldLabel")

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Taken from the list or the file name")
        self.name_input.textChanged.connect(self._update_import_button)

        format_label = QLabel("FORMAT")
        format_label.setObjectName("fieldLabel")

        self.format_input = QComboBox()
        for key, rules in decks.FORMATS.items():
            self.format_input.addItem(rules["label"], key)
        self.format_input.currentIndexChanged.connect(self._update_commander_choice)

        name_box = QVBoxLayout()
        name_box.setSpacing(6)
        name_box.addWidget(name_label)
        name_box.addWidget(self.name_input)

        format_box = QVBoxLayout()
        format_box.setSpacing(6)
        format_box.addWidget(format_label)
        format_box.addWidget(self.format_input)

        top_row = QHBoxLayout()
        top_row.setSpacing(14)
        top_row.addLayout(name_box, 3)
        top_row.addLayout(format_box, 1)

        # ---------- Left: list ----------

        self.list_input = QPlainTextEdit()
        self.list_input.setObjectName("listInput")
        self.list_input.setPlaceholderText(EXAMPLE_DECK)
        self.list_input.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.list_input.textChanged.connect(self._on_list_changed)

        load_button = QPushButton("Load file…")
        load_button.clicked.connect(self.load_file)

        self.check_button = QPushButton("Check list")
        self.check_button.setObjectName("primaryButton")
        self.check_button.setEnabled(False)
        self.check_button.clicked.connect(self.check_list)

        list_buttons = QHBoxLayout()
        list_buttons.addWidget(load_button)
        list_buttons.addStretch()
        list_buttons.addWidget(self.check_button)

        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(self.list_input, 1)
        left.addLayout(list_buttons)

        # ---------- Right: result ----------

        result_label = QLabel("RESULT")
        result_label.setObjectName("fieldLabel")

        self.status_label = QLabel("Check the list to see the deck before importing it.")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)

        # "Commander: 1 · Deck: 99 · Sideboard: 0 · Maybeboard: 3"
        self.sections_label = QLabel()
        self.sections_label.setObjectName("mutedLabel")
        self.sections_label.setWordWrap(True)

        # Shown for Commander decks whose list doesn't say who the commander is
        self.commander_label = QLabel("COMMANDER")
        self.commander_label.setObjectName("fieldLabel")
        self.commander_input = QComboBox()

        problems_label = QLabel("PROBLEMS")
        problems_label.setObjectName("fieldLabel")

        self.problem_list = QListWidget()
        self.problem_list.setObjectName("problemList")
        self.problem_list.setWordWrap(True)

        self.problems_box = QWidget()
        problems_layout = QVBoxLayout()
        problems_layout.setContentsMargins(0, 6, 0, 0)
        problems_layout.setSpacing(6)
        problems_layout.addWidget(problems_label)
        problems_layout.addWidget(self.problem_list)
        self.problems_box.setLayout(problems_layout)

        right = QVBoxLayout()
        right.setSpacing(8)
        right.addWidget(result_label)
        right.addWidget(self.status_label)
        right.addWidget(self.sections_label)
        right.addSpacing(6)
        right.addWidget(self.commander_label)
        right.addWidget(self.commander_input)
        right.addWidget(self.problems_box, 1)
        right.addStretch()

        right_widget = QWidget()
        right_widget.setLayout(right)
        right_widget.setFixedWidth(380)

        body = QHBoxLayout()
        body.setSpacing(18)
        body.addLayout(left, 1)
        body.addWidget(right_widget)

        # ---------- Buttons ----------

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)

        self.import_button = QPushButton("Create deck")
        self.import_button.setObjectName("primaryButton")
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self.import_deck)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(self.import_button)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addLayout(top_row)
        layout.addLayout(body, 1)
        layout.addLayout(buttons)
        self.setLayout(layout)

        self._clear_result()

    # ==================================
    # INPUT
    # ==================================

    def load_file(self):

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load deck list",
            str(Path.home()),
            "Deck lists (*.txt *.csv *.dek);;Text list (*.txt);;CSV spreadsheet (*.csv)",
        )

        if not path:
            return

        try:
            text, problems = read_list_file(path)
        except OSError as error:
            set_status(self.status_label, f"Could not read the file: {error}", "error")
            return

        self.list_input.setPlainText(text)

        # The file name is a good default name for the deck
        if not self.name_input.text().strip():
            self.name_input.setText(Path(path).stem.replace("_", " "))

        if problems:
            self._show_problems(problems)
            set_status(self.status_label, f"Loaded with {plural(len(problems), 'problem')}.", "error")
        else:
            set_status(self.status_label, f"Loaded {Path(path).name}. Check the list to continue.")

    def _on_list_changed(self):

        self.check_button.setEnabled(bool(self.list_input.toPlainText().strip()))

        # The previous result doesn't match the list anymore
        self._check_id += 1
        self.check_button.setText("Check list")
        if self.found or self.problem_list.count():
            self._clear_result()
            set_status(self.status_label, "The list changed. Check it again before importing.")

    # ==================================
    # CHECK
    # ==================================

    def check_list(self):

        entries, syntax_problems, deck_name = parse_deck_list(self.list_input.toPlainText())

        self._clear_result()

        if deck_name and not self.name_input.text().strip():
            self.name_input.setText(deck_name)

        suggested = suggest_deck_format(entries)
        if suggested:
            self.format_input.setCurrentIndex(self.format_input.findData(suggested))

        if not entries:
            self._show_problems(syntax_problems)
            set_status(self.status_label, "No valid card lines in the list.", "error")
            return

        self._check_id += 1
        check_id = self._check_id

        self.check_button.setEnabled(False)
        self.check_button.setText("Checking…")
        set_status(self.status_label, f"Looking for {plural(len(entries), 'card')} on Scryfall…")

        self.background.run(
            lambda: resolve_entries(entries),
            on_success=lambda result: self._on_checked(check_id, syntax_problems, result),
            on_error=lambda error: self._on_check_error(check_id, error),
        )

    def _on_checked(self, check_id, syntax_problems, result):

        if check_id != self._check_id:
            return

        self.check_button.setText("Check list")
        self.check_button.setEnabled(True)

        found, missing = result
        problems = sorted(syntax_problems + missing, key=lambda problem: problem.line)

        self.found = found
        self._show_sections()
        self._update_commander_choice()
        self._suggest_name()
        self._show_problems(problems)
        self._update_import_button()

        if problems:
            set_status(
                self.status_label,
                f"{plural(len(problems), 'line')} can't be imported (see Problems). "
                "Fix the list, or import the deck without them.",
                "error",
            )
            self._warn(problems)
        else:
            set_status(self.status_label, "All cards found. Ready to import.", "success")

    def _on_check_error(self, check_id, error):

        if check_id != self._check_id:
            return

        self.check_button.setText("Check list")
        self.check_button.setEnabled(True)

        text = (
            "Could not connect to Scryfall. Check your connection and try again."
            if isinstance(error, ScryfallError) else f"Unexpected error: {error}"
        )
        set_status(self.status_label, text, "error")

    # ==================================
    # RESULT
    # ==================================

    def _clear_result(self):

        self.found = []
        self.sections_label.setText("")
        self.problem_list.clear()
        self.problems_box.hide()
        self.commander_label.hide()
        self.commander_input.hide()
        self._update_import_button()

    def _show_sections(self):

        counts = {section: 0 for section in decks.SECTIONS}
        for entry, _ in self.found:
            counts[entry.section] = counts.get(entry.section, 0) + entry.quantity

        parts = [
            f"{decks.SECTION_LABELS[section]}: {counts[section]}"
            for section in decks.SECTIONS
            if counts[section]
        ]
        self.sections_label.setText(" · ".join(parts))

    def _update_commander_choice(self):
        """
        Commander decks without a commander in the list: let the user pick
        one of the cards that can be a commander.
        """

        needs_choice = (
            bool(self.found)
            and decks.is_commander_format(self.format_input.currentData())
            and not any(entry.section == "commander" for entry, _ in self.found)
        )

        self.commander_label.setVisible(needs_choice)
        self.commander_input.setVisible(needs_choice)

        if not needs_choice:
            return

        self.commander_input.clear()
        self.commander_input.addItem("No commander for now", None)

        for index, (entry, card) in enumerate(self.found):
            if entry.section == "main" and decks.can_be_commander(card):
                self.commander_input.addItem(card.name, index)

        # A single candidate is very likely the commander
        if self.commander_input.count() == 2:
            self.commander_input.setCurrentIndex(1)

    def _suggest_name(self):
        """
        Lists without a name (and pasted, not loaded from a file): use the
        commander's name, or a generic one. The user can change it.
        """

        if self.name_input.text().strip():
            return

        commander = next((card for entry, card in self.found if entry.section == "commander"), None)

        if commander is None and self.commander_input.isVisible():
            index = self.commander_input.currentData()
            if index is not None:
                commander = self.found[index][1]

        self.name_input.setText(commander.name if commander else "Imported deck")

    def _show_problems(self, problems):

        self.problem_list.clear()
        for problem in problems:
            self.problem_list.addItem(str(problem))
        self.problems_box.setVisible(bool(problems))

    def _warn(self, problems):

        shown = [f"• {problem}" for problem in problems[:MAX_PROBLEMS_IN_DIALOG]]
        if len(problems) > len(shown):
            shown.append(f"…and {len(problems) - len(shown)} more (see the Problems list).")

        QMessageBox.warning(
            self,
            "Problems in the deck list",
            f"{plural(len(problems), 'line')} could not be read or found:\n\n" + "\n".join(shown),
        )

    def _update_import_button(self):

        copies = sum(entry.quantity for entry, _ in self.found)
        ready = bool(self.found) and bool(self.name_input.text().strip())

        self.import_button.setEnabled(ready)
        self.import_button.setText(
            f"Create deck ({plural(copies, 'card')})" if self.found else "Create deck"
        )

    # ==================================
    # IMPORT
    # ==================================

    def import_deck(self):

        if not self.found:
            return

        if not self.name_input.text().strip():
            set_status(self.status_label, "Give the deck a name before importing it.", "error")
            self.name_input.setFocus()
            return

        # The chosen commander moves from the main deck to the Commander section
        chosen = self.commander_input.currentData() if self.commander_input.isVisible() else None
        if chosen is not None:
            entry, _ = self.found[chosen]
            if entry.quantity == 1:
                entry.section = "commander"

        self.created_deck_id = decks.create_deck_from_list(
            self.name_input.text(), self.format_input.currentData(), self.found
        )
        self.accept()
