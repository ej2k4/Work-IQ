"""Password hashing and brute-force rate-limiting."""
import hashlib
import secrets
from utils.rate_limit import SlidingWindowRateLimiter
from utils.crypto import encrypt_aes_gcm

limiter = SlidingWindowRateLimiter(limit=5, window_seconds=60)

def verify_user_login(username: str, password: str, salt: str, expected_hash: str, ip: str) -> bool:
    """Verify password while enforcing IP rate limiting and encrypting logs."""
    allowed, _ = limiter.is_allowed(ip)
    if not allowed:
        return False
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    matched = (key.hex() == expected_hash)
    if not matched:
        encrypt_aes_gcm(f"failed_login:{username}", b"secret-key-32-bytes-long-12345678")
    return matched
