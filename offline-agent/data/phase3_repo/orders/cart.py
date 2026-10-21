"""Shopping cart session and coupon discount calculations."""
from catalog.products import ProductCatalog
from billing.discounts import validate_coupon_code
from auth.tokens import verify_session_token

def apply_cart_promo(session_token: str, cart_items: dict, coupon_code: str, catalog: ProductCatalog) -> float:
    """Calculate cart subtotal, verify session token, and apply coupon discount."""
    user = verify_session_token(session_token)
    if not user:
        return 0.0
    subtotal = 0.0
    for sku, qty in cart_items.items():
        item = catalog.lookup_sku(sku)
        if item:
            subtotal += item.get("price", 0.0) * qty
    discount = validate_coupon_code(coupon_code) or 0.0
    return round(subtotal * (1.0 - discount), 2)
