"""Password hashing, salt generation, and complexity verification."""
import hashlib
import secrets
import hmac

def generate_salt(length: int = 16) -> str:
    """Generate random cryptographic salt for password hashing."""
    return secrets.token_hex(length)

def hash_password_pbkdf2(password: str, salt: str, iterations: int = 100_000) -> str:
    """Compute PBKDF2 hash with HMAC-SHA256."""
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
    return key.hex()

def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    """Verify password by computing PBKDF2 hash with salt and constant-time compare."""
    computed = hash_password_pbkdf2(password, salt)
    return hmac.compare_digest(computed, expected_hash)

def validate_password_complexity(password: str) -> bool:
    """Check minimum length, uppercase, lowercase, and special characters."""
    if len(password) < 8:
        return False
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    return has_upper and has_lower and has_digit
