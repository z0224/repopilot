def record_access_attempt(user_id, allowed):
    """Return an immutable audit record."""
    return {
        "user_id": user_id,
        "allowed": bool(allowed),
    }
