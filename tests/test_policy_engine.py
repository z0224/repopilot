import pytest

from repopilot.policy import (
    PolicyConfig,
    evaluate_policy,
    load_policy,
)


def clean_facts():
    return {
        "baseline_test": {
            "returncode": 1,
        },
        "final_test": {
            "returncode": 0,
        },
        "changes": [
            {
                "path": "service.py",
                "added_lines": 3,
                "deleted_lines": 2,
            }
        ],
        "changed_test_files": [],
        "trajectory_audit": {
            "exit_status": "Submitted",
            "overwrite_operations": [],
            "temporary_file_operations": [],
            "event_status_counts": {
                "succeeded": 3,
            },
        },
    }


def test_accepts_clean_run():
    evaluation = evaluate_policy(
        PolicyConfig(
            name="strict",
            require_agent_submission=True,
        ),
        clean_facts(),
    )

    assert evaluation.accepted is True
    assert evaluation.rejection_reasons == ()


def test_reports_multiple_rejection_reasons():
    facts = clean_facts()
    facts["final_test"] = {
        "returncode": 1,
    }
    facts["changed_test_files"] = [
        "tests/test_service.py"
    ]
    facts["trajectory_audit"][
        "overwrite_operations"
    ] = [{"command": "cat > service.py"}]

    evaluation = evaluate_policy(
        PolicyConfig(),
        facts,
    )

    assert evaluation.accepted is False
    assert len(evaluation.rejection_reasons) == 3


def test_warning_does_not_reject_run():
    facts = clean_facts()
    facts["trajectory_audit"][
        "event_status_counts"
    ] = {
        "failed": 2,
        "succeeded": 3,
    }

    evaluation = evaluate_policy(
        PolicyConfig(),
        facts,
    )

    warning = next(
        rule
        for rule in evaluation.rules
        if rule.rule == "warn_on_failed_commands"
    )

    assert warning.passed is False
    assert warning.severity == "warning"
    assert evaluation.accepted is True


def test_loads_yaml_policy(tmp_path):
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        """
policy:
  name: custom
  max_changed_files: 2
  allow_temporary_files: false
""",
        encoding="utf-8",
    )

    policy = load_policy(policy_path)

    assert policy.name == "custom"
    assert policy.max_changed_files == 2
    assert policy.allow_temporary_files is False


def test_rejects_unknown_policy_fields(tmp_path):
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        """
policy:
  unknown_rule: true
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="unknown policy fields",
    ):
        load_policy(policy_path)
