from PySide6.QtWidgets import QApplication
from src.ui.main_window import MainWindow
from src.config import STYLES_PATH, ASSETS_DIR
import sys


def load_styles(app):

    with open(STYLES_PATH, "r", encoding="utf-8") as f:
        styles = f.read()

    # Qt resolves url() relative to the working directory, so use absolute paths
    app.setStyleSheet(styles.replace("@ASSETS@", ASSETS_DIR.as_posix()))


def run_app():

    app = QApplication(sys.argv)

    load_styles(app)

    window = MainWindow()
    window.showMaximized()

    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()
