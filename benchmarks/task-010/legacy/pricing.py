def apply_coupon(price, coupon_fraction):
    """Legacy coupon helper using a decimal fraction."""
    if coupon_fraction < 0 or coupon_fraction > 1:
        raise ValueError(
            "coupon fraction must be between 0 and 1"
        )

    return round(
        price * (1 - coupon_fraction),
        2,
    )


def calculate_legacy_checkout(items, coupon_fraction=0):
    """Calculate totals for the retired legacy checkout."""
    return apply_coupon(
        sum(items),
        coupon_fraction,
    )
