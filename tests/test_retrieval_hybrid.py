import pytest

from repopilot.retrieval.chunker import chunk_python_source
from repopilot.retrieval.hybrid import HybridRetriever


class FakeMultilingualEmbedder:
    def encode(self, texts):
        vectors = []

        for text in texts:
            lowered = text.lower()

            inventory = (
                "inventory" in lowered
                or "库存" in lowered
                or "预留" in lowered
            )
            atomic = (
                "atomic" in lowered
                or "原子" in lowered
            )
            discount = (
                "discount" in lowered
                or "折扣" in lowered
            )

            vectors.append(
                [
                    float(inventory),
                    float(atomic),
                    float(discount),
                ]
            )

        return vectors


def build_chunks():
    chunks = []

    chunks.extend(
        chunk_python_source(
            '''def reserve_inventory(repository, items):
    """Atomically reserve inventory items."""
    return repository.reserve(items)
''',
            "inventory/service.py",
        )
    )

    chunks.extend(
        chunk_python_source(
            '''def apply_discount(price, percent):
    """Apply a percentage discount."""
    return price * (1 - percent / 100)
''',
            "pricing.py",
        )
    )

    return chunks


def test_cross_language_query_uses_semantic_ranking():
    retriever = HybridRetriever(
        build_chunks(),
        FakeMultilingualEmbedder(),
    )

    result = retriever.search(
        "库存预留必须具有原子性",
        top_k=1,
    )[0]

    assert result.chunk.symbol == "reserve_inventory"
    assert result.semantic_rank == 1


def test_exact_symbol_query_uses_lexical_ranking():
    retriever = HybridRetriever(
        build_chunks(),
        FakeMultilingualEmbedder(),
    )

    result = retriever.search(
        "apply_discount",
        top_k=1,
    )[0]

    assert result.chunk.symbol == "apply_discount"
    assert result.lexical_rank == 1


def test_hybrid_result_is_serializable():
    retriever = HybridRetriever(
        build_chunks(),
        FakeMultilingualEmbedder(),
    )

    payload = retriever.search("折扣计算", top_k=1)[0].to_dict()

    assert payload["chunk"]["symbol"] == "apply_discount"
    assert payload["score"] > 0
    assert "lexical_contribution" in payload
    assert "semantic_contribution" in payload


def test_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        HybridRetriever(
            build_chunks(),
            FakeMultilingualEmbedder(),
            lexical_weight=0,
            semantic_weight=0,
        )
