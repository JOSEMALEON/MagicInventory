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
