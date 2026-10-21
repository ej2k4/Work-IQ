"""
phase3_bench.py – Benchmark codebase and multi-file dependency questions for Phase 3.

Defines a multi-service application with explicit cross-file caller dependencies,
and 10 multi-file impact questions: "What breaks if I change function X?"
"""
from pathlib import Path

FILES = {
    # ── Auth module ──────────────────────────────────────────────────────────
    "auth/tokens.py": '''"""Session token generation, verification, and revocation."""
import time
import hmac
import hashlib
import json
import base64

SECRET_KEY = "auth-super-secret"

def generate_session_token(user_id: str, ttl_seconds: int = 3600) -> str:
    """Generate signed JWT-like session token."""
    payload = {"user_id": user_id, "exp": int(time.time()) + ttl_seconds}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = hmac.new(SECRET_KEY.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{sig}"

def verify_session_token(token: str) -> dict | None:
    """Validate token signature and expiration, returning user payload."""
    parts = token.split(".")
    if len(parts) != 2:
        return None
    encoded, sig = parts
    expected = hmac.new(SECRET_KEY.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    payload = json.loads(base64.urlsafe_b64decode(encoded.encode()).decode())
    return payload if time.time() <= payload.get("exp", 0) else None
''',

    "auth/passwords.py": '''"""Password hashing and brute-force rate-limiting."""
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
''',

    "auth/permissions.py": '''"""Role-based access checks requiring authenticated token."""
from auth.tokens import verify_session_token

def check_permission(session_token: str, required_role: str) -> bool:
    """Verify session token and check if user has required role."""
    user = verify_session_token(session_token)
    if not user:
        return False
    return user.get("role") == required_role or required_role == "public"
''',

    # ── Catalog module ───────────────────────────────────────────────────────
    "catalog/products.py": '''"""Product catalog management and image uploads."""
from storage.s3 import generate_presigned_upload_url

class ProductCatalog:
    def __init__(self):
        self.items = {}

    def lookup_sku(self, sku: str) -> dict | None:
        """Find product specification by SKU."""
        return self.items.get(sku)

    def decrement_stock(self, sku: str, quantity: int) -> bool:
        """Deduct purchased quantity from inventory."""
        prod = self.items.get(sku)
        if not prod or prod.get("stock", 0) < quantity:
            return False
        prod["stock"] -= quantity
        return True

    def create_product_image_upload(self, sku: str) -> str:
        """Generate presigned S3 URL for product catalog image."""
        return generate_presigned_upload_url("catalog-bucket", f"images/{sku}.png")
''',

    "catalog/inventory_sync.py": '''"""Warehouse inventory synchronization worker."""
from catalog.products import ProductCatalog

def sync_warehouse_shipment(catalog: ProductCatalog, manifest: list[dict]) -> bool:
    """Synchronize shipment by decrementing product stock."""
    for item in manifest:
        sku = item["sku"]
        qty = item["qty"]
        if not catalog.decrement_stock(sku, qty):
            return False
    return True
''',

    # ── Billing module ───────────────────────────────────────────────────────
    "billing/discounts.py": '''"""Promotional discount code validation."""
import time

COUPONS = {
    "SAVE10": 0.10,
    "VIP20": 0.20,
}

def validate_coupon_code(code: str) -> float | None:
    """Validate coupon code and return discount rate (e.g. 0.15 for 15% off)."""
    return COUPONS.get(code.upper())
''',

    "billing/invoices.py": '''"""Tax calculation and S3 storage for invoice PDFs."""
from storage.s3 import generate_presigned_upload_url

def calculate_vat_and_sales_tax(subtotal: float, country_code: str) -> float:
    """Calculate VAT or regional sales tax for invoice."""
    rate = 0.20 if country_code in {"GB", "DE", "FR"} else 0.08
    return round(subtotal * rate, 2)

def archive_invoice_pdf(order_id: str) -> str:
    """Generate presigned S3 URL to archive invoice PDF."""
    return generate_presigned_upload_url("invoices-bucket", f"pdf/{order_id}.pdf")
''',

    "billing/reports.py": '''"""Monthly tax accounting and audit reporting."""
from billing.invoices import calculate_vat_and_sales_tax

def compute_monthly_tax_liability(transactions: list[dict]) -> float:
    """Aggregate total tax owed across all orders using tax calculator."""
    total_tax = 0.0
    for t in transactions:
        subtotal = t["subtotal"]
        country = t["country"]
        total_tax += calculate_vat_and_sales_tax(subtotal, country)
    return round(total_tax, 2)
''',

    "billing/payments.py": '''"""Stripe payment processing, card encryption, and webhooks."""
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
''',

    "billing/subscriptions.py": '''"""Recurring monthly recurring billing worker."""
from billing.payments import process_stripe_charge

def process_subscription_renewal(user_id: str, card_token: str, plan_amount_cents: int) -> bool:
    """Execute automated recurring charge for customer subscription."""
    res = process_stripe_charge(card_token, plan_amount_cents, ip="127.0.0.1")
    return res.get("status") == "succeeded"
''',

    # ── Orders module ────────────────────────────────────────────────────────
    "orders/cart.py": '''"""Shopping cart session and coupon discount calculations."""
from catalog.products import ProductCatalog
from billing.discounts import validate_coupon_code
from auth.tokens import verify_session_token

def apply_cart_promo(session_token: str, cart_items: dict, coupon_code: str, catalog: ProductCatalog) -> float:
    """Calculate cart subtotal, verify session token, and apply coupon discount."""
    user = verify_session_token(session_token)
    if not user:
        return 0.0
    subtotal = 0.0
    for sku, qty in cart_items.items():
        item = catalog.lookup_sku(sku)
        if item:
            subtotal += item.get("price", 0.0) * qty
    discount = validate_coupon_code(coupon_code) or 0.0
    return round(subtotal * (1.0 - discount), 2)
''',

    "orders/checkout.py": '''"""Main checkout pipeline coordinating catalog, billing, and email."""
from catalog.products import ProductCatalog
from billing.discounts import validate_coupon_code
from billing.invoices import calculate_vat_and_sales_tax
from billing.payments import process_stripe_charge
from notifications.email import send_order_confirmation
from notifications.webhook import sign_webhook_payload
from auth.tokens import verify_session_token

def execute_checkout(session_token: str, cart: dict, card_token: str,
                     country: str, promo: str, catalog: ProductCatalog, ip: str) -> dict:
    """Complete order checkout across inventory, pricing, payments, and delivery."""
    user = verify_session_token(session_token)
    if not user:
        return {"error": "unauthorized"}
    # Deduct stock
    for sku, qty in cart.items():
        if not catalog.decrement_stock(sku, qty):
            return {"error": f"insufficient_stock_{sku}"}
    # Validate discount
    discount_rate = validate_coupon_code(promo) or 0.0
    subtotal = 100.0 * (1.0 - discount_rate)
    tax = calculate_vat_and_sales_tax(subtotal, country)
    # Charge card
    charge = process_stripe_charge(card_token, int((subtotal + tax) * 100), ip)
    if charge.get("status") != "succeeded":
        return {"error": "payment_failed"}
    # Notify
    send_order_confirmation(user.get("email", ""), "ORD-123")
    sign_webhook_payload(b"order_placed", "order-secret")
    return {"status": "completed", "order_id": "ORD-123"}
''',

    # ── Notifications & Storage & Utils ──────────────────────────────────────
    "notifications/email.py": '''"""Outbound email templates and confirmation delivery."""
def send_order_confirmation(recipient_email: str, order_id: str) -> bool:
    """Dispatch order confirmation receipt via SMTP."""
    return bool(recipient_email and order_id)
''',

    "notifications/webhook.py": '''"""HMAC signature computation for outgoing webhooks."""
import hmac
import hashlib

def sign_webhook_payload(payload_bytes: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature for outgoing webhook event."""
    return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
''',

    "storage/s3.py": '''"""Amazon S3 presigned URL generation."""
def generate_presigned_upload_url(bucket: str, object_key: str) -> str:
    """Generate presigned S3 upload URL for media and PDFs."""
    return f"https://{bucket}.s3.amazonaws.com/{object_key}?signature=mock_sig"
''',

    "utils/crypto.py": '''"""AES-256-GCM symmetric payload encryption."""
import base64
import os

def encrypt_aes_gcm(plaintext: str, key_bytes: bytes) -> dict:
    """Encrypt payload string with AES-256-GCM authenticated cipher."""
    return {"ciphertext": base64.b64encode(plaintext.encode()).decode(), "nonce": "mock_nonce"}
''',

    "utils/rate_limit.py": '''"""Sliding-window rate limiter."""
class SlidingWindowRateLimiter:
    def __init__(self, limit: int = 10, window_seconds: int = 60):
        self.limit = limit
        self.window = window_seconds

    def is_allowed(self, ip_address: str) -> tuple[bool, int]:
        """Check if request is permitted under current sliding window counter."""
        return True, 0
''',
}

# 10 multi-file impact questions: "What breaks if I change function X?"
IMPACT_QUESTIONS = [
    {
        "id": 1,
        "target_function": "validate_coupon_code",
        "defined_in": "billing/discounts.py",
        "query": "What functions and files break if I change the signature or return type of validate_coupon_code?",
        "expected_callers": ["orders/cart.py", "orders/checkout.py"],
    },
    {
        "id": 2,
        "target_function": "lookup_sku",
        "defined_in": "catalog/products.py",
        "query": "What functions and files break if I change the lookup_sku function?",
        "expected_callers": ["orders/cart.py"],
    },
    {
        "id": 3,
        "target_function": "decrement_stock",
        "defined_in": "catalog/products.py",
        "query": "What functions and files break if I change the decrement_stock method in ProductCatalog?",
        "expected_callers": ["catalog/inventory_sync.py", "orders/checkout.py"],
    },
    {
        "id": 4,
        "target_function": "process_stripe_charge",
        "defined_in": "billing/payments.py",
        "query": "What functions and files break if I modify process_stripe_charge?",
        "expected_callers": ["billing/subscriptions.py", "orders/checkout.py"],
    },
    {
        "id": 5,
        "target_function": "sign_webhook_payload",
        "defined_in": "notifications/webhook.py",
        "query": "What functions and files break if I change sign_webhook_payload?",
        "expected_callers": ["billing/payments.py", "orders/checkout.py"],
    },
    {
        "id": 6,
        "target_function": "verify_session_token",
        "defined_in": "auth/tokens.py",
        "query": "What functions and files break if I change verify_session_token in auth/tokens.py?",
        "expected_callers": ["auth/permissions.py", "orders/cart.py", "orders/checkout.py"],
    },
    {
        "id": 7,
        "target_function": "encrypt_aes_gcm",
        "defined_in": "utils/crypto.py",
        "query": "What functions and files break if I change encrypt_aes_gcm in utils/crypto.py?",
        "expected_callers": ["auth/passwords.py", "billing/payments.py"],
    },
    {
        "id": 8,
        "target_function": "is_allowed",
        "defined_in": "utils/rate_limit.py",
        "query": "What functions and files break if I change the is_allowed method on SlidingWindowRateLimiter?",
        "expected_callers": ["auth/passwords.py", "billing/payments.py"],
    },
    {
        "id": 9,
        "target_function": "generate_presigned_upload_url",
        "defined_in": "storage/s3.py",
        "query": "What functions and files break if I change generate_presigned_upload_url?",
        "expected_callers": ["catalog/products.py", "billing/invoices.py"],
    },
    {
        "id": 10,
        "target_function": "calculate_vat_and_sales_tax",
        "defined_in": "billing/invoices.py",
        "query": "What functions and files break if I change calculate_vat_and_sales_tax in billing/invoices.py?",
        "expected_callers": ["billing/reports.py", "orders/checkout.py"],
    },
]


def build_phase3_repo(target_dir: Path) -> list[str]:
    """Write all benchmark files into target_dir."""
    written = []
    for rel_path, content in FILES.items():
        p = target_dir / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        written.append(rel_path)
    return written
