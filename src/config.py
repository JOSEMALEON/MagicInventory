from pathlib import Path

# =============================
# PATHS
# =============================

# Project root (the folder that contains main.py). Built from this file's
# location so the app works no matter which directory it is launched from.
BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = BASE_DIR / "magic_inventory.db"
STYLES_PATH = BASE_DIR / "src" / "ui" / "styles.qss"
ASSETS_DIR = BASE_DIR / "assets"

# Downloaded card images, so each one is only downloaded once
IMAGE_CACHE_DIR = BASE_DIR / "cache" / "images"

# Mana symbols ({W}, {2}, {G/P}...) as SVG files, downloaded once from Scryfall
SYMBOL_CACHE_DIR = BASE_DIR / "cache" / "symbols"

# =============================
# NETWORK
# =============================

# Seconds to wait for Scryfall before giving up (avoids freezing the app forever)
REQUEST_TIMEOUT = 10

# Scryfall asks every client to identify itself with these headers
HTTP_HEADERS = {
    "User-Agent": "MagicInventory/0.1 (https://github.com/JOSEMALEON/MagicInventory)",
    "Accept": "application/json;q=0.9,*/*;q=0.8",
}

# =============================
# COLORS
# =============================

# The theme colors live in src/ui/styles.qss. These are only the ones the
# code needs to choose at runtime: the rarity badge of each card.
RARITY_COLORS = {
    "common": "#C9CED8",
    "uncommon": "#9FC3E0",
    "rare": "#E6C068",
    "mythic": "#F2753A",
    "special": "#C38BEA",
    "bonus": "#C38BEA",
}
