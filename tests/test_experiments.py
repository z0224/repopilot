from pathlib import Path
import subprocess
import sys
import pytest
import json
from repopilot.experiments import (
    build_experiment_plan,
    write_experiment_plan,
    EXPERIMENT_GROUPS,
    get_experiment_group,
    prepare_experiment_batch,
    prepare_experiment_workspace,
    parse_pytest_summary,
    run_experiment_baseline,
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
def test_builds_complete_experiment_plan():
    plan = build_experiment_plan(MANIFEST)

    assert len(plan) == 40
    assert len(
        {item.run_id for item in plan}
    ) == 40

    combinations = {
        (item.task_id, item.group.name)
        for item in plan
    }

    assert (
        "task-001",
        "baseline",
    ) in combinations
    assert (
        "task-010",
        "rag_safe",
    ) in combinations


def test_experiment_plan_supports_group_subset():
    plan = build_experiment_plan(
        MANIFEST,
        ("safe",),
    )

    assert len(plan) == 10
    assert all(
        item.group.name == "safe"
        for item in plan
    )
    assert all(
        item.group.use_rag is False
        for item in plan
    )
    assert all(
        item.group.use_safety_requirements is True
        for item in plan
    )


def test_writes_machine_readable_experiment_plan(
    tmp_path,
):
    output_path, payload = write_experiment_plan(
        MANIFEST,
        tmp_path / "experiment-plan.json",
    )

    assert output_path.is_file()
    assert payload["task_count"] == 10
    assert payload["group_count"] == 4
    assert payload["run_count"] == 40
    assert len(payload["runs"]) == 40

def test_plan_experiments_cli(tmp_path):
    output_path = (
        tmp_path / "experiment-plan.json"
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "repopilot",
            "plan-experiments",
            str(MANIFEST),
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Tasks: 10" in result.stdout
    assert "Groups: 4" in result.stdout
    assert "Runs: 40" in result.stdout

    payload = json.loads(
        output_path.read_text(encoding="utf-8")
    )

    assert payload["run_count"] == 40
    assert len(payload["runs"]) == 40
def test_prepares_filtered_experiment_batch(tmp_path):
    batch_path, payload = (
        prepare_experiment_batch(
            MANIFEST,
            tmp_path,
            group_names=("baseline", "safe"),
            task_ids=("task-001",),
            limit=2,
        )
    )

    assert batch_path.is_file()
    assert payload["dry_run"] is True
    assert payload["run_count"] == 2
    assert (
        payload["baseline_verified_count"]
        == 2
    )
    assert (
        payload["baseline_mismatch_count"]
        == 0
    )
    assert {
        run["status"]
        for run in payload["runs"]
    } == {"baseline_verified"}
    assert all(
        run["baseline"]["matches_expected"]
        for run in payload["runs"]
    )
    assert {
        run["group"]
        for run in payload["runs"]
    } == {"baseline", "safe"}

    assert (
        tmp_path
        / "baseline"
        / "task-001"
        / "calculator.py"
    ).is_file()


def test_run_experiments_cli_dry_run(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "repopilot",
            "run-experiments",
            str(MANIFEST),
            "--output-root",
            str(tmp_path),
            "--task",
            "task-001",
            "--group",
            "baseline",
            "--limit",
            "1",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Dry run: True" in result.stdout
    assert "Prepared runs: 1" in result.stdout
    assert (tmp_path / "batch.json").is_file()
    assert "Baseline verified: 1" in result.stdout
    assert "Baseline mismatches: 0" in result.stdout
def test_parses_pytest_summary():
    counts = parse_pytest_summary(
        "3 failed, 5 passed in 0.02s"
    )

    assert counts == {
        "passed": 5,
        "failed": 3,
        "errors": 0,
    }


def test_runs_and_validates_expected_baseline(
    tmp_path,
):
    prepared = prepare_experiment_workspace(
        MANIFEST,
        "task-001",
        "baseline",
        tmp_path,
    )

    result = run_experiment_baseline(prepared)

    assert result.returncode == 1
    assert result.passed == 0
    assert result.failed == 1
    assert result.errors == 0
    assert result.matches_expected is True
