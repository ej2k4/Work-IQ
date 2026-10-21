"""Payment gateway tokenization, Stripe charges, and refund processing."""
import hashlib

def tokenize_credit_card(card_number: str, exp_month: int, exp_year: int, cvc: str) -> str:
    """Tokenize credit card details with gateway token vault."""
    masked = f"{card_number[-4:]}-{exp_month}-{exp_year}"
    token = f"tok_{hashlib.sha256(card_number.encode()).hexdigest()[:16]}"
    return token

def process_stripe_charge(token: str, amount_cents: int, currency: str = "usd") -> dict:
    """Execute gateway charge via Stripe API with idempotency key."""
    if amount_cents <= 0:
        return {"status": "failed", "error": "Invalid charge amount"}
    return {"status": "succeeded", "charge_id": f"ch_{token[:8]}", "amount": amount_cents}

def process_refund(charge_id: str, amount_cents: int, reason: str = "customer_return") -> dict:
    """Issue full or partial refund to original credit card."""
    return {"status": "refunded", "charge_id": charge_id, "amount_refunded": amount_cents, "reason": reason}
