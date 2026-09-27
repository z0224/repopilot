"""Explainable weighted lexical retrieval for code chunks."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .chunker import CodeChunk


FIELD_WEIGHTS = {
    "symbol": 5.0,
    "path": 3.0,
    "imports": 2.5,
    "docstring": 2.0,
    "content": 1.0,
}

STOP_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "class",
    "def",
    "for",
    "from",
    "in",
    "import",
    "is",
    "none",
    "of",
    "or",
    "return",
    "self",
    "the",
    "to",
    "true",
    "false",
    "with",
}


@dataclass(frozen=True)
class RetrievalResult:
    """One ranked lexical retrieval result."""

    chunk: CodeChunk
    score: float
    matched_terms: tuple[str, ...]
    field_matches: dict[str, tuple[str, ...]]

    def to_dict(self):
        return {
            "chunk": self.chunk.to_dict(),
            "score": self.score,
            "matched_terms": list(self.matched_terms),
            "field_matches": {
                field: list(terms)
                for field, terms in self.field_matches.items()
            },
        }


def tokenize(text):
    """Tokenize prose, paths, snake_case and camelCase."""
    if not text:
        return []

    expanded = re.sub(
        r"([a-z0-9])([A-Z])",
        r"\1 \2",
        str(text),
    )
    expanded = expanded.replace("_", " ")

    tokens = re.findall(
        r"[A-Za-z0-9]+|[\u4e00-\u9fff]+",
        expanded,
    )

    return [
        token.lower()
        for token in tokens
        if token.lower() not in STOP_WORDS
    ]


def chunk_fields(chunk):
    return {
        "symbol": tokenize(chunk.symbol),
        "path": tokenize(chunk.path),
        "imports": tokenize(" ".join(chunk.imports)),
        "docstring": tokenize(chunk.docstring or ""),
        "content": tokenize(chunk.content),
    }


class LexicalRetriever:
    """Rank code chunks using weighted token overlap."""

    def __init__(self, chunks):
        self.chunks = tuple(chunks)
        self._fields = {
            chunk.chunk_id: chunk_fields(chunk)
            for chunk in self.chunks
        }
        self._document_frequencies = (
            self._calculate_document_frequencies()
        )

    def _calculate_document_frequencies(self):
        frequencies = Counter()

        for fields in self._fields.values():
            document_terms = set()

            for tokens in fields.values():
                document_terms.update(tokens)

            frequencies.update(document_terms)

        return frequencies

    def _idf(self, term):
        document_count = len(self.chunks)
        document_frequency = self._document_frequencies.get(
            term,
            0,
        )

        return math.log(
            (document_count + 1)
            / (document_frequency + 1)
        ) + 1.0

    def _score_chunk(self, chunk, query_terms):
        fields = self._fields[chunk.chunk_id]
        score = 0.0
        field_matches = {}

        for field_name, tokens in fields.items():
            counts = Counter(tokens)
            matched = []

            for term in query_terms:
                frequency = counts.get(term, 0)

                if not frequency:
                    continue

                matched.append(term)
                score += (
                    FIELD_WEIGHTS[field_name]
                    * self._idf(term)
                    * (1.0 + math.log(frequency))
                )

            if matched:
                field_matches[field_name] = tuple(
                    dict.fromkeys(matched)
                )

        symbol_terms = set(fields["symbol"])

        if (
            symbol_terms
            and symbol_terms.issubset(set(query_terms))
        ):
            score += 2.0 * len(symbol_terms)

        matched_terms = tuple(
            term
            for term in query_terms
            if any(
                term in matches
                for matches in field_matches.values()
            )
        )

        return RetrievalResult(
            chunk=chunk,
            score=round(score, 6),
            matched_terms=matched_terms,
            field_matches=field_matches,
        )

    def search(self, query, top_k=5, include_zero=False):
        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        query_terms = tuple(
            dict.fromkeys(tokenize(query))
        )

        if not query_terms:
            return []

        results = [
            self._score_chunk(chunk, query_terms)
            for chunk in self.chunks
        ]

        if not include_zero:
            results = [
                result
                for result in results
                if result.score > 0
            ]

        results.sort(
            key=lambda result: (
                -result.score,
                result.chunk.chunk_id,
            )
        )

        return results[:top_k]


def search_chunks(chunks, query, top_k=5):
    """Convenience function for one lexical search."""
    return LexicalRetriever(chunks).search(
        query,
        top_k=top_k,
    )
