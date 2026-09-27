from dataclasses import dataclass


@dataclass(frozen=True)
class InvoiceLine:
    sku: str
    unit_price: float
    quantity: int


def validate_line(line):
    if not line.sku:
        raise ValueError("sku must not be empty")

    if line.unit_price < 0:
        raise ValueError("unit price must not be negative")

    if line.quantity <= 0:
        raise ValueError("quantity must be positive")


def calculate_subtotal(lines):
    subtotal = 0.0

    for line in lines:
        validate_line(line)
        subtotal += line.unit_price * line.quantity

    return round(subtotal, 2)


def calculate_discount(subtotal, percent):
    if percent < 0 or percent > 100:
        raise ValueError("discount percent must be between 0 and 100")

    return round(subtotal * percent / 100, 2)


def calculate_tax(taxable_amount, tax_rate):
    if tax_rate < 0:
        raise ValueError("tax rate must not be negative")

    return round(taxable_amount * tax_rate / 100, 2)


def calculate_total(
    lines,
    *,
    discount_percent=0,
    tax_rate=0,
):
    subtotal = calculate_subtotal(lines)
    discount = calculate_discount(
        subtotal,
        discount_percent,
    )
    taxable_amount = subtotal - discount
    tax = calculate_tax(
        taxable_amount,
        tax_rate,
    )

    return round(taxable_amount + tax, 2)


def calculate_refund(
    paid,
    total,
    *,
    restocking_fee=0,
):
    """Return refundable overpayment after a restocking fee."""
    if paid < total:
        raise ValueError("paid amount is less than invoice total")

    if restocking_fee < 0:
        raise ValueError("restocking fee must not be negative")

    return round(
        max(0.0, paid - total - restocking_fee),
        2,
    )


def format_money(value, currency="USD"):
    return f"{currency} {value:.2f}"


def summarize_invoice(
    lines,
    *,
    discount_percent=0,
    tax_rate=0,
    currency="USD",
):
    total = calculate_total(
        lines,
        discount_percent=discount_percent,
        tax_rate=tax_rate,
    )

    return {
        "line_count": len(lines),
        "total": total,
        "formatted_total": format_money(
            total,
            currency,
        ),
    }
