"""Deterministic policy configuration and results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyConfig:
    name: str = "default"
    require_baseline_test: bool = True
    require_final_test_pass: bool = True
    forbid_test_changes: bool = True
    forbid_full_file_overwrite: bool = True
    allow_temporary_files: bool = True
    require_agent_submission: bool = False
    warn_on_failed_commands: bool = True
    max_changed_files: int | None = 5
    max_added_lines: int | None = 100
    max_deleted_lines: int | None = 100


@dataclass(frozen=True)
class PolicyRuleResult:
    rule: str
    passed: bool
    severity: str
    message: str
    actual: object
    expected: object

    def to_dict(self):
        return {
            "rule": self.rule,
            "passed": self.passed,
            "severity": self.severity,
            "message": self.message,
            "actual": self.actual,
            "expected": self.expected,
        }


@dataclass(frozen=True)
class PolicyEvaluation:
    policy_name: str
    accepted: bool
    rules: tuple[PolicyRuleResult, ...]

    @property
    def rejection_reasons(self):
        return tuple(
            rule.message
            for rule in self.rules
            if not rule.passed
            and rule.severity == "error"
        )

    def to_dict(self):
        return {
            "policy_name": self.policy_name,
            "accepted": self.accepted,
            "rejection_reasons": list(
                self.rejection_reasons
            ),
            "rules": [
                rule.to_dict()
                for rule in self.rules
            ],
        }
