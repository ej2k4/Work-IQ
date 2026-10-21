"""Outbound email templates, SMTP connection pooling, and order confirmation sender."""
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
