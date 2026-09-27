def format_currency(value):
    """Format a monetary value without changing its amount."""
    return f"¥{value:.2f}"


def apply_discount(price, percent):
    """Apply a percentage discount to a price."""
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")

    return round(price * (1 - percent / 100), 2)
