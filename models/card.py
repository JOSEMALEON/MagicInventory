class Card:

    def __init__(self, name, set_name, type_line, mana_cost, rarity, image_url, quantity=1):

        self.name = name
        self.set_name = set_name
        self.type_line = type_line
        self.mana_cost = mana_cost
        self.rarity = rarity
        self.image_url = image_url
        self.quantity = quantity


    def __str__(self):

        return f"""
Name: {self.name}
Set: {self.set_name}
Type: {self.type_line}
Mana Cost: {self.mana_cost}
Rarity: {self.rarity}
Quantity: {self.quantity}
Image: {self.image_url}
"""