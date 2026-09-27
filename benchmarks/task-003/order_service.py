from pricing import apply_discount


def checkout_total(items, discount_percent=0):
    subtotal = sum(items)
    return apply_discount(subtotal, discount_percent)
