"""Monthly tax accounting and audit reporting."""
from billing.invoices import calculate_vat_and_sales_tax

def compute_monthly_tax_liability(transactions: list[dict]) -> float:
    """Aggregate total tax owed across all orders using tax calculator."""
    total_tax = 0.0
    for t in transactions:
        subtotal = t["subtotal"]
        country = t["country"]
        total_tax += calculate_vat_and_sales_tax(subtotal, country)
    return round(total_tax, 2)
