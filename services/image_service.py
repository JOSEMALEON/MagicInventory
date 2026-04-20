from PySide6.QtGui import QPixmap
import requests


def get_card_pixmap(url, width=None, height=None):
    try:
        response = requests.get(url)

        if response.status_code == 200:
            pixmap = QPixmap()
            pixmap.loadFromData(response.content)

            if width and height:
                return pixmap.scaled(width, height)
            elif width:
                return pixmap.scaledToWidth(width)

            return pixmap

    except Exception:
        pass

    return None