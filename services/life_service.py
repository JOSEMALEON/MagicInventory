"""
Life counter for games of up to 6 players: life, commander damage (with
partner commanders), poison, experience, energy, rad, commander tax and the
Monarch / Initiative / City's blessing markers.

Pure logic (no Qt), so it can be tested on its own. The game is saved to
cache/life_game.json after every change, so closing the app doesn't lose it.
"""

import copy
import json
import os
import random
import tempfile
from dataclasses import asdict, dataclass, field

from src.config import BASE_DIR

GAME_FILE = BASE_DIR / "cache" / "life_game.json"

MIN_PLAYERS = 2
MAX_PLAYERS = 6

STARTING_LIFE_OPTIONS = (20, 30, 40)
DEFAULT_STARTING_LIFE = 40

# Rules that eliminate a player
LETHAL_COMMANDER_DAMAGE = 21
LETHAL_POISON = 10

# Commander tax: {2} more each time the commander was cast from the command zone
TAX_PER_CAST = 2

# Counters a player can have (key -> label shown in the panel)
COUNTERS = {
    "poison": "Poison",
    "experience": "Experience",
    "energy": "Energy",
    "rad": "Rad",
}

# Seat colors, in the app's palette
PLAYER_COLORS = ["#3B82F6", "#F87171", "#4ADE80", "#FBBF24", "#A78BFA", "#38BDF8"]

# How many undo steps are kept
MAX_UNDO = 200


@dataclass
class Player:
    name: str
    color: str
    life: int
    partner: bool = False                   # has two commanders (Partner, Background...)
    counters: dict = field(default_factory=lambda: {key: 0 for key in COUNTERS})
    # Times each commander was cast (index 0 = first, 1 = partner)
    casts: list = field(default_factory=lambda: [0, 0])
    city_blessing: bool = False
    # Damage received from each commander: {"<source index>:<commander 0|1>": amount}
    commander_damage: dict = field(default_factory=dict)

    def damage_from(self, source, commander=0):
        return self.commander_damage.get(f"{source}:{commander}", 0)

    def tax(self, commander=0):
        return self.casts[commander] * TAX_PER_CAST


@dataclass
class Game:
    players: list
    starting_life: int = DEFAULT_STARTING_LIFE
    monarch: int = None          # index of the player with the Monarch, or None
    initiative: int = None       # index of the player with the Initiative, or None
    first_player: int = None     # who starts (chosen at random), or None


# ==================================
# CREATE / LOAD / SAVE
# ==================================

def new_game(player_count=4, starting_life=DEFAULT_STARTING_LIFE, names=None):
    """A new game. Names default to "Player 1", "Player 2"..."""

    player_count = max(MIN_PLAYERS, min(MAX_PLAYERS, int(player_count)))
    names = list(names or [])

    players = [
        Player(
            name=names[index] if index < len(names) and names[index] else f"Player {index + 1}",
            color=PLAYER_COLORS[index % len(PLAYER_COLORS)],
            life=starting_life,
        )
        for index in range(player_count)
    ]

    return Game(players=players, starting_life=starting_life)


def game_to_dict(game):
    return asdict(game)


def game_from_dict(data):

    players = []
    for item in data.get("players", []):
        player = Player(**{key: item[key] for key in ("name", "color", "life")})
        player.partner = bool(item.get("partner", False))
        player.counters = {key: int(item.get("counters", {}).get(key, 0)) for key in COUNTERS}
        player.casts = list(item.get("casts", [0, 0]))[:2] + [0] * (2 - len(item.get("casts", [0, 0])[:2]))
        player.city_blessing = bool(item.get("city_blessing", False))
        player.commander_damage = {k: int(v) for k, v in item.get("commander_damage", {}).items()}
        players.append(player)

    return Game(
        players=players,
        starting_life=int(data.get("starting_life", DEFAULT_STARTING_LIFE)),
        monarch=data.get("monarch"),
        initiative=data.get("initiative"),
        first_player=data.get("first_player"),
    )


def save_game(game, path=None):
    """Write the game to disk (through a temporary file, never half-written)."""

    path = path or GAME_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        json.dump(game_to_dict(game), file, indent=1)
    os.replace(temp_name, path)


def load_game(path=None):
    """The saved game, or None if there isn't one (or it can't be read)."""

    path = path or GAME_FILE

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        game = game_from_dict(data)
    except (OSError, ValueError, KeyError, TypeError):
        return None

    return game if MIN_PLAYERS <= len(game.players) <= MAX_PLAYERS else None


# ==================================
# GAME LOGIC
# ==================================

class LifeCounter:
    """
    The current game plus an undo history. Every change is saved to disk
    (unless autosave is False, e.g. in tests).
    """

    def __init__(self, game=None, autosave=True, path=None):
        self.game = game or new_game()
        self.autosave = autosave
        self.path = path
        self._undo = []

    # ---------- History ----------

    def _remember(self):
        """Call before every change: keeps a copy to undo it."""
        self._undo.append(copy.deepcopy(self.game))
        if len(self._undo) > MAX_UNDO:
            self._undo.pop(0)

    def _changed(self):
        if self.autosave:
            save_game(self.game, self.path)

    def can_undo(self):
        return bool(self._undo)

    def undo(self):
        if self._undo:
            self.game = self._undo.pop()
            self._changed()

    # ---------- Whole game ----------

    def new_game(self, player_count, starting_life, keep_names=True):
        """Start again. Names, colors and partners of the seats are kept."""

        self._remember()

        old = self.game.players
        names = [player.name for player in old] if keep_names else None
        game = new_game(player_count, starting_life, names)

        for index, player in enumerate(game.players):
            if keep_names and index < len(old):
                player.color = old[index].color
                player.partner = old[index].partner

        self.game = game
        self._changed()

    def choose_first_player(self):
        """Pick who starts at random. Return the player's index."""

        self._remember()
        self.game.first_player = random.randrange(len(self.game.players))
        self._changed()
        return self.game.first_player

    # ---------- Life ----------

    def change_life(self, index, delta):
        if delta:
            self._remember()
            self.game.players[index].life += delta
            self._changed()

    # ---------- Commander damage ----------

    def change_commander_damage(self, target, source, commander, delta, affects_life=True):
        """
        Commander damage dealt to `target` by `source`'s commander (0 or 1).
        It never goes below 0. Commander damage is also life loss, so by
        default the target's life changes by the same amount.
        """

        if target == source or delta == 0:
            return

        player = self.game.players[target]
        key = f"{source}:{commander}"
        current = player.commander_damage.get(key, 0)
        new_value = max(0, current + delta)
        applied = new_value - current

        if applied == 0:
            return

        self._remember()
        player.commander_damage[key] = new_value
        if affects_life:
            player.life -= applied
        self._changed()

    def set_partner(self, index, partner):
        """
        Give a player two commanders (Partner, Background, Friends forever...)
        or one. Turning it off adds the second commander's damage and casts
        to the first, so nothing is lost.
        """

        player = self.game.players[index]
        if player.partner == partner:
            return

        self._remember()
        player.partner = partner

        if not partner:
            for other in self.game.players:
                second = other.commander_damage.pop(f"{index}:1", 0)
                if second:
                    key = f"{index}:0"
                    other.commander_damage[key] = other.commander_damage.get(key, 0) + second
            player.casts = [player.casts[0] + player.casts[1], 0]

        self._changed()

    # ---------- Counters and markers ----------

    def change_counter(self, index, counter, delta):
        player = self.game.players[index]
        new_value = max(0, player.counters[counter] + delta)
        if new_value != player.counters[counter]:
            self._remember()
            player.counters[counter] = new_value
            self._changed()

    def change_casts(self, index, commander, delta):
        """Times a commander was cast (its tax is 2 per cast)."""
        player = self.game.players[index]
        new_value = max(0, player.casts[commander] + delta)
        if new_value != player.casts[commander]:
            self._remember()
            player.casts[commander] = new_value
            self._changed()

    def toggle_city_blessing(self, index):
        self._remember()
        player = self.game.players[index]
        player.city_blessing = not player.city_blessing
        self._changed()

    def toggle_marker(self, marker, index):
        """
        Monarch / Initiative: only one player can have each one. Giving it
        to a player takes it from the previous one; clicking the holder
        removes it.
        """

        self._remember()
        current = getattr(self.game, marker)
        setattr(self.game, marker, None if current == index else index)
        self._changed()

    def rename(self, index, name):
        name = name.strip()
        if name and name != self.game.players[index].name:
            self._remember()
            self.game.players[index].name = name
            self._changed()

    # ---------- Elimination ----------

    def elimination_reason(self, index):
        """
        Why the player has lost ("Life", "Poison", "Commander damage from X"),
        or None if they are still in the game.
        """

        player = self.game.players[index]

        if player.life <= 0:
            return "0 life"

        if player.counters["poison"] >= LETHAL_POISON:
            return f"{LETHAL_POISON} poison counters"

        for key, damage in player.commander_damage.items():
            if damage >= LETHAL_COMMANDER_DAMAGE:
                source, commander = (int(part) for part in key.split(":"))
                if source < len(self.game.players):
                    name = self.game.players[source].name
                    suffix = " (B)" if commander == 1 else ""
                    return f"{LETHAL_COMMANDER_DAMAGE} commander damage from {name}{suffix}"

        return None
