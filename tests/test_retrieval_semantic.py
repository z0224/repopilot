import pytest

from repopilot.retrieval import (
    SemanticRetriever,
    chunk_embedding_text,
    chunk_python_source,
    cosine_similarity,
)


class FakeMultilingualEmbedder:
    """Deterministic test embedder."""

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


class BadCountEmbedder:
    def encode(self, texts):
        return [[1.0, 0.0]]


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


def test_semantic_search_matches_cross_language_query():
    retriever = SemanticRetriever(
        build_chunks(),
        FakeMultilingualEmbedder(),
    )

    results = retriever.search(
        "库存预留操作必须具有原子性",
        top_k=2,
    )

    assert results[0].chunk.chunk_id == (
        "inventory/service.py::reserve_inventory"
    )
    assert results[0].score > results[1].score


def test_semantic_result_is_serializable():
    retriever = SemanticRetriever(
        build_chunks(),
        FakeMultilingualEmbedder(),
    )

    result = retriever.search("折扣计算", top_k=1)[0]
    payload = result.to_dict()

    assert payload["chunk"]["symbol"] == (
        "apply_discount"
    )
    assert payload["score"] == result.score


def test_chunk_embedding_text_contains_metadata():
    chunk = build_chunks()[0]

    text = chunk_embedding_text(chunk)

    assert "Path: inventory/service.py" in text
    assert "Symbol: reserve_inventory" in text
    assert "Atomically reserve inventory" in text
    assert "Code:" in text


def test_cosine_similarity_handles_zero_vector():
    assert cosine_similarity(
        [0.0, 0.0],
        [1.0, 0.0],
    ) == 0.0


def test_rejects_invalid_top_k():
    retriever = SemanticRetriever(
        build_chunks(),
        FakeMultilingualEmbedder(),
    )

    with pytest.raises(ValueError):
        retriever.search("inventory", top_k=0)


def test_rejects_wrong_embedding_count():
    with pytest.raises(
        ValueError,
        match="unexpected number",
    ):
        SemanticRetriever(
            build_chunks(),
            BadCountEmbedder(),
        )
