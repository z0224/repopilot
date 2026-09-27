def valid_scores(records):
    """Return scores that are present and not None without changing records."""
    return [record.get("score") for record in records if record.get("score") is not None]
