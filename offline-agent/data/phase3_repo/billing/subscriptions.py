"""Recurring monthly recurring billing worker."""
from billing.payments import process_stripe_charge

def process_subscription_renewal(user_id: str, card_token: str, plan_amount_cents: int) -> bool:
    """Execute automated recurring charge for customer subscription."""
    res = process_stripe_charge(card_token, plan_amount_cents, ip="127.0.0.1")
    return res.get("status") == "succeeded"
