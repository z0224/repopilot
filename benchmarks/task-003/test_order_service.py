import pytest

from order_service import checkout_total
from pricing import format_currency


def test_checkout_with_discount():
    assert checkout_total([50, 50], 10) == 90


def test_checkout_without_discount():
    assert checkout_total([40, 60]) == 100


def test_format_currency_is_preserved():
    assert format_currency(12.5) == "¥12.50"


def test_invalid_discount():
    with pytest.raises(ValueError):
        checkout_total([100], 120)
