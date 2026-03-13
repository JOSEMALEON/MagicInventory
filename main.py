from PySide6.QtWidgets import QApplication
from src.ui.main_window import MainWindow
import sys


def load_styles(app):

    with open("src/ui/styles.qss", "r") as f:
        app.setStyleSheet(f.read())


def run_app():

    app = QApplication(sys.argv)

    load_styles(app)

    window = MainWindow()
    window.showMaximized()

    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()