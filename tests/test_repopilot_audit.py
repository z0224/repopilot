import json

from repopilot.audit import (
    audit_trajectory,
    compare_files,
    is_test_file,
)
from repopilot.snapshot import sha256_text


def file_record(content):
    return {
        "sha256": sha256_text(content),
        "line_count": len(content.splitlines()),
        "content": content,
    }


def test_detects_modified_file():
    before = {
        "service.py": file_record(
            "def add(a, b):\n    return a - b\n"
        )
    }
    after = {
        "service.py": file_record(
            "def add(a, b):\n    return a + b\n"
        )
    }

    changes = compare_files(before, after)

    assert changes == [
        {
            "path": "service.py",
            "status": "modified",
            "added_lines": 1,
            "deleted_lines": 1,
        }
    ]


def test_detects_added_and_deleted_files():
    before = {
        "old.py": file_record("value = 1\n"),
    }
    after = {
        "new.py": file_record("value = 2\n"),
    }

    changes = compare_files(before, after)

    assert {change["status"] for change in changes} == {
        "added",
        "deleted",
    }


def test_recognizes_test_files():
    assert is_test_file("tests/test_service.py")
    assert is_test_file("test_calculator.py")
    assert is_test_file("calculator_test.py")
    assert not is_test_file("src/calculator.py")


def test_detects_overwrite_commands(tmp_path):
    trajectory = {
        "messages": [
            {
                "role": "assistant",
                "extra": {
                    "actions": [
                        {
                            "command": (
                                "cat > service.py <<'EOF'\n"
                                "value = 1\n"
                                "EOF"
                            )
                        },
                        {
                            "command": (
                                "python - <<'PY'\n"
                                "from pathlib import Path\n"
                                "Path('app.py').write_text('value = 2')\n"
                                "PY"
                            )
                        },
                    ]
                },
            }
        ]
    }

    trajectory_path = tmp_path / "trajectory.json"
    trajectory_path.write_text(
        json.dumps(trajectory),
        encoding="utf-8",
    )

    result = audit_trajectory(trajectory_path)

    assert result["commands_checked"] == 2
    assert len(result["overwrite_operations"]) == 2


def test_ignores_prompt_examples_and_read_only_cat(tmp_path):
    trajectory = {
        "messages": [
            {
                "role": "system",
                "content": "Example: cat > example.py",
            },
            {
                "role": "assistant",
                "extra": {
                    "actions": [
                        {"command": "cat -n service.py"},
                    ]
                },
            },
        ]
    }

    trajectory_path = tmp_path / "trajectory.json"
    trajectory_path.write_text(
        json.dumps(trajectory),
        encoding="utf-8",
    )

    result = audit_trajectory(trajectory_path)

    assert result["commands_checked"] == 1
    assert result["overwrite_operations"] == []

def test_ignores_read_only_cat_before_later_heredoc(
    tmp_path,
):
    trajectory = {
        "messages": [
            {
                "role": "assistant",
                "extra": {
                    "actions": [
                        {
                            "command": (
                                "cat calculator.py && "
                                "python - <<'PY'\n"
                                "print('validation')\n"
                                "PY"
                            )
                        }
                    ]
                },
            }
        ]
    }

    trajectory_path = tmp_path / "trajectory.json"
    trajectory_path.write_text(
        json.dumps(trajectory),
        encoding="utf-8",
    )

    result = audit_trajectory(trajectory_path)

    assert result["overwrite_operations"] == []
    assert result["temporary_file_operations"] == []

def test_recognizes_guarded_targeted_rewrite(tmp_path):
    trajectory = {
        "messages": [
            {
                "role": "assistant",
                "extra": {
                    "actions": [
                        {
                            "command": (
                                "python - <<'PY'\n"
                                "from pathlib import Path\n"
                                "path = Path('calculator.py')\n"
                                "text = path.read_text()\n"
                                "old = 'return a - b'\n"
                                "new = 'return a + b'\n"
                                "if text.count(old) != 1:\n"
                                "    raise SystemExit('bad count')\n"
                                "path.write_text("
                                "text.replace(old, new, 1))\n"
                                "PY"
                            )
                        }
                    ]
                },
            }
        ]
    }

    trajectory_path = tmp_path / "trajectory.json"
    trajectory_path.write_text(
        json.dumps(trajectory),
        encoding="utf-8",
    )

    result = audit_trajectory(trajectory_path)

    assert result["overwrite_operations"] == []
    assert len(result["targeted_rewrite_operations"]) == 1


def test_treats_tmp_cat_redirect_as_temporary(tmp_path):
    trajectory = {
        "messages": [
            {
                "role": "assistant",
                "extra": {
                    "actions": [
                        {
                            "command": (
                                "cat > /tmp/reproduce.py <<'PY'\n"
                                "print('reproduce')\n"
                                "PY\n"
                                "python /tmp/reproduce.py\n"
                                "rm -f /tmp/reproduce.py"
                            )
                        }
                    ]
                },
            }
        ]
    }

    trajectory_path = tmp_path / "trajectory.json"
    trajectory_path.write_text(
        json.dumps(trajectory),
        encoding="utf-8",
    )

    result = audit_trajectory(trajectory_path)

    assert result["overwrite_operations"] == []
    assert len(result["temporary_file_operations"]) == 1


def test_recognizes_targeted_sed_substitution(tmp_path):
    trajectory = {
        "messages": [
            {
                "role": "assistant",
                "extra": {
                    "actions": [
                        {
                            "command": (
                                "sed -i "
                                "'s/1 - percent)/"
                                "1 - percent \\/ 100)/' pricing.py"
                            )
                        }
                    ]
                },
            }
        ]
    }

    trajectory_path = tmp_path / "trajectory.json"
    trajectory_path.write_text(
        json.dumps(trajectory),
        encoding="utf-8",
    )

    result = audit_trajectory(trajectory_path)

    assert result["overwrite_operations"] == []
    assert len(result["targeted_rewrite_operations"]) == 1
    assert (
        result["targeted_rewrite_operations"][0]["operation_type"]
        == "targeted_sed_substitution"
    )


def test_recognizes_targeted_perl_substitution(tmp_path):
    trajectory = {
        "messages": [
            {
                "role": "assistant",
                "extra": {
                    "actions": [
                        {
                            "command": (
                                "perl -0pi -e "
                                "'s/old block/new block/s' service.py"
                            )
                        }
                    ]
                },
            }
        ]
    }

    trajectory_path = tmp_path / "trajectory.json"
    trajectory_path.write_text(
        json.dumps(trajectory),
        encoding="utf-8",
    )

    result = audit_trajectory(trajectory_path)

    assert result["overwrite_operations"] == []
    assert len(result["targeted_rewrite_operations"]) == 1
    assert (
        result["targeted_rewrite_operations"][0]["operation_type"]
        == "targeted_perl_substitution"
    )


def test_audit_links_command_returncode_and_paths(
    tmp_path,
):
    trajectory = {
        "trajectory_format": "mini-swe-agent-v2",
        "info": {
            "exit_status": "Submitted",
        },
        "messages": [
            {
                "created_at": 100.0,
                "output": [
                    {
                        "type": "function_call",
                        "name": "bash",
                        "call_id": "call-edit",
                        "arguments": json.dumps({
                            "command": (
                                "sed -i 's/old/new/' "
                                "src/service.py"
                            ),
                        }),
                    }
                ],
            },
            {
                "type": "function_call_output",
                "call_id": "call-edit",
                "extra": {
                    "returncode": 0,
                    "raw_output": "",
                    "timestamp": 101.0,
                },
            },
        ],
    }

    trajectory_path = tmp_path / "trajectory.json"
    trajectory_path.write_text(
        json.dumps(trajectory),
        encoding="utf-8",
    )

    result = audit_trajectory(trajectory_path)
    event = result["command_events"][0]

    assert result["commands_checked"] == 1
    assert result["event_status_counts"] == {
        "succeeded": 1,
    }
    assert event["status"] == "succeeded"
    assert event["returncode"] == 0
    assert event["paths"] == [
        {
            "path": "src/service.py",
            "category": "source",
        }
    ]


def test_unexecuted_write_is_not_a_real_operation(
    tmp_path,
):
    trajectory = {
        "messages": [
            {
                "created_at": 100.0,
                "output": [
                    {
                        "type": "function_call",
                        "name": "bash",
                        "call_id": "call-write",
                        "arguments": json.dumps({
                            "command": (
                                "cat > service.py <<'EOF'\n"
                                "value = 1\n"
                                "EOF"
                            ),
                        }),
                    }
                ],
            },
            {
                "type": "function_call_output",
                "call_id": "call-write",
                "extra": {
                    "returncode": -1,
                    "raw_output": "",
                    "exception_info": (
                        "action was not executed"
                    ),
                    "timestamp": 101.0,
                },
            },
        ],
    }

    trajectory_path = tmp_path / "trajectory.json"
    trajectory_path.write_text(
        json.dumps(trajectory),
        encoding="utf-8",
    )

    result = audit_trajectory(trajectory_path)

    assert result["command_events"][0]["status"] == (
        "not_executed"
    )
    assert result["overwrite_operations"] == []
def test_verify_applies_yaml_policy(
    tmp_path,
    monkeypatch,
):
    from repopilot.audit import verify

    project = tmp_path / "project"
    project.mkdir()

    state = project / ".repopilot"
    state.mkdir()

    old_source = "def run():\n    return False\n"
    new_source = "def run():\n    return True\n"

    (project / "service.py").write_text(
        new_source,
        encoding="utf-8",
    )

    baseline = {
        "files": {
            "service.py": file_record(old_source),
        },
        "baseline_test": {
            "returncode": 1,
        },
    }
    (state / "baseline.json").write_text(
        json.dumps(baseline),
        encoding="utf-8",
    )

    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        """
policy:
  name: integration-test
  require_baseline_test: true
  require_final_test_pass: true
  forbid_test_changes: true
  forbid_full_file_overwrite: true
  allow_temporary_files: true
  require_agent_submission: false
  max_changed_files: 0
  max_added_lines: 100
  max_deleted_lines: 100
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "repopilot.audit.run_test_command",
        lambda project, command: {
            "command": command,
            "returncode": 0,
            "duration_seconds": 0.01,
            "stdout": "1 passed",
            "stderr": "",
        },
    )

    report = verify(
        project,
        "python -m pytest -q",
        None,
        policy_path,
    )

    assert report["schema_version"] == 7
    assert report["accepted"] is False
    assert report["policy"]["policy_name"] == (
        "integration-test"
    )
    assert report["policy"]["rejection_reasons"] == [
        "max_changed_files limit must not be exceeded."
    ]


def test_verify_default_policy_is_backward_compatible(
    tmp_path,
    monkeypatch,
):
    from repopilot.audit import verify

    project = tmp_path / "project"
    project.mkdir()

    state = project / ".repopilot"
    state.mkdir()

    old_source = "value = 1\n"
    new_source = "value = 2\n"

    (project / "service.py").write_text(
        new_source,
        encoding="utf-8",
    )
    (state / "baseline.json").write_text(
        json.dumps({
            "files": {
                "service.py": file_record(old_source),
            },
            "baseline_test": {
                "returncode": 1,
            },
        }),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "repopilot.audit.run_test_command",
        lambda project, command: {
            "command": command,
            "returncode": 0,
            "duration_seconds": 0.01,
            "stdout": "1 passed",
            "stderr": "",
        },
    )

    report = verify(
        project,
        "python -m pytest -q",
        None,
    )

    assert report["accepted"] is True
    assert report["policy"]["policy_name"] == "default"
