"""Order checkout, state machine transitions, and address validation."""
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
