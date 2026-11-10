from dataclasses import dataclass, field

# Where a card lives inside a deck
SECTIONS = ("commander", "main", "sideboard", "maybeboard")

SECTION_LABELS = {
    "commander": "Commander",
    "main": "Main deck",
    "sideboard": "Sideboard",
    "maybeboard": "Maybeboard",
}


@dataclass
class Deck:
    """A deck (without its cards)."""

    id: int
    name: str
    format: str
    notes: str = ""
    created_at: str = None
    updated_at: str = None

    # Filled by get_decks(): cards in commander + main (copies)
    card_count: int = 0


@dataclass
class DeckCard:
    """
    One card line of a deck: a printing (card), its copies (card.quantity)
    and the section it belongs to. id is the row id in deck_cards.
    """

    id: int
    section: str
    card: object = field(repr=False)

    @property
    def quantity(self):
        return self.card.quantity or 0

    @property
    def name(self):
        return self.card.name
