"""
bench_repo.py – Realistic 16-file benchmark repository for Phase 2 retrieval eval.

Simulates an unseen multi-service application with distinct domains:
auth, catalog, billing, orders, notifications, storage, utils.
Provides 20 ground-truth questions: 'Where is X handled?'
"""
from pathlib import Path

BENCH_FILES = {
    "auth/tokens.py": '''"""Session token generation, verification, and revocation."""
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
''',

    "auth/passwords.py": '''"""Password hashing, salt generation, and complexity verification."""
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
''',

    "auth/permissions.py": '''"""Role-based access control (RBAC) and permission checks."""
ROLES_PERMISSIONS = {
    "admin": {"view_catalog", "edit_catalog", "view_orders", "refund_orders", "manage_users"},
    "manager": {"view_catalog", "edit_catalog", "view_orders"},
    "customer": {"view_catalog", "create_order", "view_own_orders"},
}

def check_user_permission(role: str, action: str) -> bool:
    """Perform role-based access control (RBAC) permission check."""
    allowed_actions = ROLES_PERMISSIONS.get(role, set())
    return action in allowed_actions

def require_role(role: str, user_role: str) -> bool:
    """Check if user role matches or exceeds required role level."""
    hierarchy = {"admin": 3, "manager": 2, "customer": 1}
    return hierarchy.get(user_role, 0) >= hierarchy.get(role, 0)
''',

    "catalog/products.py": '''"""Product catalog management, SKU lookups, and inventory decrement."""
class ProductCatalog:
    def __init__(self):
        self.inventory = {}
        self.categories = {}

    def lookup_sku(self, sku: str) -> dict | None:
        """Find product by unique stock keeping unit (SKU)."""
        return self.inventory.get(sku)

    def decrement_stock(self, sku: str, quantity: int) -> bool:
        """Reduce product inventory count when an order is placed."""
        item = self.inventory.get(sku)
        if not item or item["stock"] < quantity:
            return False
        item["stock"] -= quantity
        return True

    def tag_category(self, sku: str, category_path: list[str]) -> None:
        """Assign product to nested category hierarchy tree."""
        self.categories[sku] = category_path
''',

    "catalog/search.py": '''"""Product catalog full-text search, price filtering, and popularity sorting."""
def filter_by_price_range(items: list[dict], min_price: float, max_price: float) -> list[dict]:
    """Filter product list by minimum and maximum price range."""
    return [p for p in items if min_price <= p.get("price", 0.0) <= max_price]

def full_text_search(items: list[dict], query: str) -> list[dict]:
    """Search products matching keywords in title or description."""
    keywords = query.lower().split()
    matched = []
    for item in items:
        text = f"{item.get('title', '')} {item.get('description', '')}".lower()
        if any(kw in text for kw in keywords):
            matched.append(item)
    return matched

def sort_by_popularity(items: list[dict], descending: bool = True) -> list[dict]:
    """Sort products by review score and sales volume."""
    return sorted(items, key=lambda x: (x.get("rating", 0), x.get("sales_count", 0)), reverse=descending)
''',

    "billing/invoices.py": '''"""Invoice generation, VAT and sales tax calculation."""
def calculate_vat_and_sales_tax(subtotal: float, country_code: str) -> dict:
    """Calculate VAT or sales tax based on customer destination country code."""
    rates = {"US": 0.08, "GB": 0.20, "DE": 0.19, "CA": 0.13}
    tax_rate = rates.get(country_code, 0.05)
    tax_amount = round(subtotal * tax_rate, 2)
    return {
        "subtotal": subtotal,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "total": round(subtotal + tax_amount, 2),
    }

def generate_invoice_metadata(order_id: str, items: list[dict], customer_info: dict) -> dict:
    """Generate invoice PDF header, billing address, line items, and VAT breakdown."""
    return {
        "invoice_number": f"INV-{order_id}",
        "customer": customer_info,
        "line_items": items,
        "currency": "USD",
    }
''',

    "billing/payments.py": '''"""Payment gateway tokenization, Stripe charges, and refund processing."""
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
''',

    "billing/discounts.py": '''"""Coupon promo validation and percentage discount calculation."""
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
''',

    "orders/cart.py": '''"""Shopping cart management, item quantity updates, and merging duplicates."""
class ShoppingCart:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.items = {}

    def update_quantity(self, sku: str, quantity: int) -> None:
        """Update cart item quantity or remove item if quantity <= 0."""
        if quantity <= 0:
            self.items.pop(sku, None)
        else:
            self.items[sku] = quantity

    def merge_duplicate_items(self, incoming_items: dict) -> None:
        """Merge items from guest cart into authenticated user cart."""
        for sku, qty in incoming_items.items():
            self.items[sku] = self.items.get(sku, 0) + qty

    def get_cart_total(self, price_lookup: dict) -> float:
        """Compute subtotal for all items in shopping cart."""
        return sum(qty * price_lookup.get(sku, 0.0) for sku, qty in self.items.items())
''',

    "orders/checkout.py": '''"""Order checkout, state machine transitions, and address validation."""
VALID_TRANSITIONS = {
    "pending": {"paid", "cancelled"},
    "paid": {"processing", "refunded"},
    "processing": {"shipped"},
    "shipped": {"delivered", "returned"},
}

def transition_order_state(current_state: str, new_state: str) -> bool:
    """Validate and execute order state machine transition (pending -> paid -> shipped)."""
    allowed = VALID_TRANSITIONS.get(current_state, set())
    return new_state in allowed

def validate_shipping_address(address: dict) -> list[str]:
    """Validate street, postal code, city, and ISO country."""
    errors = []
    for field in ["street", "city", "postal_code", "country"]:
        if not address.get(field):
            errors.append(f"Missing required field: {field}")
    return errors
''',

    "notifications/email.py": '''"""Outbound email templates, SMTP connection pooling, and order confirmation sender."""
def pool_smtp_connection(host: str = "smtp.example.com", port: int = 587):
    """Manage pooled connection to outbound SMTP mail server."""
    return {"host": host, "port": port, "active": True}

def render_welcome_email(username: str, confirmation_link: str) -> str:
    """Render welcome email HTML template with account activation URL."""
    return f"<h1>Welcome, {username}!</h1><p>Confirm: {confirmation_link}</p>"

def send_order_confirmation(to_email: str, order_id: str, summary: dict) -> bool:
    """Send order confirmation email with receipt and tracking number."""
    if not to_email or "@" not in to_email:
        return False
    return True
''',

    "notifications/webhook.py": '''"""Outgoing webhook event delivery, HMAC signing, and exponential backoff retry."""
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
''',

    "storage/s3.py": '''"""Amazon S3 presigned URL generation, multipart uploads, and bucket policy."""
def generate_presigned_upload_url(bucket: str, object_key: str, expires_in: int = 3600) -> str:
    """Generate presigned S3 URL for direct client media upload."""
    return f"https://{bucket}.s3.amazonaws.com/{object_key}?expires={expires_in}&signature=mock"

def split_multipart_chunks(file_path: str, chunk_size_mb: int = 5) -> list[dict]:
    """Split large files into 5MB parts for S3 multipart upload."""
    parts = []
    # simulate chunk partitioning
    return parts

def enforce_bucket_security_policy(bucket: str, enable_encryption: bool = True) -> bool:
    """Enforce SSE-S3 AES-256 server-side encryption bucket policy."""
    return enable_encryption
''',

    "storage/cache.py": '''"""LRU in-memory cache, TTL eviction cleaner, and Redis key namespacing."""
from collections import OrderedDict
import time

class LRUCache:
    def __init__(self, capacity: int = 1000):
        self.capacity = capacity
        self.cache = OrderedDict()
        self.expirations = {}

    def get(self, key: str):
        """Retrieve key and refresh LRU position."""
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def set(self, key: str, value, ttl_seconds: int = 300) -> None:
        """Store key-value with TTL expiration and evict oldest if full."""
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        self.expirations[key] = time.time() + ttl_seconds
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

    def namespace_key(self, prefix: str, raw_key: str) -> str:
        """Apply Redis key namespacing prefix."""
        return f"{prefix}:{raw_key}"
''',

    "utils/crypto.py": '''"""AES-256-GCM symmetric payload encryption and decryption utilities."""
import base64
import os

def encrypt_aes_gcm(plaintext: str, key_bytes: bytes) -> dict:
    """Encrypt sensitive string payload using AES-256-GCM authenticated cipher."""
    nonce = os.urandom(12)
    ciphertext = base64.b64encode(plaintext.encode()).decode()
    tag = os.urandom(16).hex()
    return {"ciphertext": ciphertext, "nonce": nonce.hex(), "tag": tag}

def decrypt_aes_gcm(encrypted_dict: dict, key_bytes: bytes) -> str:
    """Decrypt AES-256-GCM ciphertext and verify auth tag."""
    return base64.b64decode(encrypted_dict["ciphertext"].encode()).decode()
''',

    "utils/rate_limit.py": '''"""Sliding-window rate limiter, IP throttling, and Retry-After calculation."""
import time
from collections import deque

class SlidingWindowRateLimiter:
    def __init__(self, limit: int = 60, window_seconds: int = 60):
        self.limit = limit
        self.window = window_seconds
        self.requests = {}

    def is_allowed(self, ip_address: str) -> tuple[bool, int]:
        """Check if IP address exceeded sliding window counter; return (allowed, retry_after)."""
        now = time.time()
        q = self.requests.setdefault(ip_address, deque())
        while q and q[0] <= now - self.window:
            q.popleft()
        if len(q) < self.limit:
            q.append(now)
            return True, 0
        retry_after = int(self.window - (now - q[0]))
        return False, max(1, retry_after)
''',
}

# Exactly 20 questions for the Phase 2 gate
QUESTIONS = [
    {
        "id": 1,
        "query": "Where is coupon code validation and expiry checking handled?",
        "expected_file": "billing/discounts.py",
    },
    {
        "id": 2,
        "query": "Where is role-based access control (RBAC) permission checking handled?",
        "expected_file": "auth/permissions.py",
    },
    {
        "id": 3,
        "query": "Where is HMAC signature header generation for outgoing webhook events handled?",
        "expected_file": "notifications/webhook.py",
    },
    {
        "id": 4,
        "query": "Where is bcrypt salt generation and PBKDF2 password hash comparison handled?",
        "expected_file": "auth/passwords.py",
    },
    {
        "id": 5,
        "query": "Where is signed session token generation and expiration validation handled?",
        "expected_file": "auth/tokens.py",
    },
    {
        "id": 6,
        "query": "Where is sliding-window IP rate limiting and 429 Retry-After calculation handled?",
        "expected_file": "utils/rate_limit.py",
    },
    {
        "id": 7,
        "query": "Where is AES-256-GCM authenticated payload encryption and decryption handled?",
        "expected_file": "utils/crypto.py",
    },
    {
        "id": 8,
        "query": "Where is LRU cache eviction and TTL expiration cleaning handled?",
        "expected_file": "storage/cache.py",
    },
    {
        "id": 9,
        "query": "Where is presigned S3 URL generation and multipart upload chunking handled?",
        "expected_file": "storage/s3.py",
    },
    {
        "id": 10,
        "query": "Where is outbound SMTP order confirmation email sending and template rendering handled?",
        "expected_file": "notifications/email.py",
    },
    {
        "id": 11,
        "query": "Where is credit card gateway tokenization and Stripe charge processing handled?",
        "expected_file": "billing/payments.py",
    },
    {
        "id": 12,
        "query": "Where is VAT and sales tax calculation for invoices handled?",
        "expected_file": "billing/invoices.py",
    },
    {
        "id": 13,
        "query": "Where is product SKU lookup and inventory decrement handled?",
        "expected_file": "catalog/products.py",
    },
    {
        "id": 14,
        "query": "Where is product price range filtering and full-text keyword search handled?",
        "expected_file": "catalog/search.py",
    },
    {
        "id": 15,
        "query": "Where is shopping cart item quantity updating and duplicate merging handled?",
        "expected_file": "orders/cart.py",
    },
    {
        "id": 16,
        "query": "Where is order checkout state machine transition from pending to paid handled?",
        "expected_file": "orders/checkout.py",
    },
    {
        "id": 17,
        "query": "Where is session token revocation on user logout handled?",
        "expected_file": "auth/tokens.py",
    },
    {
        "id": 18,
        "query": "Where is percentage discount calculation against order subtotal handled?",
        "expected_file": "billing/discounts.py",
    },
    {
        "id": 19,
        "query": "Where is outgoing webhook retry logic with exponential backoff handled?",
        "expected_file": "notifications/webhook.py",
    },
    {
        "id": 20,
        "query": "Where is Redis key namespacing and cache TTL storage handled?",
        "expected_file": "storage/cache.py",
    },
]


def build_bench_repo(target_dir: Path) -> list[str]:
    """Write all benchmark files into target_dir and return list of relative paths."""
    written = []
    for rel_path, content in BENCH_FILES.items():
        p = target_dir / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        written.append(rel_path)
    return written
