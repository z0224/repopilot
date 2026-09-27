import json

import pytest

from repopilot.benchmarks import (
    build_retrieval_manifest,
    load_benchmark_manifest,
    write_retrieval_manifests,
)


def sample_manifest():
    return {
        "schema_version": 1,
        "task_count": 1,
        "tasks": [
            {
                "id": "task-001",
                "project": "task-001",
                "task": "Fix addition.",
                "task_zh": "修复加法。",
                "test_command": (
                    "python -m pytest -q"
                ),
                "bug_files": [
                    {
                        "fixture": "bug.txt",
                        "target": "service.py",
                    }
                ],
                "relevant_files": [
                    "service.py",
                    "test_service.py",
                ],
            }
        ],
    }


def test_builds_english_and_chinese_manifests():
    manifest = sample_manifest()

    english = build_retrieval_manifest(
        manifest,
        language="en",
    )
    chinese = build_retrieval_manifest(
        manifest,
        language="zh",
    )

    assert english["tasks"][0]["query"] == (
        "Fix addition."
    )
    assert chinese["tasks"][0]["query"] == (
        "修复加法。"
    )
    assert english["task_count"] == 1


def test_rejects_duplicate_task_ids():
    manifest = sample_manifest()
    manifest["tasks"].append(
        dict(manifest["tasks"][0])
    )
    manifest["task_count"] = 2

    with pytest.raises(
        ValueError,
        match="duplicate task id",
    ):
        build_retrieval_manifest(manifest)


def test_writes_retrieval_manifests(tmp_path):
    manifest_path = tmp_path / "benchmark.json"
    manifest_path.write_text(
        json.dumps(sample_manifest()),
        encoding="utf-8",
    )

    outputs = write_retrieval_manifests(
        manifest_path,
        output_directory=tmp_path / "output",
    )

    assert outputs["en"].is_file()
    assert outputs["zh"].is_file()

    chinese = json.loads(
        outputs["zh"].read_text(
            encoding="utf-8"
        )
    )

    assert chinese["language"] == "zh"
    assert chinese["tasks"][0]["query"] == "修复加法。"


def test_loads_and_validates_manifest(tmp_path):
    manifest_path = tmp_path / "benchmark.json"
    manifest_path.write_text(
        json.dumps(sample_manifest()),
        encoding="utf-8",
    )

    loaded = load_benchmark_manifest(
        manifest_path
    )

    assert loaded["task_count"] == 1
