"""Hybrid lexical and semantic retrieval using rank fusion."""

from __future__ import annotations

from dataclasses import dataclass

from .chunker import CodeChunk
from .lexical import LexicalRetriever
from .semantic import SemanticRetriever


@dataclass(frozen=True)
class HybridRetrievalResult:
    """One result produced by reciprocal-rank fusion."""

    chunk: CodeChunk
    score: float
    lexical_rank: int | None
    semantic_rank: int | None
    lexical_contribution: float
    semantic_contribution: float

    def to_dict(self):
        return {
            "chunk": self.chunk.to_dict(),
            "score": self.score,
            "lexical_rank": self.lexical_rank,
            "semantic_rank": self.semantic_rank,
            "lexical_contribution": self.lexical_contribution,
            "semantic_contribution": self.semantic_contribution,
        }


class HybridRetriever:
    """Fuse lexical and semantic rankings with weighted RRF."""

    def __init__(
        self,
        chunks,
        embedder,
        *,
        lexical_weight=1.0,
        semantic_weight=1.0,
        rrf_k=60,
    ):
        if lexical_weight < 0 or semantic_weight < 0:
            raise ValueError("retrieval weights must not be negative")

        if lexical_weight == 0 and semantic_weight == 0:
            raise ValueError("at least one weight must be positive")

        if rrf_k < 1:
            raise ValueError("rrf_k must be at least 1")

        self.chunks = tuple(chunks)
        self.lexical_weight = float(lexical_weight)
        self.semantic_weight = float(semantic_weight)
        self.rrf_k = int(rrf_k)

        self.lexical = LexicalRetriever(self.chunks)
        self.semantic = SemanticRetriever(
            self.chunks,
            embedder,
        )

    def search(self, query, top_k=5):
        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        if not str(query).strip() or not self.chunks:
            return []

        result_count = len(self.chunks)

        lexical_results = self.lexical.search(
            query,
            top_k=result_count,
        )
        semantic_results = self.semantic.search(
            query,
            top_k=result_count,
        )

        lexical_ranks = {
            result.chunk.chunk_id: rank
            for rank, result in enumerate(
                lexical_results,
                start=1,
            )
        }
        semantic_ranks = {
            result.chunk.chunk_id: rank
            for rank, result in enumerate(
                semantic_results,
                start=1,
            )
        }

        results = []

        for chunk in self.chunks:
            lexical_rank = lexical_ranks.get(chunk.chunk_id)
            semantic_rank = semantic_ranks.get(chunk.chunk_id)

            lexical_contribution = 0.0
            semantic_contribution = 0.0

            if lexical_rank is not None:
                lexical_contribution = (
                    self.lexical_weight
                    / (self.rrf_k + lexical_rank)
                )

            if semantic_rank is not None:
                semantic_contribution = (
                    self.semantic_weight
                    / (self.rrf_k + semantic_rank)
                )

            score = (
                lexical_contribution
                + semantic_contribution
            )

            if score <= 0:
                continue

            results.append(
                HybridRetrievalResult(
                    chunk=chunk,
                    score=round(score, 8),
                    lexical_rank=lexical_rank,
                    semantic_rank=semantic_rank,
                    lexical_contribution=round(
                        lexical_contribution,
                        8,
                    ),
                    semantic_contribution=round(
                        semantic_contribution,
                        8,
                    ),
                )
            )

        results.sort(
            key=lambda result: (
                -result.score,
                result.chunk.chunk_id,
            )
        )

        return results[:top_k]
