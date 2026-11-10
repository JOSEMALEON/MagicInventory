from pathlib import Path

# =============================
# PATHS
# =============================

# Project root (the folder that contains main.py). Built from this file's
# location so the app works no matter which directory it is launched from.
BASE_DIR = Path(__file__).resolve().parent.parent

DB_PATH = BASE_DIR / "magic_inventory.db"
STYLES_PATH = BASE_DIR / "src" / "ui" / "styles.qss"

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

COLORS = {
    "bg_deep": "#1E2A4A",
    "bg_panel": "#3F5FA8",
    "primary": "#7093EF",
    "hover": "#9FB8F5",
    "highlight": "#D6E1FF",
    "text": "#FFFFFF"
}
