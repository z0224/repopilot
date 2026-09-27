def parse_age(payload):
    """Parse a non-negative age, returning None for invalid input."""
    try:
        age = int(payload["age"])
    except (KeyError, TypeError, ValueError):
        return None

    return age if age >= 0 else None
