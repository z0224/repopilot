"""Evaluate repository retrieval at file level."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from .indexer import index_repository
from .lexical import LexicalRetriever
from .semantic import (
    SemanticRetriever,
    SentenceTransformerEmbedder,
)


DEFAULT_K_VALUES = (1, 3, 5)


def normalize_path(path):
    return str(path).replace("\\", "/")


def unique_ranked_files(results):
    """Convert ranked chunks into ranked unique file paths."""
    files = []
    seen = set()

    for result in results:
        path = normalize_path(result.chunk.path)

        if path in seen:
            continue

        seen.add(path)
        files.append(path)

    return tuple(files)


@dataclass(frozen=True)
class RetrievalEvaluation:
    task_id: str
    query: str
    relevant_files: tuple[str, ...]
    retrieved_files: tuple[str, ...]
    recall_at: dict[int, float]
    reciprocal_rank: float

    def to_dict(self):
        return {
            "task_id": self.task_id,
            "query": self.query,
            "relevant_files": list(self.relevant_files),
            "retrieved_files": list(self.retrieved_files),
            "recall_at": {
                str(k): value
                for k, value in self.recall_at.items()
            },
            "reciprocal_rank": self.reciprocal_rank,
        }


def evaluate_results(
    *,
    task_id,
    query,
    relevant_files,
    results,
    k_values=DEFAULT_K_VALUES,
):
    relevant = tuple(
        dict.fromkeys(
            normalize_path(path)
            for path in relevant_files
        )
    )

    if not relevant:
        raise ValueError(
            "relevant_files must contain at least one path"
        )

    retrieved = unique_ranked_files(results)
    relevant_set = set(relevant)
    recall_at = {}

    for k in k_values:
        if k < 1:
            raise ValueError("k values must be at least 1")

        hits = len(
            relevant_set.intersection(retrieved[:k])
        )
        recall_at[k] = round(
            hits / len(relevant_set),
            6,
        )

    reciprocal_rank = 0.0

    for rank, path in enumerate(retrieved, start=1):
        if path in relevant_set:
            reciprocal_rank = round(1.0 / rank, 6)
            break

    return RetrievalEvaluation(
        task_id=task_id,
        query=query,
        relevant_files=relevant,
        retrieved_files=retrieved,
        recall_at=recall_at,
        reciprocal_rank=reciprocal_rank,
    )


def aggregate_evaluations(
    evaluations,
    k_values=DEFAULT_K_VALUES,
):
    evaluations = tuple(evaluations)

    if not evaluations:
        return {
            "task_count": 0,
            "mean_recall_at": {
                str(k): 0.0
                for k in k_values
            },
            "mean_reciprocal_rank": 0.0,
        }

    return {
        "task_count": len(evaluations),
        "mean_recall_at": {
            str(k): round(
                mean(
                    evaluation.recall_at[k]
                    for evaluation in evaluations
                ),
                6,
            )
            for k in k_values
        },
        "mean_reciprocal_rank": round(
            mean(
                evaluation.reciprocal_rank
                for evaluation in evaluations
            ),
            6,
        ),
    }


def evaluate_lexical_manifest(
    manifest_path,
    k_values=DEFAULT_K_VALUES,
):
    """Evaluate lexical retrieval using a JSON manifest."""
    manifest_path = Path(
        manifest_path
    ).expanduser().resolve()

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )
    tasks = manifest.get("tasks")

    if not isinstance(tasks, list):
        raise ValueError(
            "manifest must contain a tasks list"
        )

    evaluations = []
    benchmark_root = manifest_path.parent

    for task in tasks:
        task_id = task["id"]
        project = benchmark_root / task["project"]
        query = task["query"]
        relevant_files = task["relevant_files"]

        index = index_repository(project)
        retriever = LexicalRetriever(index.chunks)

        # Search all positively-scored chunks so file-level
        # evaluation is not dominated by many chunks from one file.
        results = retriever.search(
            query,
            top_k=max(1, len(index.chunks)),
        )

        evaluations.append(
            evaluate_results(
                task_id=task_id,
                query=query,
                relevant_files=relevant_files,
                results=results,
                k_values=k_values,
            )
        )

    return {
        "schema_version": 1,
        "retriever": "lexical",
        "manifest": str(manifest_path),
        "tasks": [
            evaluation.to_dict()
            for evaluation in evaluations
        ],
        "aggregate": aggregate_evaluations(
            evaluations,
            k_values=k_values,
        ),
    }


def evaluate_semantic_manifest(
    manifest_path,
    embedder=None,
    k_values=DEFAULT_K_VALUES,
):
    """Evaluate semantic retrieval using a JSON manifest."""
    manifest_path = Path(
        manifest_path
    ).expanduser().resolve()

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )
    tasks = manifest.get("tasks")

    if not isinstance(tasks, list):
        raise ValueError(
            "manifest must contain a tasks list"
        )

    if embedder is None:
        embedder = SentenceTransformerEmbedder()

    evaluations = []
    benchmark_root = manifest_path.parent

    for task in tasks:
        project = benchmark_root / task["project"]
        index = index_repository(project)
        retriever = SemanticRetriever(
            index.chunks,
            embedder,
        )

        results = retriever.search(
            task["query"],
            top_k=max(1, len(index.chunks)),
        )

        evaluations.append(
            evaluate_results(
                task_id=task["id"],
                query=task["query"],
                relevant_files=task["relevant_files"],
                results=results,
                k_values=k_values,
            )
        )

    return {
        "schema_version": 1,
        "retriever": "semantic",
        "model": getattr(
            embedder,
            "model_name",
            type(embedder).__name__,
        ),
        "manifest": str(manifest_path),
        "tasks": [
            evaluation.to_dict()
            for evaluation in evaluations
        ],
        "aggregate": aggregate_evaluations(
            evaluations,
            k_values=k_values,
        ),
    }
