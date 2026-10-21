"""HMAC signature computation for outgoing webhooks."""
import hmac
import hashlib

def sign_webhook_payload(payload_bytes: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature for outgoing webhook event."""
    return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
