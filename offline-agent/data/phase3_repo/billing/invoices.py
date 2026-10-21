"""Tax calculation and S3 storage for invoice PDFs."""
from storage.s3 import generate_presigned_upload_url

def calculate_vat_and_sales_tax(subtotal: float, country_code: str) -> float:
    """Calculate VAT or regional sales tax for invoice."""
    rate = 0.20 if country_code in {"GB", "DE", "FR"} else 0.08
    return round(subtotal * rate, 2)

def archive_invoice_pdf(order_id: str) -> str:
    """Generate presigned S3 URL to archive invoice PDF."""
    return generate_presigned_upload_url("invoices-bucket", f"pdf/{order_id}.pdf")
