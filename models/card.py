class Card:

    def __init__(
        self,
        name,
        set_name,
        type_line,
        mana_cost,
        rarity,
        image_url,
        quantity=1,
        scryfall_id=None,
        set_code=None,
        collector_number=None,
        prints_search_uri=None,
        id=None,
        price_eur=None,
        price_eur_foil=None,
        price_usd=None,
        price_usd_foil=None,
        prices_updated_at=None,
        cmc=None,
        colors=None,
        color_identity=None,
        legalities=None,
        oracle_text=None,
        foil=False,
        finishes=None,
        collection_id=None,
    ):

        self.name = name
        self.set_name = set_name
        self.type_line = type_line
        self.mana_cost = mana_cost
        self.rarity = rarity
        self.image_url = image_url
        self.quantity = quantity

        # Identify one exact printing (edition + collector number) of the card
        self.scryfall_id = scryfall_id
        self.set_code = set_code
        self.collector_number = collector_number

        # Scryfall URL that lists every printing of this card (not stored in the DB)
        self.prints_search_uri = prints_search_uri

        # Row id in the database (None for cards that come from Scryfall)
        self.id = id

        # Market prices from Scryfall (None = no price for that finish/currency)
        self.price_eur = price_eur
        self.price_eur_foil = price_eur_foil
        self.price_usd = price_usd
        self.price_usd_foil = price_usd_foil
        # ISO date-time of the last price update (None if never updated)
        self.prices_updated_at = prices_updated_at

        # Gameplay data used by the deck builder
        self.cmc = cmc                                  # mana value, e.g. 3.0
        self.colors = colors or []                      # e.g. ["U", "R"]
        self.color_identity = color_identity or []      # e.g. ["U", "R", "G"]
        self.legalities = legalities or {}              # e.g. {"commander": "legal", ...}
        self.oracle_text = oracle_text or ""            # rules text (faces joined by "//")

        # Collection copies: foil or not. Each finish is its own collection row.
        self.foil = bool(foil)

        # Finishes this printing exists in, from Scryfall: ["nonfoil", "foil",
        # "etched"]. Only known for cards that come from Scryfall (not stored).
        self.finishes = finishes or []

        # Collection the row belongs to (None = the first one, "Main collection")
        self.collection_id = collection_id


    @property
    def can_be_foil(self):
        """False only when Scryfall says this printing has no foil version."""
        return not self.finishes or "foil" in self.finishes or "etched" in self.finishes


    @property
    def only_foil(self):
        """True when this printing exists only in foil (no normal version)."""
        return bool(self.finishes) and "nonfoil" not in self.finishes


    def price(self, currency="EUR"):
        """
        Price of one copy in "EUR" or "USD" for its finish: foil copies use the
        foil price, the rest the normal one. If that price is missing, the
        other one is used. Return None if Scryfall has no price.
        """

        if currency == "USD":
            normal, foil = self.price_usd, self.price_usd_foil
        else:
            normal, foil = self.price_eur, self.price_eur_foil

        first, second = (foil, normal) if self.foil else (normal, foil)
        return first if first is not None else second


    def value(self, currency="EUR"):
        """
        price x quantity, or None if there is no price.
        """

        price = self.price(currency)
        return None if price is None else price * (self.quantity or 0)


    @property
    def printing_label(self):
        """
        Human-readable edition, e.g. "Commander Masters (CMM #410)"
        """

        if self.set_code and self.collector_number:
            return f"{self.set_name} ({self.set_code.upper()} #{self.collector_number})"

        return self.set_name or ""


    def __str__(self):

        return f"""
Name: {self.name}
Set: {self.printing_label}
Type: {self.type_line}
Mana Cost: {self.mana_cost}
Rarity: {self.rarity}
Quantity: {self.quantity}
Image: {self.image_url}
"""
