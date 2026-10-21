"""Product catalog management and image uploads."""
from storage.s3 import generate_presigned_upload_url

class ProductCatalog:
    def __init__(self):
        self.items = {}

    def lookup_sku(self, sku: str) -> dict | None:
        """Find product specification by SKU."""
        return self.items.get(sku)

    def decrement_stock(self, sku: str, quantity: int) -> bool:
        """Deduct purchased quantity from inventory."""
        prod = self.items.get(sku)
        if not prod or prod.get("stock", 0) < quantity:
            return False
        prod["stock"] -= quantity
        return True

    def create_product_image_upload(self, sku: str) -> str:
        """Generate presigned S3 URL for product catalog image."""
        return generate_presigned_upload_url("catalog-bucket", f"images/{sku}.png")
