from checkout.pricing import apply_coupon


def checkout_total(items, coupon_percent=0):
    """Calculate the active checkout total."""
    subtotal = sum(items)

    return apply_coupon(
        subtotal,
        coupon_percent,
    )
