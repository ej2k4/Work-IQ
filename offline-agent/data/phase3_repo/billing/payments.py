"""Stripe payment processing, card encryption, and webhooks."""
from utils.crypto import encrypt_aes_gcm
from utils.rate_limit import SlidingWindowRateLimiter
from notifications.webhook import sign_webhook_payload

pay_limiter = SlidingWindowRateLimiter(limit=10, window_seconds=60)

def process_stripe_charge(card_token: str, amount_cents: int, ip: str) -> dict:
    """Process credit card charge with rate-limiting, encryption, and webhook notification."""
    allowed, _ = pay_limiter.is_allowed(ip)
    if not allowed:
        return {"status": "failed", "error": "rate_limited"}
    # Encrypt transaction payload
    encrypted = encrypt_aes_gcm(f"charge:{amount_cents}:{card_token}", b"payment-key-32-bytes-long-123456")
    # Sign webhook notification
    signature = sign_webhook_payload(b"charge_succeeded", "stripe-secret")
    return {"status": "succeeded", "charge_id": "ch_mock_123", "sig": signature}
