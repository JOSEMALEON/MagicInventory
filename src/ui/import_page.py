from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.list_service import (
    add_found_cards,
    parse_card_list,
    read_list_file,
    resolve_entries,
)
from services.card_service import ScryfallError
from services.price_service import format_money
from src.ui.widgets import set_status, styled_panel

EXAMPLE_LIST = """1 Sol Ring
4 Lightning Bolt
1 Wurmcoil Engine (2XM) 308"""

# How many problems are listed in the warning dialog (all of them are in the page)
MAX_PROBLEMS_IN_DIALOG = 12


def plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


class ImportPage(QWidget):
    """
    Page to add many cards at once: paste a list or load a .txt/.csv file,
    check it against Scryfall and add the cards found.

    on_cards_added() is called after adding, so the window can refresh the
    collection. get_currency() returns the currency chosen in the collection.
    """

    def __init__(self, background, on_cards_added, get_currency):
        super().__init__()

        self.background = background
        self.on_cards_added = on_cards_added
        self.get_currency = get_currency

        # Result of the last check: [(ListEntry, Card)]
        self.found = []

        # Ignore check results if the list changed while checking
        self._check_id = 0

        # ---------- Header ----------

        title = QLabel("Import cards")
        title.setObjectName("pageTitle")

        hint = QLabel(
            "Paste a list with one card per line — “1 Sol Ring”, or “1 Sol Ring (CMM) 410” "
            "for an exact edition — or load a .txt / .csv file."
        )
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)

        # ---------- Left: the list ----------

        list_caption = QLabel("CARD LIST")
        list_caption.setObjectName("fieldLabel")

        self.list_input = QPlainTextEdit()
        self.list_input.setObjectName("listInput")
        self.list_input.setPlaceholderText(EXAMPLE_LIST)
        self.list_input.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.list_input.textChanged.connect(self._on_list_changed)

        self.line_count_label = QLabel()
        self.line_count_label.setObjectName("mutedSmall")

        load_button = QPushButton("Load file…")
        load_button.setCursor(Qt.CursorShape.PointingHandCursor)
        load_button.clicked.connect(self.load_file)

        clear_button = QPushButton("Clear")
        clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_button.clicked.connect(self.list_input.clear)

        self.check_button = QPushButton("Check list")
        self.check_button.setObjectName("primaryButton")
        self.check_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.check_button.clicked.connect(self.check_list)

        list_buttons = QHBoxLayout()
        list_buttons.setSpacing(10)
        list_buttons.addWidget(load_button)
        list_buttons.addWidget(clear_button)
        list_buttons.addWidget(self.line_count_label)
        list_buttons.addStretch()
        list_buttons.addWidget(self.check_button)

        left = QVBoxLayout()
        left.setContentsMargins(20, 20, 20, 20)
        left.setSpacing(10)
        left.addWidget(list_caption)
        left.addWidget(self.list_input)
        left.addLayout(list_buttons)

        left_panel = styled_panel("cardPanel", left)

        # ---------- Right: result ----------

        result_caption = QLabel("RESULT")
        result_caption.setObjectName("fieldLabel")

        self.status_label = QLabel("Check the list to see which cards will be added.")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)

        self.results_table = QTableWidget()
        self.results_table.setObjectName("resultsTable")
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(["Qty", "Name", "Edition", "Price"])
        self.results_table.setShowGrid(False)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.results_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.verticalHeader().setDefaultSectionSize(34)

        header = self.results_table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.results_table.setColumnWidth(0, 50)
        self.results_table.setColumnWidth(3, 90)

        problems_caption = QLabel("PROBLEMS")
        problems_caption.setObjectName("fieldLabel")

        # One line per problem: "Line 4: “Bronze Guardan” not found. Did you mean…"
        self.problem_list = QListWidget()
        self.problem_list.setObjectName("problemList")
        self.problem_list.setWordWrap(True)
        self.problem_list.setMaximumHeight(170)

        self.problems_box = QWidget()
        problems_layout = QVBoxLayout()
        problems_layout.setContentsMargins(0, 6, 0, 0)
        problems_layout.setSpacing(6)
        problems_layout.addWidget(problems_caption)
        problems_layout.addWidget(self.problem_list)
        self.problems_box.setLayout(problems_layout)
        self.problems_box.hide()

        self.add_button = QPushButton("Add to Collection")
        self.add_button.setObjectName("primaryButton")
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.setEnabled(False)
        self.add_button.clicked.connect(self.add_cards)

        right = QVBoxLayout()
        right.setContentsMargins(20, 20, 20, 20)
        right.setSpacing(10)
        right.addWidget(result_caption)
        right.addWidget(self.status_label)
        right.addWidget(self.results_table, 1)
        right.addWidget(self.problems_box)
        right.addWidget(self.add_button)

        right_panel = styled_panel("cardPanel", right)

        columns = QHBoxLayout()
        columns.setSpacing(20)
        columns.addWidget(left_panel, 2)
        columns.addWidget(right_panel, 3)

        page_layout = QVBoxLayout()
        page_layout.setContentsMargins(32, 28, 32, 28)
        page_layout.setSpacing(14)
        page_layout.addWidget(title)
        page_layout.addWidget(hint)
        page_layout.addLayout(columns, 1)

        self.setLayout(page_layout)
        self._update_line_count()

    # ==================================
    # LIST INPUT
    # ==================================

    def _update_line_count(self):

        lines = [line for line in self.list_input.toPlainText().splitlines() if line.strip()]
        self.line_count_label.setText(plural(len(lines), "line") if lines else "")
        self.check_button.setEnabled(bool(lines))

    def _on_list_changed(self):

        self._update_line_count()

        # The previous result doesn't match the list anymore
        if self.found or self.problem_list.count():
            self._clear_results()
            set_status(self.status_label, "The list changed. Check it again before adding.")

        # Ignore a check still running for the old text
        self._check_id += 1
        self.check_button.setText("Check list")

    def load_file(self):

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load card list",
            str(Path.home()),
            "Card lists (*.txt *.csv);;Text list (*.txt);;CSV spreadsheet (*.csv)",
        )

        if not path:
            return

        try:
            text, problems = read_list_file(path)
        except OSError as error:
            set_status(self.status_label, f"Could not read the file: {error}", "error")
            return

        self.list_input.setPlainText(text)

        if problems:
            # Errors found while reading the CSV (the valid rows are in the list)
            self._show_problems(problems)
            set_status(
                self.status_label,
                f"Loaded {Path(path).name} with {plural(len(problems), 'problem')}.",
                "error",
            )
            self._warn(problems)
        else:
            set_status(self.status_label, f"Loaded {Path(path).name}. Check the list to continue.")

    # ==================================
    # CHECK
    # ==================================

    def check_list(self):

        entries, syntax_problems = parse_card_list(self.list_input.toPlainText())

        self._clear_results()

        if not entries:
            self._show_problems(syntax_problems)
            set_status(self.status_label, "No valid lines to check.", "error")
            if syntax_problems:
                self._warn(syntax_problems)
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

        self._finish_check()

        found, missing = result
        problems = sorted(syntax_problems + missing, key=lambda problem: problem.line)

        self.found = found
        self._show_found(found)
        self._show_problems(problems)

        copies = sum(entry.quantity for entry, _ in found)

        if found:
            self.add_button.setText(f"Add {plural(copies, 'card')} to Collection")
            self.add_button.setEnabled(True)

        if problems:
            set_status(
                self.status_label,
                f"{plural(len(found), 'line')} OK, {plural(len(problems), 'problem')}. "
                "Fix the list and check again, or add only the cards found.",
                "error",
            )
            self._warn(problems)
        else:
            set_status(
                self.status_label,
                f"All {plural(len(found), 'line')} found ({plural(copies, 'card')}).",
                "success",
            )

    def _on_check_error(self, check_id, error):

        if check_id != self._check_id:
            return

        self._finish_check()

        if isinstance(error, ScryfallError):
            text = "Could not connect to Scryfall. Check your connection and try again."
        else:
            text = f"Unexpected error: {error}"

        set_status(self.status_label, text, "error")

    def _finish_check(self):

        self.check_button.setText("Check list")
        self._update_line_count()

    # ==================================
    # RESULTS
    # ==================================

    def _clear_results(self):

        self.found = []
        self.results_table.setRowCount(0)
        self.problem_list.clear()
        self.problems_box.hide()
        self.add_button.setEnabled(False)
        self.add_button.setText("Add to Collection")

    def _show_found(self, found):

        currency = self.get_currency()
        self.results_table.setRowCount(len(found))

        for row, (entry, card) in enumerate(found):

            quantity = QTableWidgetItem(f"{entry.quantity}")
            quantity.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            price = QTableWidgetItem(format_money(card.price(currency), currency))
            price.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            self.results_table.setItem(row, 0, quantity)
            self.results_table.setItem(row, 1, QTableWidgetItem(card.name))
            self.results_table.setItem(row, 2, QTableWidgetItem(card.printing_label))
            self.results_table.setItem(row, 3, price)

    def _show_problems(self, problems):

        self.problem_list.clear()

        for problem in problems:
            self.problem_list.addItem(str(problem))

        self.problems_box.setVisible(bool(problems))

    def _warn(self, problems):
        """
        Pop-up naming the lines/cards that failed (all of them stay listed in the page).
        """

        shown = [f"• {problem}" for problem in problems[:MAX_PROBLEMS_IN_DIALOG]]
        hidden = len(problems) - len(shown)

        if hidden:
            shown.append(f"…and {hidden} more (see the Problems list).")

        QMessageBox.warning(
            self,
            "Problems in the card list",
            f"{plural(len(problems), 'line')} could not be read or found:\n\n" + "\n".join(shown),
        )

    # ==================================
    # ADD
    # ==================================

    def add_cards(self):

        if not self.found:
            return

        found = self.found
        copies = add_found_cards(found)

        # Avoid adding the same cards twice by clicking again
        self._clear_results()

        set_status(
            self.status_label,
            f"Added {plural(copies, 'card')} ({plural(len(found), 'line')}) to your collection.",
            "success",
        )

        self.on_cards_added()
