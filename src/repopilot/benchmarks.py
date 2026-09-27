"""Benchmark manifest loading and retrieval-manifest generation."""

from __future__ import annotations

import json
from pathlib import Path


REQUIRED_TASK_FIELDS = {
    "id",
    "project",
    "task",
    "task_zh",
    "relevant_files",
    "bug_files",
    "test_command",
}


def validate_benchmark_manifest(manifest):
    if not isinstance(manifest, dict):
        raise ValueError(
            "benchmark manifest must be a JSON object"
        )

    tasks = manifest.get("tasks")

    if not isinstance(tasks, list):
        raise ValueError(
            "benchmark manifest must contain a tasks list"
        )

    declared_count = manifest.get("task_count")

    if (
        declared_count is not None
        and declared_count != len(tasks)
    ):
        raise ValueError(
            "task_count does not match tasks list"
        )

    seen_ids = set()

    for position, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            raise ValueError(
                f"task {position} must be an object"
            )

        missing = REQUIRED_TASK_FIELDS - set(task)

        if missing:
            raise ValueError(
                f"task {position} is missing fields: "
                + ", ".join(sorted(missing))
            )

        task_id = task["id"]

        if task_id in seen_ids:
            raise ValueError(
                f"duplicate task id: {task_id}"
            )

        seen_ids.add(task_id)

        if not task["relevant_files"]:
            raise ValueError(
                f"{task_id} has no relevant files"
            )

        if not task["bug_files"]:
            raise ValueError(
                f"{task_id} has no bug files"
            )

    return manifest


def load_benchmark_manifest(path):
    path = Path(path).expanduser().resolve()

    if not path.is_file():
        raise FileNotFoundError(
            f"benchmark manifest not found: {path}"
        )

    manifest = json.loads(
        path.read_text(encoding="utf-8")
    )

    return validate_benchmark_manifest(manifest)


def build_retrieval_manifest(
    benchmark_manifest,
    *,
    language="en",
):
    validate_benchmark_manifest(
        benchmark_manifest
    )

    if language not in {"en", "zh"}:
        raise ValueError(
            "language must be 'en' or 'zh'"
        )

    query_field = (
        "task_zh"
        if language == "zh"
        else "task"
    )

    return {
        "schema_version": 1,
        "language": language,
        "task_count": len(
            benchmark_manifest["tasks"]
        ),
        "tasks": [
            {
                "id": task["id"],
                "project": task["project"],
                "query": task[query_field],
                "relevant_files": list(
                    task["relevant_files"]
                ),
            }
            for task in benchmark_manifest["tasks"]
        ],
    }


def write_retrieval_manifests(
    manifest_path,
    *,
    output_directory=None,
):
    manifest_path = Path(
        manifest_path
    ).expanduser().resolve()

    benchmark_manifest = load_benchmark_manifest(
        manifest_path
    )

    if output_directory is None:
        output_directory = manifest_path.parent
    else:
        output_directory = Path(
            output_directory
        ).expanduser().resolve()

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    outputs = {
        "en": (
            output_directory
            / "retrieval-ground-truth.json"
        ),
        "zh": (
            output_directory
            / "retrieval-ground-truth-zh.json"
        ),
    }

    for language, output_path in outputs.items():
        retrieval_manifest = (
            build_retrieval_manifest(
                benchmark_manifest,
                language=language,
            )
        )
        output_path.write_text(
            json.dumps(
                retrieval_manifest,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    return outputs
