import pytest

from checkout.service import checkout_total


def test_checkout_without_coupon():
    assert checkout_total([40, 60]) == 100


def test_checkout_with_ten_percent_coupon():
    assert checkout_total([40, 60], 10) == 90


def test_checkout_with_full_coupon():
    assert checkout_total([40, 60], 100) == 0


def test_checkout_rejects_invalid_coupon():
    with pytest.raises(ValueError):
        checkout_total([40, 60], -1)
