"""Shopping cart management, item quantity updates, and merging duplicates."""
class ShoppingCart:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.items = {}

    def update_quantity(self, sku: str, quantity: int) -> None:
        """Update cart item quantity or remove item if quantity <= 0."""
        if quantity <= 0:
            self.items.pop(sku, None)
        else:
            self.items[sku] = quantity

    def merge_duplicate_items(self, incoming_items: dict) -> None:
        """Merge items from guest cart into authenticated user cart."""
        for sku, qty in incoming_items.items():
            self.items[sku] = self.items.get(sku, 0) + qty

    def get_cart_total(self, price_lookup: dict) -> float:
        """Compute subtotal for all items in shopping cart."""
        return sum(qty * price_lookup.get(sku, 0.0) for sku, qty in self.items.items())
