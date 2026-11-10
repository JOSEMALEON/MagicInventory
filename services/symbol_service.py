"""
Mana symbols ({W}, {2}, {W/U}, {G/P}...) as SVG files.

The first time, the list of symbols and their SVGs are downloaded from
Scryfall to cache/symbols/. After that everything is read from disk.
"""

import json
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor

import requests

from api.scryfall_api import get_symbology
from src.config import HTTP_HEADERS, REQUEST_TIMEOUT, SYMBOL_CACHE_DIR

# {"{W}": "W.svg", ...}: which file holds each symbol
INDEX_FILE = SYMBOL_CACHE_DIR / "symbols.json"

SYMBOL_PATTERN = re.compile(r"\{[^}]+\}")

DOWNLOAD_THREADS = 8

_index = None


def _load_index():
    """The symbol -> file name map saved on disk, or {}."""

    global _index

    if _index is None:
        try:
            _index = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _index = {}

    return _index


def _file_name(svg_url):
    """https://svgs.scryfall.io/card-symbols/WU.svg?1234 -> WU.svg"""
    return svg_url.split("?")[0].rsplit("/", 1)[-1]


def _save(path, data):
    """Write through a temporary file so a half-written SVG is never read."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")

    with os.fdopen(fd, "wb") as file:
        file.write(data)

    os.replace(temp_name, path)


def symbols_ready():
    """True when the symbols were already downloaded (nothing to do)."""

    index = _load_index()

    return bool(index) and all((SYMBOL_CACHE_DIR / name).exists() for name in index.values())


def ensure_symbols():
    """
    Download the symbol list and any missing SVG (network: call it from a
    background thread). Return how many files were downloaded.
    Raise ScryfallError if the symbol list can't be obtained.
    """

    global _index

    if symbols_ready():
        return 0

    symbology = get_symbology()
    index = {symbol: _file_name(url) for symbol, url in symbology.items()}

    missing = [
        (url, SYMBOL_CACHE_DIR / index[symbol])
        for symbol, url in symbology.items()
        if not (SYMBOL_CACHE_DIR / index[symbol]).exists()
    ]

    # The SVGs come from Scryfall's image CDN (no API rate limit), so a few
    # downloads at once: ~3 s instead of ~30 s for the 84 symbols
    with ThreadPoolExecutor(max_workers=DOWNLOAD_THREADS) as pool:
        downloaded = sum(pool.map(lambda job: _download(*job), missing))

    _save(INDEX_FILE, json.dumps(index, indent=1).encode("utf-8"))
    _index = index

    return downloaded


def _download(url, path):
    """Download one SVG. Return 1 if it was saved, 0 otherwise."""

    try:
        response = requests.get(url, headers=HTTP_HEADERS, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        return 0

    if response.status_code != 200:
        return 0

    _save(path, response.content)
    return 1


def split_mana_cost(mana_cost):
    """
    "{2}{W}{U} // {R}" -> [["{2}", "{W}", "{U}"], ["{R}"]] (one list per face).
    """

    if not mana_cost:
        return []

    return [SYMBOL_PATTERN.findall(face) for face in mana_cost.split(" // ")]


def symbol_path(symbol):
    """Path of the SVG for "{W}", or None if it isn't downloaded."""

    name = _load_index().get(symbol)

    if not name:
        return None

    path = SYMBOL_CACHE_DIR / name
    return path if path.exists() else None
