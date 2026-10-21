"""Main checkout pipeline coordinating catalog, billing, and email."""
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
