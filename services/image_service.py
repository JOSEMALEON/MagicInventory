import hashlib
import os
import tempfile

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QImage, QPainter, QPainterPath, QPixmap
import requests

from src.config import REQUEST_TIMEOUT, HTTP_HEADERS, IMAGE_CACHE_DIR


def _cache_path(url):
    """
    One file per image URL. Scryfall adds a version number to the URL
    (e.g. "...jpg?1562..."), so an updated image gets a new cache file.
    """

    name = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return IMAGE_CACHE_DIR / f"{name}.jpg"


def _save_to_cache(path, data):
    """
    Write to a temporary file and rename it, so another thread never
    reads a half-written image.
    """

    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")

    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
        os.replace(temp_name, path)
    except OSError:
        # The cache is only an optimisation: ignore disk errors
        try:
            os.remove(temp_name)
        except OSError:
            pass


def _get_image_bytes(url):
    """
    Return the image bytes from the disk cache, downloading them the first time.
    Return None if the image can't be obtained.
    """

    path = _cache_path(url)

    if path.exists():
        return path.read_bytes()

    try:
        response = requests.get(url, headers=HTTP_HEADERS, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None

    _save_to_cache(path, response.content)

    return response.content


def art_crop_url(image_url):
    """
    URL of the illustration only ("art crop") for a Scryfall card image URL:
    .../normal/front/... -> .../art_crop/front/...  None if it isn't a Scryfall image.
    """

    if not image_url or "/normal/" not in image_url:
        return None

    return image_url.replace("/normal/", "/art_crop/", 1)


def load_card_image(url, width=None, height=None, rounded=True):
    """
    Return the card image as a scaled QImage, or None if it fails.

    Safe to call from a background thread (QImage, unlike QPixmap, can be
    used outside the GUI thread). Convert it with to_pixmap() in the GUI thread.
    """

    if not url:
        return None

    data = _get_image_bytes(url)

    if not data:
        return None

    image = QImage()

    if not image.loadFromData(data):
        # Corrupt cache file: delete it so it is downloaded again next time
        _cache_path(url).unlink(missing_ok=True)
        return None

    if width and height:
        image = image.scaled(
            width, height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    elif width:
        image = image.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)

    return _round_corners(image) if rounded else image


def _round_corners(image):
    """
    Return a copy of the image with transparent rounded corners, like a
    real card (the radius is about 4.5% of the card width).
    """

    radius = image.width() * 0.045

    rounded = QImage(image.size(), QImage.Format.Format_ARGB32_Premultiplied)
    rounded.fill(Qt.GlobalColor.transparent)

    path = QPainterPath()
    path.addRoundedRect(QRectF(rounded.rect()), radius, radius)

    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setClipPath(path)
    painter.drawImage(0, 0, image)
    painter.end()

    return rounded


def to_pixmap(image):
    """
    Convert a QImage to a QPixmap. Must be called in the GUI thread.
    """

    return QPixmap.fromImage(image)
