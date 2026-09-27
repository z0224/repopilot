import json

import pytest

from repopilot.retrieval import (
    RetrievalResult,
    aggregate_evaluations,
    chunk_python_source,
    evaluate_lexical_manifest,
    evaluate_results,
    unique_ranked_files,
)


def make_result(path, symbol, score):
    chunk = chunk_python_source(
        f"def {symbol}():\n    return True\n",
        path,
    )[0]

    return RetrievalResult(
        chunk=chunk,
        score=score,
        matched_terms=("test",),
        field_matches={"content": ("test",)},
    )


def test_unique_ranked_files_removes_duplicate_paths():
    results = [
        make_result("tests/test_service.py", "test_one", 3),
        make_result("tests/test_service.py", "test_two", 2),
        make_result("service.py", "run", 1),
    ]

    assert unique_ranked_files(results) == (
        "tests/test_service.py",
        "service.py",
    )


def test_evaluates_file_recall_and_reciprocal_rank():
    results = [
        make_result("unrelated.py", "other", 3),
        make_result("service.py", "run", 2),
        make_result("tests/test_service.py", "test_run", 1),
    ]

    evaluation = evaluate_results(
        task_id="task-001",
        query="run service",
        relevant_files=[
            "service.py",
            "tests/test_service.py",
        ],
        results=results,
    )

    assert evaluation.recall_at[1] == 0.0
    assert evaluation.recall_at[3] == 1.0
    assert evaluation.reciprocal_rank == 0.5


def test_aggregate_evaluations():
    first = evaluate_results(
        task_id="one",
        query="service",
        relevant_files=["service.py"],
        results=[
            make_result("service.py", "run", 1),
        ],
    )
    second = evaluate_results(
        task_id="two",
        query="missing",
        relevant_files=["missing.py"],
        results=[],
    )

    aggregate = aggregate_evaluations([first, second])

    assert aggregate["task_count"] == 2
    assert aggregate["mean_recall_at"]["1"] == 0.5
    assert aggregate["mean_reciprocal_rank"] == 0.5


def test_evaluates_manifest(tmp_path):
    benchmark_root = tmp_path / "benchmarks"
    project = benchmark_root / "task-001"
    project.mkdir(parents=True)

    (project / "service.py").write_text(
        '''def calculate_total(items):
    """Calculate a total price."""
    return sum(items)
''',
        encoding="utf-8",
    )

    manifest = benchmark_root / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "task-001",
                        "project": "task-001",
                        "query": "calculate total price",
                        "relevant_files": ["service.py"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = evaluate_lexical_manifest(manifest)

    assert report["retriever"] == "lexical"
    assert report["aggregate"]["task_count"] == 1
    assert report["aggregate"]["mean_recall_at"]["1"] == 1.0


def test_rejects_empty_relevant_files():
    with pytest.raises(ValueError):
        evaluate_results(
            task_id="empty",
            query="anything",
            relevant_files=[],
            results=[],
        )


class FakeCrossLanguageEmbedder:
    model_name = "fake-cross-language"

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

            vectors.append([
                float(inventory),
                float(atomic),
            ])

        return vectors


def test_evaluates_semantic_manifest(tmp_path):
    benchmark_root = tmp_path / "benchmarks"
    project = benchmark_root / "task-001"
    project.mkdir(parents=True)

    (project / "inventory.py").write_text(
        '''def reserve_inventory(items):
    """Atomically reserve inventory."""
    return items
''',
        encoding="utf-8",
    )

    manifest = benchmark_root / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "task-001",
                        "project": "task-001",
                        "query": "库存预留必须具有原子性",
                        "relevant_files": [
                            "inventory.py"
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    from repopilot.retrieval import (
        evaluate_semantic_manifest,
    )

    report = evaluate_semantic_manifest(
        manifest,
        embedder=FakeCrossLanguageEmbedder(),
    )

    assert report["retriever"] == "semantic"
    assert report["model"] == "fake-cross-language"
    assert report["aggregate"]["mean_recall_at"]["1"] == 1.0

def test_evaluates_hybrid_manifest(tmp_path):
    benchmark_root = tmp_path / "benchmarks"
    project = benchmark_root / "task-001"
    project.mkdir(parents=True)

    (project / "inventory.py").write_text(
        '''def reserve_inventory(items):
    """Atomically reserve inventory."""
    return items
''',
        encoding="utf-8",
    )

    manifest = benchmark_root / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "task-001",
                        "project": "task-001",
                        "query": "库存预留必须具有原子性",
                        "relevant_files": [
                            "inventory.py"
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    from repopilot.retrieval import (
        evaluate_hybrid_manifest,
    )

    report = evaluate_hybrid_manifest(
        manifest,
        embedder=FakeCrossLanguageEmbedder(),
    )

    assert report["retriever"] == "hybrid"
    assert report["fusion"] == (
        "reciprocal_rank_fusion"
    )
    assert report["model"] == "fake-cross-language"
    assert report["aggregate"]["mean_recall_at"]["1"] == 1.0
