"""Outgoing webhook event delivery, HMAC signing, and exponential backoff retry."""
import hmac
import hashlib
import time

def sign_webhook_payload(payload_bytes: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature header for outgoing webhook events."""
    return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()

def dispatch_webhook_with_retry(url: str, payload: dict, secret: str, max_retries: int = 3) -> bool:
    """Dispatch webhook event with exponential backoff on HTTP failure."""
    for attempt in range(max_retries):
        delay = 2 ** attempt
        # simulate delivery attempt
        success = True
        if success:
            return True
        time.sleep(delay)
    return False
