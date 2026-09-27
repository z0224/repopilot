from exception_service import parse_age


def test_parses_valid_age():
    assert parse_age({"age": "21"}) == 21


def test_rejects_invalid_string():
    assert parse_age({"age": "unknown"}) is None


def test_rejects_missing_age():
    assert parse_age({}) is None


def test_rejects_none_age():
    assert parse_age({"age": None}) is None


def test_rejects_negative_age():
    assert parse_age({"age": "-1"}) is None
