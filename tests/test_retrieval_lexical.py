import pytest

from repopilot.retrieval import (
    LexicalRetriever,
    chunk_python_source,
    search_chunks,
    tokenize,
)


def build_chunks():
    chunks = []

    chunks.extend(
        chunk_python_source(
            '''def apply_discount(price, percent):
    """Apply a percentage discount to a price."""
    return price * (1 - percent / 100)


def format_currency(value):
    """Format a monetary value."""
    return f"¥{value:.2f}"
''',
            "pricing.py",
        )
    )

    chunks.extend(
        chunk_python_source(
            '''from pricing import apply_discount


def checkout_total(items, discount_percent=0):
    """Calculate the final order total."""
    return apply_discount(sum(items), discount_percent)
''',
            "order_service.py",
        )
    )

    chunks.extend(
        chunk_python_source(
            '''def test_checkout_with_discount():
    assert checkout_total([50, 50], 10) == 90
''',
            "tests/test_order_service.py",
        )
    )

    return chunks


def test_tokenizes_snake_case_and_camel_case():
    assert tokenize("reserve_inventory InventoryService") == [
        "reserve",
        "inventory",
        "inventory",
        "service",
    ]


def test_symbol_match_ranks_expected_function_first():
    results = search_chunks(
        build_chunks(),
        "apply discount percentage",
        top_k=3,
    )

    assert results[0].chunk.chunk_id == (
        "pricing.py::apply_discount"
    )
    assert "symbol" in results[0].field_matches
    assert "discount" in results[0].matched_terms


def test_returns_explainable_field_matches():
    results = search_chunks(
        build_chunks(),
        "format currency monetary",
    )

    result = results[0]

    assert result.chunk.symbol == "format_currency"
    assert result.score > 0
    assert "symbol" in result.field_matches
    assert "docstring" in result.field_matches

    serialized = result.to_dict()

    assert serialized["chunk"]["symbol"] == "format_currency"
    assert serialized["score"] == result.score


def test_top_k_limits_results():
    results = search_chunks(
        build_chunks(),
        "discount",
        top_k=2,
    )

    assert len(results) == 2
    assert results[0].score >= results[1].score


def test_zero_score_results_are_excluded():
    results = search_chunks(
        build_chunks(),
        "completely_unrelated_term",
    )

    assert results == []


def test_rejects_invalid_top_k():
    retriever = LexicalRetriever(build_chunks())

    with pytest.raises(ValueError):
        retriever.search("discount", top_k=0)
