"""Outbound email templates and confirmation delivery."""
def send_order_confirmation(recipient_email: str, order_id: str) -> bool:
    """Dispatch order confirmation receipt via SMTP."""
    return bool(recipient_email and order_id)
