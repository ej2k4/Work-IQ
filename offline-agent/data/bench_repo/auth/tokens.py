"""Session token generation, verification, and revocation."""
import time
import hmac
import hashlib
import json
import base64

SECRET_KEY = "super-secret-key"

def generate_session_token(user_id: str, ttl_seconds: int = 3600) -> str:
    """Generate a signed session token containing user_id and expiration."""
    payload = {"user_id": user_id, "exp": int(time.time()) + ttl_seconds}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = hmac.new(SECRET_KEY.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{sig}"

def verify_session_token(token: str) -> dict | None:
    """Validate token signature and expiration, returning the payload if valid."""
    parts = token.split(".")
    if len(parts) != 2:
        return None
    encoded, sig = parts
    expected_sig = hmac.new(SECRET_KEY.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None
    payload = json.loads(base64.urlsafe_b64decode(encoded.encode()).decode())
    if time.time() > payload.get("exp", 0):
        return None
    return payload

def revoke_session_token(token: str, blacklist_set: set) -> bool:
    """Add session token to revocation blacklist on user logout."""
    blacklist_set.add(token)
    return True
