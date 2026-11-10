from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
import requests

from src.config import REQUEST_TIMEOUT, HTTP_HEADERS


def get_card_pixmap(url, width=None, height=None):
    """
    Download a card image and return it as a QPixmap, or None if it fails.
    """

    if not url:
        return None

    try:
        response = requests.get(url, headers=HTTP_HEADERS, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None

    pixmap = QPixmap()

    if not pixmap.loadFromData(response.content):
        return None

    if width and height:
        return pixmap.scaled(
            width, height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    if width:
        return pixmap.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)

    return pixmap
