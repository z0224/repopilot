#!/usr/bin/env python3

import argparse
import hashlib
import json
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    ".repopilot",
    "__pycache__",
    ".pytest_cache",
}

TRACKED_SUFFIXES = {".py"}


def sha256_text(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def collect_files(project):
    """Collect Python source and test files from a project."""
    files = {}

    for path in sorted(project.rglob("*")):
        if not path.is_file():
            continue

        relative_path = path.relative_to(project)

        if any(part in IGNORED_DIRECTORIES for part in relative_path.parts):
            continue

        if path.suffix not in TRACKED_SUFFIXES:
            continue

        content = path.read_text(encoding="utf-8")

        files[str(relative_path)] = {
            "sha256": sha256_text(content),
            "line_count": len(content.splitlines()),
            "content": content,
        }

    return files


def run_test_command(project, command):
    """Run a controlled local test command and capture its result."""
    started_at = time.perf_counter()

    completed = subprocess.run(
        shlex.split(command),
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )

    duration = time.perf_counter() - started_at

    return {
        "command": command,
        "returncode": completed.returncode,
        "duration_seconds": round(duration, 4),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def start_baseline(project_path, test_command):
    project = Path(project_path).expanduser().resolve()

    if not project.is_dir():
        raise SystemExit(f"Project directory does not exist: {project}")

    state_directory = project / ".repopilot"
    state_directory.mkdir(exist_ok=True)

    baseline = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project": str(project),
        "files": collect_files(project),
        "baseline_test": run_test_command(project, test_command),
    }

    output_path = state_directory / "baseline.json"
    output_path.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    test_result = baseline["baseline_test"]
    tracked_files = len(baseline["files"])

    print(f"Baseline saved to: {output_path}")
    print(f"Tracked files: {tracked_files}")
    print(f"Test return code: {test_result['returncode']}")
    print(f"Test duration: {test_result['duration_seconds']}s")

    if test_result["stdout"]:
        print("\nTest stdout:")
        print(test_result["stdout"])

    if test_result["stderr"]:
        print("\nTest stderr:")
        print(test_result["stderr"])


def build_parser():
    parser = argparse.ArgumentParser(
        description="Audit AI agent code changes."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser(
        "start",
        help="Save a source snapshot and run baseline tests.",
    )
    start_parser.add_argument(
        "project",
        help="Path to the project being evaluated.",
    )
    start_parser.add_argument(
        "--test-command",
        default="python -m pytest -q",
        help="Test command to run.",
    )

    return parser


def main():
    parser = build_parser()
    arguments = parser.parse_args()

    if arguments.command == "start":
        start_baseline(arguments.project, arguments.test_command)


if __name__ == "__main__":
    main()
