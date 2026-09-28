"""Prepare isolated benchmark workspaces for experiments."""

from __future__ import annotations

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
    )
