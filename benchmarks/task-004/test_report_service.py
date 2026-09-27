from copy import deepcopy

from report_service import average_score


def test_average_normal_scores():
    records = [{"score": 80}, {"score": 90}]
    assert average_score(records) == 85


def test_ignores_missing_and_none_scores():
    records = [
        {"score": 80},
        {"score": None},
        {"name": "missing score"},
        {"score": 100},
    ]
    assert average_score(records) == 90


def test_empty_records_return_none():
    assert average_score([]) is None


def test_input_records_are_not_modified():
    records = [{"score": 80}, {"score": None}]
    original = deepcopy(records)

    average_score(records)

    assert records == original
