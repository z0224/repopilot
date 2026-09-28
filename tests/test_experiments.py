from pathlib import Path
import subprocess
import sys
import pytest

from repopilot.experiments import (
    EXPERIMENT_GROUPS,
    get_experiment_group,
    prepare_experiment_workspace,
)


MANIFEST = (
    Path(__file__).parent.parent
    / "benchmarks"
    / "benchmark-manifest.json"
)


def test_experiment_group_matrix():
    assert len(EXPERIMENT_GROUPS) == 4

    assert get_experiment_group("baseline").use_rag is False
    assert (
        get_experiment_group(
            "baseline"
        ).use_safety_requirements
        is False
    )

    assert get_experiment_group("safe").use_rag is False
    assert (
        get_experiment_group(
            "safe"
        ).use_safety_requirements
        is True
    )

    assert get_experiment_group("rag").use_rag is True
    assert (
        get_experiment_group(
            "rag"
        ).use_safety_requirements
        is False
    )

    assert get_experiment_group("rag_safe").use_rag is True
    assert (
        get_experiment_group(
            "rag_safe"
        ).use_safety_requirements
        is True
    )


def test_prepare_workspace_applies_bug_fixture(tmp_path):
    prepared = prepare_experiment_workspace(
        MANIFEST,
        "task-001",
        "baseline",
        tmp_path,
    )

    source = (
        prepared.workspace / "calculator.py"
    ).read_text(encoding="utf-8")

    assert prepared.workspace.is_dir()
    assert prepared.task_id == "task-001"
    assert prepared.group.name == "baseline"
    assert "return a - b" in source

    assert not (
        prepared.workspace / "__pycache__"
    ).exists()
    assert not (
        prepared.workspace / ".pytest_cache"
    ).exists()
    assert not (
        prepared.workspace / ".repopilot"
    ).exists()

    source = (
        prepared.workspace / "calculator.py"
    ).read_text(encoding="utf-8")

    assert prepared.workspace.is_dir()
    assert prepared.task_id == "task-001"
    assert prepared.group.name == "baseline"
    assert "return a - b" in source


def test_prepare_workspace_refuses_existing_directory(
    tmp_path,
):
    prepare_experiment_workspace(
        MANIFEST,
        "task-001",
        "safe",
        tmp_path,
    )

    with pytest.raises(FileExistsError):
        prepare_experiment_workspace(
            MANIFEST,
            "task-001",
            "safe",
            tmp_path,
        )


def test_unknown_experiment_group_is_rejected():
    with pytest.raises(
        ValueError,
        match="unknown experiment group",
    ):
        get_experiment_group("unknown")

def test_prepare_experiment_cli(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "repopilot",
            "prepare-experiment",
            str(MANIFEST),
            "--task",
            "task-001",
            "--group",
            "rag_safe",
            "--output-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    workspace = (
        tmp_path / "rag_safe" / "task-001"
    )

    assert result.returncode == 0
    assert "Group: rag_safe" in result.stdout
    assert "Use RAG: True" in result.stdout
    assert "Use safety requirements: True" in result.stdout
    assert workspace.is_dir()
    assert "return a - b" in (
        workspace / "calculator.py"
    ).read_text(encoding="utf-8")
