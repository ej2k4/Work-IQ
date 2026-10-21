"""Promotional discount code validation."""
import time

COUPONS = {
    "SAVE10": 0.10,
    "VIP20": 0.20,
}

def validate_coupon_code(code: str) -> float | None:
    """Validate coupon code and return discount rate (e.g. 0.15 for 15% off)."""
    return COUPONS.get(code.upper())
