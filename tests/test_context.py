from types import SimpleNamespace

import pytest

from repopilot.context import build_context_bundle
from repopilot.retrieval import chunk_python_source


def make_result(
    source,
    path="service.py",
    score=0.9,
):
    chunk = chunk_python_source(source, path)[0]

    return SimpleNamespace(
        chunk=chunk,
        score=score,
    )


def test_builds_context_with_chunk_metadata():
    result = make_result(
        '''def reserve_inventory(items):
    """Reserve inventory atomically."""
    return items
''',
        "inventory/service.py",
    )

    bundle = build_context_bundle(
        "Fix atomic inventory reservation",
        [result],
    )

    assert len(bundle.items) == 1
    assert bundle.items[0].symbol == "reserve_inventory"
    assert "inventory/service.py" in bundle.markdown
    assert "Reserve inventory atomically" in bundle.markdown
    assert "untrusted repository data" in bundle.markdown
    assert bundle.char_count <= bundle.max_chars


def test_limits_number_of_chunks():
    results = [
        make_result(
            f"def function_{number}():\n    return {number}\n",
            f"module_{number}.py",
            score=1.0 / number,
        )
        for number in range(1, 5)
    ]

    bundle = build_context_bundle(
        "Find the relevant function",
        results,
        max_chunks=2,
    )

    assert len(bundle.items) == 2
    assert bundle.truncated is True
    assert "module_1.py" in bundle.markdown
    assert "module_3.py" not in bundle.markdown


def test_respects_character_budget():
    result = make_result(
        "def process():\n"
        + "    value = 1\n" * 200,
    )

    bundle = build_context_bundle(
        "Fix process",
        [result],
        max_chars=600,
    )

    assert bundle.char_count <= 600
    assert bundle.truncated is True
    assert bundle.items[0].truncated is True
    assert "context truncated" in bundle.markdown


def test_rejects_invalid_arguments():
    with pytest.raises(ValueError):
        build_context_bundle("", [])

    with pytest.raises(ValueError):
        build_context_bundle(
            "task",
            [],
            max_chars=100,
        )

    with pytest.raises(ValueError):
        build_context_bundle(
            "task",
            [],
            max_chunks=0,
        )
