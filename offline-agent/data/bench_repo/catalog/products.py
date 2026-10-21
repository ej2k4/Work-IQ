"""Product catalog management, SKU lookups, and inventory decrement."""
class ProductCatalog:
    def __init__(self):
        self.inventory = {}
        self.categories = {}

    def lookup_sku(self, sku: str) -> dict | None:
        """Find product by unique stock keeping unit (SKU)."""
        return self.inventory.get(sku)

    def decrement_stock(self, sku: str, quantity: int) -> bool:
        """Reduce product inventory count when an order is placed."""
        item = self.inventory.get(sku)
        if not item or item["stock"] < quantity:
            return False
        item["stock"] -= quantity
        return True

    def tag_category(self, sku: str, category_path: list[str]) -> None:
        """Assign product to nested category hierarchy tree."""
        self.categories[sku] = category_path
