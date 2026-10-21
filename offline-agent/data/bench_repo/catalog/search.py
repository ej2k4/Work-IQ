"""Product catalog full-text search, price filtering, and popularity sorting."""
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
