def apply_coupon(price, percent):
    """Apply an integer percentage coupon to a checkout price."""
    if percent < 0 or percent > 100:
        raise ValueError(
            "coupon percent must be between 0 and 100"
        )

    return round(
        price * (1 - percent / 100),
        2,
    )
