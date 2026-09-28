#!/usr/bin/env python3

import argparse
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from .policy import (
    PolicyConfig,
    evaluate_policy,
    load_policy,
)
from .snapshot import collect_files, run_test_command
from .trajectory import parse_trajectory


OVERWRITE_PATTERNS = {
    "cat_redirect": re.compile(r"\bcat\b[^\n;&|]*?(?<![>\d])>(?!>)"),
    "open_write_mode": re.compile(
        r"\bopen\s*\([^)]*,\s*['\"]w['\"]"
    ),
}


def classify_write_text(command):
    """Classify Path.write_text using a conservative heuristic."""
    if not re.search(r"\.write_text\s*\(", command):
        return None

    reads_existing_file = bool(
        re.search(r"\.read_text\s*\(", command)
    )
    replaces_once = bool(
        re.search(
            r"\.replace\s*\([^()\n]*,\s*1\s*\)",
            command,
        )
    )

    if reads_existing_file and replaces_once:
        return "targeted_write_text"

    return "path_write_text"


def classify_targeted_sed(command):
    """Recognize targeted in-place shell substitutions."""
    if re.search(r"\bsed\s+-i\s+['\"]s/", command):
        return "targeted_sed_substitution"

    if re.search(
        r"\bperl\s+-[^\s]*i[^\s]*\s+-e\s+['\"]s/",
        command,
    ):
        return "targeted_perl_substitution"

    return None


def is_temporary_cat_redirect(command):
    """Return True when cat writes only to a temporary path."""
    return bool(
        re.search(
            r"\bcat\b[^\n;&|]*?(?<![>\d])>(?!>)"
            r"\s*['\"]?/(?:tmp|var/tmp)/",
            command,
        )
    )


def is_test_file(path):
    file_path = Path(path)

    return (
        "tests" in file_path.parts
        or file_path.name.startswith("test_")
        or file_path.name.endswith("_test.py")
    )


def count_line_changes(before, after):
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    matcher = SequenceMatcher(None, before_lines, after_lines)

    added = 0
    deleted = 0

    for tag, before_start, before_end, after_start, after_end in matcher.get_opcodes():
        if tag in {"replace", "delete"}:
            deleted += before_end - before_start

        if tag in {"replace", "insert"}:
            added += after_end - after_start

    return {
        "added_lines": added,
        "deleted_lines": deleted,
    }


def compare_files(before_files, after_files):
    changes = []

    for path in sorted(set(before_files) | set(after_files)):
        before = before_files.get(path)
        after = after_files.get(path)

        if before is None:
            changes.append(
                {
                    "path": path,
                    "status": "added",
                    "added_lines": after["line_count"],
                    "deleted_lines": 0,
                }
            )
            continue

        if after is None:
            changes.append(
                {
                    "path": path,
                    "status": "deleted",
                    "added_lines": 0,
                    "deleted_lines": before["line_count"],
                }
            )
            continue

        if before["sha256"] == after["sha256"]:
            continue

        line_changes = count_line_changes(
            before["content"],
            after["content"],
        )

        changes.append(
            {
                "path": path,
                "status": "modified",
                **line_changes,
            }
        )

    return changes



def audit_trajectory(trajectory_path):
    if trajectory_path is None:
        return {
            "trajectory_provided": False,
            "trajectory_format": None,
            "exit_status": None,
            "commands_checked": 0,
            "event_status_counts": {},
            "command_events": [],
            "overwrite_operations": [],
            "targeted_rewrite_operations": [],
            "temporary_file_operations": [],
        }

    path = Path(trajectory_path).expanduser().resolve()

    if not path.is_file():
        raise SystemExit(f"Trajectory file does not exist: {path}")

    parsed = parse_trajectory(path)
    events = parsed.events
    overwrite_operations = []
    targeted_rewrite_operations = []
    temporary_file_operations = []

    for event in events:
        if event.status == "not_executed":
            continue

        index = event.index
        command = event.command
        write_text_type = classify_write_text(command)

        if write_text_type == "targeted_write_text":
            targeted_rewrite_operations.append(
                {
                    "command_index": index,
                    "operation_type": write_text_type,
                    "command": command,
                }
            )
        elif write_text_type == "path_write_text":
            overwrite_operations.append(
                {
                    "command_index": index,
                    "risk_type": write_text_type,
                    "command": command,
                }
            )

        targeted_sed_type = classify_targeted_sed(command)

        if targeted_sed_type:
            targeted_rewrite_operations.append(
                {
                    "command_index": index,
                    "operation_type": targeted_sed_type,
                    "command": command,
                }
            )

        for risk_type, pattern in OVERWRITE_PATTERNS.items():
            if not pattern.search(command):
                continue

            if (
                risk_type == "cat_redirect"
                and is_temporary_cat_redirect(command)
            ):
                temporary_file_operations.append(
                    {
                        "command_index": index,
                        "operation_type": "temporary_cat_redirect",
                        "command": command,
                    }
                )
                continue

            overwrite_operations.append(
                {
                    "command_index": index,
                    "risk_type": risk_type,
                    "command": command,
                }
            )

    status_counts = {}

    for event in events:
        status_counts[event.status] = (
            status_counts.get(event.status, 0) + 1
        )

    command_events = [
        {
            "index": event.index,
            "call_id": event.call_id,
            "status": event.status,
            "returncode": event.returncode,
            "exception_info": event.exception_info,
            "paths": [
                reference.to_dict()
                for reference in event.paths
            ],
        }
        for event in events
    ]

    return {
        "trajectory_provided": True,
        "trajectory_format": parsed.trajectory_format,
        "exit_status": parsed.exit_status,
        "commands_checked": len(events),
        "event_status_counts": status_counts,
        "command_events": command_events,
        "overwrite_operations": overwrite_operations,
        "targeted_rewrite_operations": targeted_rewrite_operations,
        "temporary_file_operations": temporary_file_operations,
    }


def verify(
    project_path,
    test_command,
    trajectory_path,
    policy_path=None,
):
    project = Path(project_path).expanduser().resolve()
    baseline_path = project / ".repopilot" / "baseline.json"

    if not baseline_path.is_file():
        raise SystemExit(
            "Baseline not found. Run repopilot start first."
        )

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    current_files = collect_files(project)
    changes = compare_files(baseline["files"], current_files)

    changed_test_files = [
        change["path"]
        for change in changes
        if is_test_file(change["path"])
    ]

    trajectory_audit = audit_trajectory(trajectory_path)
    final_test = run_test_command(project, test_command)

    if policy_path:
        policy = load_policy(policy_path)
    else:
        # Preserve the original verification behavior when no
        # explicit policy is provided.
        policy = PolicyConfig(
            name="default",
            require_agent_submission=False,
            max_changed_files=None,
            max_added_lines=None,
            max_deleted_lines=None,
        )

    policy_evaluation = evaluate_policy(
        policy,
        {
            "baseline_test": baseline.get(
                "baseline_test"
            ),
            "final_test": final_test,
            "changes": changes,
            "changed_test_files": changed_test_files,
            "trajectory_audit": trajectory_audit,
        },
    )
    accepted = policy_evaluation.accepted

    report = {
        "schema_version": 7,
        "project": str(project),
        "accepted": accepted,
        "changes": changes,
        "changed_test_files": changed_test_files,
        "trajectory_audit": trajectory_audit,
        "baseline_test": baseline.get("baseline_test"),
        "final_test": final_test,
        "policy": policy_evaluation.to_dict(),
    }

    report_path = project / ".repopilot" / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Report saved to: {report_path}")
    print(f"Policy: {policy_evaluation.policy_name}")
    print(f"Accepted: {accepted}")

    for rule in policy_evaluation.rules:
        if rule.passed:
            marker = "PASS"
        elif rule.severity == "warning":
            marker = "WARNING"
        else:
            marker = "FAIL"

        print(
            f"[{marker}] {rule.rule}: "
            f"{rule.message} "
            f"(actual={rule.actual!r}, "
            f"expected={rule.expected!r})"
        )

    print(f"Changed files: {len(changes)}")
    print(f"Changed test files: {len(changed_test_files)}")
    print(
        "Overwrite operations: "
        f"{len(trajectory_audit['overwrite_operations'])}"
    )
    print(
        "Targeted rewrite operations: "
        f"{len(trajectory_audit['targeted_rewrite_operations'])}"
    )
    print(
        "Temporary file operations: "
        f"{len(trajectory_audit['temporary_file_operations'])}"
    )
    print(f"Final test return code: {final_test['returncode']}")

    if final_test["stdout"]:
        print("\nTest stdout:")
        print(final_test["stdout"])

    return report


def build_parser():
    parser = argparse.ArgumentParser(
        description="Verify and audit AI agent code changes."
    )
    parser.add_argument("project")
    parser.add_argument(
        "--test-command",
        default="python -m pytest -q",
    )
    parser.add_argument(
        "--trajectory",
        help="Path to a mini-SWE-agent trajectory JSON file.",
    )
    parser.add_argument(
        "--policy",
        help="Path to a RepoPilot YAML policy.",
    )

    return parser


def main():
    arguments = build_parser().parse_args()

    verify(
        arguments.project,
        arguments.test_command,
        arguments.trajectory,
        arguments.policy,
    )


if __name__ == "__main__":
    main()
