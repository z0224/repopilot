import json

from repopilot_audit import (
    audit_trajectory,
    compare_files,
    is_test_file,
)
from repopilot_guard import sha256_text


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
