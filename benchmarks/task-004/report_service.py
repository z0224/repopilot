from data_cleaner import valid_scores


def average_score(records):
    """Return the average valid score, or None when no valid scores exist."""
    scores = valid_scores(records)
    if not scores:
        return None
    return round(sum(scores) / len(scores), 2)
