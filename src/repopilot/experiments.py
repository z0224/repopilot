"""Prepare isolated benchmark workspaces for experiments."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import shutil
from dataclasses import dataclass
from pathlib import Path

from .benchmarks import load_benchmark_manifest


@dataclass(frozen=True)
class ExperimentGroup:
    name: str
    use_rag: bool
    use_safety_requirements: bool


EXPERIMENT_GROUPS = {
    "baseline": ExperimentGroup(
        name="baseline",
        use_rag=False,
        use_safety_requirements=False,
    ),
    "safe": ExperimentGroup(
        name="safe",
        use_rag=False,
        use_safety_requirements=True,
    ),
    "rag": ExperimentGroup(
        name="rag",
        use_rag=True,
        use_safety_requirements=False,
    ),
    "rag_safe": ExperimentGroup(
        name="rag_safe",
        use_rag=True,
        use_safety_requirements=True,
    ),
}


@dataclass(frozen=True)
class PreparedExperiment:
    task_id: str
    group: ExperimentGroup
    workspace: Path
    task: str
    test_command: str
    relevant_files: tuple[str, ...]
    expected_baseline: dict[str, int]

def get_experiment_group(name: str) -> ExperimentGroup:
    try:
        return EXPERIMENT_GROUPS[name]
    except KeyError as error:
        choices = ", ".join(EXPERIMENT_GROUPS)
        raise ValueError(
            f"unknown experiment group {name!r}; "
            f"choose from: {choices}"
        ) from error


def _resolve_inside(
    root: Path,
    relative_path: str,
    *,
    label: str,
) -> Path:
    root = root.resolve()
    relative = Path(relative_path)

    if relative.is_absolute():
        raise ValueError(
            f"{label} must be a relative path"
        )

    resolved = (root / relative).resolve()

    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError(
            f"{label} escapes its allowed directory"
        ) from error

    return resolved


def prepare_experiment_workspace(
    manifest_path,
    task_id: str,
    group_name: str,
    output_root,
) -> PreparedExperiment:
    manifest_path = Path(
        manifest_path
    ).expanduser().resolve()
    manifest = load_benchmark_manifest(manifest_path)
    manifest_root = manifest_path.parent
    group = get_experiment_group(group_name)

    task = next(
        (
            candidate
            for candidate in manifest["tasks"]
            if candidate["id"] == task_id
        ),
        None,
    )

    if task is None:
        raise ValueError(
            f"unknown benchmark task: {task_id}"
        )

    source = _resolve_inside(
        manifest_root,
        task["project"],
        label="project path",
    )

    if not source.is_dir():
        raise FileNotFoundError(
            f"benchmark project not found: {source}"
        )

    output_root = Path(
        output_root
    ).expanduser().resolve()

    destination = _resolve_inside(
        output_root,
        f"{group.name}/{task_id}",
        label="experiment destination",
    )

    if destination.exists():
        raise FileExistsError(
            f"experiment workspace already exists: "
            f"{destination}"
        )

    bug_files = []

    for bug_file in task["bug_files"]:
        fixture = _resolve_inside(
            source,
            bug_file["fixture"],
            label="bug fixture",
        )
        target = _resolve_inside(
            destination,
            bug_file["target"],
            label="bug target",
        )

        if not fixture.is_file():
            raise FileNotFoundError(
                f"bug fixture not found: {fixture}"
            )

        bug_files.append((fixture, target))

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            ".pytest_cache",
            ".repopilot",
            ".git",
            "*.pyc",
        ),
    )
    for fixture, target in bug_files:
        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        shutil.copy2(fixture, target)

    return PreparedExperiment(
        task_id=task_id,
        group=group,
        workspace=destination,
        task=task["task"],
        test_command=task["test_command"],
        relevant_files=tuple(task["relevant_files"]),
        expected_baseline=dict(
            task.get("expected_baseline", {})
        ),
    )
@dataclass(frozen=True)
class ExperimentPlanItem:
    task_id: str
    group: ExperimentGroup
    task: str
    test_command: str

    @property
    def run_id(self) -> str:
        return f"{self.task_id}__{self.group.name}"

    def to_dict(self):
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "group": self.group.name,
            "use_rag": self.group.use_rag,
            "use_safety_requirements": (
                self.group.use_safety_requirements
            ),
            "task": self.task,
            "test_command": self.test_command,
        }


def build_experiment_plan(
    manifest_path,
    group_names=None,
):
    manifest = load_benchmark_manifest(manifest_path)

    if group_names is None:
        group_names = tuple(EXPERIMENT_GROUPS)
    else:
        group_names = tuple(group_names)

    if not group_names:
        raise ValueError(
            "at least one experiment group is required"
        )

    if len(set(group_names)) != len(group_names):
        raise ValueError(
            "experiment groups must not be duplicated"
        )

    groups = tuple(
        get_experiment_group(name)
        for name in group_names
    )

    return tuple(
        ExperimentPlanItem(
            task_id=task["id"],
            group=group,
            task=task["task"],
            test_command=task["test_command"],
        )
        for task in manifest["tasks"]
        for group in groups
    )


def write_experiment_plan(
    manifest_path,
    output_path,
    group_names=None,
):
    plan = build_experiment_plan(
        manifest_path,
        group_names,
    )
    output_path = Path(
        output_path
    ).expanduser().resolve()

    groups = []

    for item in plan:
        if item.group.name not in groups:
            groups.append(item.group.name)

    payload = {
        "schema_version": 1,
        "task_count": len(
            {item.task_id for item in plan}
        ),
        "group_count": len(groups),
        "run_count": len(plan),
        "groups": groups,
        "runs": [
            item.to_dict()
            for item in plan
        ],
    }

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    output_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return output_path, payload
def prepare_experiment_batch(
    manifest_path,
    output_root,
    *,
    group_names=None,
    task_ids=None,
    limit=None,
):
    plan = list(
        build_experiment_plan(
            manifest_path,
            group_names,
        )
    )

    if task_ids is not None:
        task_ids = tuple(task_ids)
        available_tasks = {
            item.task_id
            for item in plan
        }
        unknown_tasks = (
            set(task_ids) - available_tasks
        )

        if unknown_tasks:
            raise ValueError(
                "unknown benchmark tasks: "
                + ", ".join(sorted(unknown_tasks))
            )

        plan = [
            item
            for item in plan
            if item.task_id in task_ids
        ]

    if limit is not None:
        if limit < 1:
            raise ValueError(
                "experiment limit must be at least 1"
            )

        plan = plan[:limit]

    if not plan:
        raise ValueError(
            "experiment selection is empty"
        )

    output_root = Path(
        output_root
    ).expanduser().resolve()

    runs = []

    for item in plan:
        prepared = prepare_experiment_workspace(
            manifest_path,
            item.task_id,
            item.group.name,
            output_root,
        )

        baseline = run_experiment_baseline(
            prepared
        )
        status = (
            "baseline_verified"
            if baseline.matches_expected
            else "baseline_mismatch"
        )

        runs.append({
            "run_id": item.run_id,
            "task_id": item.task_id,
            "group": item.group.name,
            "use_rag": item.group.use_rag,
            "use_safety_requirements": (
                item.group.use_safety_requirements
            ),
            "workspace": str(prepared.workspace),
            "status": status,
            "baseline": baseline.to_dict(),
        })

    verified_count = sum(
        run["status"] == "baseline_verified"
        for run in runs
    )
    mismatch_count = sum(
        run["status"] == "baseline_mismatch"
        for run in runs
    )

    payload = {
        "schema_version": 2,
        "dry_run": True,
        "run_count": len(runs),
        "baseline_verified_count": verified_count,
        "baseline_mismatch_count": mismatch_count,
        "runs": runs,
    }

    batch_path = output_root / "batch.json"
    batch_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return batch_path, payload
@dataclass(frozen=True)
class BaselineResult:
    command: tuple[str, ...]
    returncode: int
    passed: int
    failed: int
    errors: int
    expected_passed: int
    expected_failed: int
    matches_expected: bool
    stdout: str
    stderr: str

    def to_dict(self):
        return {
            "command": list(self.command),
            "returncode": self.returncode,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "expected_passed": self.expected_passed,
            "expected_failed": self.expected_failed,
            "matches_expected": self.matches_expected,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


def parse_pytest_summary(output: str):
    counts = {
        "passed": 0,
        "failed": 0,
        "errors": 0,
    }

    pattern = re.compile(
        r"(\d+)\s+(passed|failed|errors?)\b"
    )

    for count, label in pattern.findall(output):
        if label in {"error", "errors"}:
            label = "errors"

        counts[label] = int(count)

    return counts


def run_experiment_baseline(
    prepared: PreparedExperiment,
    *,
    runner=subprocess.run,
):
    command = list(
        shlex.split(prepared.test_command)
    )

    if not command:
        raise ValueError(
            "baseline test command must not be empty"
        )

    if command[0] in {"python", "python3"}:
        command[0] = sys.executable

    command = tuple(command)
    completed = runner(
        list(command),
        cwd=str(prepared.workspace),
        capture_output=True,
        text=True,
        check=False,
    )

    combined_output = "\n".join(
        part
        for part in (
            completed.stdout,
            completed.stderr,
        )
        if part
    )
    counts = parse_pytest_summary(
        combined_output
    )

    expected_passed = int(
        prepared.expected_baseline.get(
            "passed",
            0,
        )
    )
    expected_failed = int(
        prepared.expected_baseline.get(
            "failed",
            0,
        )
    )

    matches_expected = (
        counts["passed"] == expected_passed
        and counts["failed"] == expected_failed
        and counts["errors"] == 0
    )

    return BaselineResult(
        command=command,
        returncode=completed.returncode,
        passed=counts["passed"],
        failed=counts["failed"],
        errors=counts["errors"],
        expected_passed=expected_passed,
        expected_failed=expected_failed,
        matches_expected=matches_expected,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
