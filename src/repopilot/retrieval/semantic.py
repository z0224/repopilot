"""Pluggable semantic retrieval for repository code chunks."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, Sequence

from .chunker import CodeChunk


DEFAULT_MODEL = (
    "sentence-transformers/"
    "paraphrase-multilingual-MiniLM-L12-v2"
)


class EmbeddingProvider(Protocol):
    """Interface implemented by embedding backends."""

    def encode(
        self,
        texts: Sequence[str],
    ) -> Sequence[Sequence[float]]:
        ...


class SentenceTransformerEmbedder:
    """Local sentence-transformers embedding backend."""

    def __init__(
        self,
        model_name=DEFAULT_MODEL,
        device=None,
    ):
        try:
            from sentence_transformers import (
                SentenceTransformer,
            )
        except ImportError as error:
            raise RuntimeError(
                "Semantic dependencies are not installed. "
                'Run: python -m pip install -e ".[semantic]"'
            ) from error

        self.model_name = model_name
        self.model = SentenceTransformer(
            model_name,
            device=device,
        )

    def encode(self, texts):
        vectors = self.model.encode(
            list(texts),
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        if hasattr(vectors, "tolist"):
            return vectors.tolist()

        return vectors


@dataclass(frozen=True)
class SemanticRetrievalResult:
    chunk: CodeChunk
    score: float

    def to_dict(self):
        return {
            "chunk": self.chunk.to_dict(),
            "score": self.score,
        }


def chunk_embedding_text(chunk):
    """Build the text embedded for one code chunk."""
    sections = [
        f"Path: {chunk.path}",
        f"Symbol: {chunk.symbol}",
        f"Kind: {chunk.kind}",
    ]

    if chunk.docstring:
        sections.append(
            f"Docstring: {chunk.docstring}"
        )

    if chunk.imports:
        sections.append(
            "Imports: " + ", ".join(chunk.imports)
        )

    sections.append("Code:\n" + chunk.content)

    return "\n".join(sections)


def cosine_similarity(left, right):
    if len(left) != len(right):
        raise ValueError(
            "embedding dimensions do not match"
        )

    if not left:
        raise ValueError(
            "embedding vectors must not be empty"
        )

    dot_product = sum(
        left_value * right_value
        for left_value, right_value in zip(
            left,
            right,
        )
    )
    left_norm = math.sqrt(
        sum(value * value for value in left)
    )
    right_norm = math.sqrt(
        sum(value * value for value in right)
    )

    if left_norm == 0 or right_norm == 0:
        return 0.0

    return dot_product / (left_norm * right_norm)


def normalize_vectors(vectors, expected_count):
    if len(vectors) != expected_count:
        raise ValueError(
            "embedding provider returned an unexpected "
            "number of vectors"
        )

    normalized = [
        tuple(float(value) for value in vector)
        for vector in vectors
    ]

    if not normalized:
        return ()

    dimensions = {
        len(vector)
        for vector in normalized
    }

    if 0 in dimensions:
        raise ValueError(
            "embedding vectors must not be empty"
        )

    if len(dimensions) != 1:
        raise ValueError(
            "embedding vectors have inconsistent dimensions"
        )

    return tuple(normalized)


class SemanticRetriever:
    """Rank code chunks by embedding cosine similarity."""

    def __init__(self, chunks, embedder):
        self.chunks = tuple(chunks)
        self.embedder = embedder

        texts = [
            chunk_embedding_text(chunk)
            for chunk in self.chunks
        ]

        if texts:
            vectors = embedder.encode(texts)
            self.chunk_vectors = normalize_vectors(
                vectors,
                expected_count=len(texts),
            )
        else:
            self.chunk_vectors = ()

    def search(self, query, top_k=5):
        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        if not str(query).strip():
            return []

        if not self.chunks:
            return []

        query_vectors = normalize_vectors(
            self.embedder.encode([str(query)]),
            expected_count=1,
        )
        query_vector = query_vectors[0]

        results = []

        for chunk, vector in zip(
            self.chunks,
            self.chunk_vectors,
        ):
            score = cosine_similarity(
                query_vector,
                vector,
            )
            results.append(
                SemanticRetrievalResult(
                    chunk=chunk,
                    score=round(score, 6),
                )
            )

        results.sort(
            key=lambda result: (
                -result.score,
                result.chunk.chunk_id,
            )
        )

        return results[:top_k]
