def safe_divide(a, b):
    """Return ``a / b``, or ``None`` when the divisor is zero."""
    if b == 0:
        return None
    return a / b
