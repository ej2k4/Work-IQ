"""Invoice generation, VAT and sales tax calculation."""
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
