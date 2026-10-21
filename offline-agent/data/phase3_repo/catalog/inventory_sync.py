"""Warehouse inventory synchronization worker."""
from catalog.products import ProductCatalog

def sync_warehouse_shipment(catalog: ProductCatalog, manifest: list[dict]) -> bool:
    """Synchronize shipment by decrementing product stock."""
    for item in manifest:
        sku = item["sku"]
        qty = item["qty"]
        if not catalog.decrement_stock(sku, qty):
            return False
    return True
