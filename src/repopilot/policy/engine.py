"""Load and evaluate deterministic RepoPilot policies."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import yaml

from .models import (
    PolicyConfig,
    PolicyEvaluation,
    PolicyRuleResult,
)


BOOLEAN_FIELDS = {
    "require_baseline_test",
    "require_final_test_pass",
    "forbid_test_changes",
    "forbid_full_file_overwrite",
    "allow_temporary_files",
    "require_agent_submission",
    "warn_on_failed_commands",
}

LIMIT_FIELDS = {
    "max_changed_files",
    "max_added_lines",
    "max_deleted_lines",
}


def load_policy(path):
    path = Path(path).expanduser().resolve()

    if not path.is_file():
        raise FileNotFoundError(
            f"policy file not found: {path}"
        )

    document = yaml.safe_load(
        path.read_text(encoding="utf-8")
    )

    if not isinstance(document, dict):
        raise ValueError(
            "policy document must be a mapping"
        )

    values = document.get("policy")

    if not isinstance(values, dict):
        raise ValueError(
            "policy document must contain a policy mapping"
        )

    allowed = {
        field.name
        for field in fields(PolicyConfig)
    }
    unknown = set(values) - allowed

    if unknown:
        raise ValueError(
            "unknown policy fields: "
            + ", ".join(sorted(unknown))
        )

    for name in BOOLEAN_FIELDS:
        if name in values and not isinstance(
            values[name],
            bool,
        ):
            raise ValueError(
                f"{name} must be a boolean"
            )

    for name in LIMIT_FIELDS:
        value = values.get(name)

        if value is not None and (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
        ):
            raise ValueError(
                f"{name} must be null or a non-negative integer"
            )

    return PolicyConfig(**values)


def evaluate_policy(policy, facts):
    """Evaluate a policy against verification facts."""
    rules = []

    def add(
        rule,
        passed,
        severity,
        message,
        actual,
        expected,
    ):
        rules.append(
            PolicyRuleResult(
                rule=rule,
                passed=passed,
                severity=severity,
                message=message,
                actual=actual,
                expected=expected,
            )
        )

    baseline_test = facts.get("baseline_test")

    if policy.require_baseline_test:
        add(
            "require_baseline_test",
            isinstance(baseline_test, dict),
            "error",
            (
                "Baseline test result must be recorded."
            ),
            isinstance(baseline_test, dict),
            True,
        )
    else:
        add(
            "require_baseline_test",
            True,
            "info",
            "Baseline test result is optional.",
            isinstance(baseline_test, dict),
            "optional",
        )

    final_test = facts.get("final_test", {})
    final_returncode = final_test.get("returncode")

    if policy.require_final_test_pass:
        add(
            "require_final_test_pass",
            final_returncode == 0,
            "error",
            "Final test command must pass.",
            final_returncode,
            0,
        )
    else:
        add(
            "require_final_test_pass",
            True,
            "info",
            "Final test success is optional.",
            final_returncode,
            "optional",
        )

    changed_test_files = tuple(
        facts.get("changed_test_files", ())
    )

    if policy.forbid_test_changes:
        add(
            "forbid_test_changes",
            not changed_test_files,
            "error",
            "Test files must not be modified.",
            list(changed_test_files),
            [],
        )
    else:
        add(
            "forbid_test_changes",
            True,
            "info",
            "Test file changes are allowed.",
            list(changed_test_files),
            "allowed",
        )

    audit = facts.get("trajectory_audit", {})
    overwrite_operations = tuple(
        audit.get("overwrite_operations", ())
    )

    if policy.forbid_full_file_overwrite:
        add(
            "forbid_full_file_overwrite",
            not overwrite_operations,
            "error",
            "Full-file overwrite operations are forbidden.",
            len(overwrite_operations),
            0,
        )
    else:
        add(
            "forbid_full_file_overwrite",
            True,
            "info",
            "Full-file overwrite operations are allowed.",
            len(overwrite_operations),
            "allowed",
        )

    temporary_operations = tuple(
        audit.get("temporary_file_operations", ())
    )

    add(
        "allow_temporary_files",
        (
            policy.allow_temporary_files
            or not temporary_operations
        ),
        (
            "info"
            if policy.allow_temporary_files
            else "error"
        ),
        (
            "Temporary file operations follow policy."
        ),
        len(temporary_operations),
        (
            "allowed"
            if policy.allow_temporary_files
            else 0
        ),
    )

    changes = tuple(facts.get("changes", ()))
    added_lines = sum(
        change.get("added_lines", 0)
        for change in changes
    )
    deleted_lines = sum(
        change.get("deleted_lines", 0)
        for change in changes
    )

    for rule, actual, limit in (
        (
            "max_changed_files",
            len(changes),
            policy.max_changed_files,
        ),
        (
            "max_added_lines",
            added_lines,
            policy.max_added_lines,
        ),
        (
            "max_deleted_lines",
            deleted_lines,
            policy.max_deleted_lines,
        ),
    ):
        add(
            rule,
            limit is None or actual <= limit,
            "error" if limit is not None else "info",
            f"{rule} limit must not be exceeded.",
            actual,
            limit,
        )

    exit_status = audit.get("exit_status")

    if policy.require_agent_submission:
        add(
            "require_agent_submission",
            exit_status == "Submitted",
            "error",
            "Agent must finish with Submitted status.",
            exit_status,
            "Submitted",
        )
    else:
        add(
            "require_agent_submission",
            True,
            "info",
            "Agent submission status is optional.",
            exit_status,
            "optional",
        )

    failed_commands = audit.get(
        "event_status_counts",
        {},
    ).get("failed", 0)

    if policy.warn_on_failed_commands:
        add(
            "warn_on_failed_commands",
            failed_commands == 0,
            "warning",
            "Agent trajectory contains failed commands.",
            failed_commands,
            0,
        )
    else:
        add(
            "warn_on_failed_commands",
            True,
            "info",
            "Failed-command warnings are disabled.",
            failed_commands,
            "ignored",
        )

    accepted = not any(
        not rule.passed
        and rule.severity == "error"
        for rule in rules
    )

    return PolicyEvaluation(
        policy_name=policy.name,
        accepted=accepted,
        rules=tuple(rules),
    )
