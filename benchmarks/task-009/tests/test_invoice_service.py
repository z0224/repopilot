import pytest

from invoice_service import (
    InvoiceLine,
    calculate_discount,
    calculate_refund,
    calculate_subtotal,
    calculate_total,
    format_money,
)


def sample_lines():
    return [
        InvoiceLine("apple", 10, 2),
        InvoiceLine("banana", 5, 2),
    ]


def test_calculates_subtotal():
    assert calculate_subtotal(sample_lines()) == 30


def test_calculates_discount():
    assert calculate_discount(200, 10) == 20


def test_calculates_invoice_total():
    assert calculate_total(
        sample_lines(),
        discount_percent=10,
        tax_rate=10,
    ) == 29.7


def test_formats_money():
    assert format_money(29.7) == "USD 29.70"


def test_refunds_only_the_overpayment():
    assert calculate_refund(120, 100) == 20


def test_refund_deducts_restocking_fee():
    assert calculate_refund(
        120,
        100,
        restocking_fee=5,
    ) == 15


def test_refund_without_overpayment_is_zero():
    assert calculate_refund(100, 100) == 0


def test_refund_rejects_underpayment():
    with pytest.raises(ValueError):
        calculate_refund(90, 100)
