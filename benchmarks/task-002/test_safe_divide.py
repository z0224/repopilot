from safe_divide import safe_divide


def test_normal_division():
    assert safe_divide(6, 2) == 3


def test_division_by_zero():
    assert safe_divide(6, 0) is None
