"""Coupon promo validation and percentage discount calculation."""
import time

COUPONS = {
    "SUMMER20": {"type": "percent", "value": 0.20, "expires": 1893456000},
    "FLAT10": {"type": "flat", "value": 10.0, "expires": 1893456000},
}

def validate_coupon_code(code: str) -> dict | None:
    """Validate coupon promo code and check expiration timestamp."""
    coupon = COUPONS.get(code.upper())
    if not coupon:
        return None
    if time.time() > coupon["expires"]:
        return None
    return coupon

def apply_percentage_discount(subtotal: float, discount_percent: float) -> float:
    """Apply percentage discount against order subtotal."""
    discount = subtotal * discount_percent
    return round(max(0.0, subtotal - discount), 2)
