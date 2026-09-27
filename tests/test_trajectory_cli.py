import json
import subprocess
import sys


def run_cli(*arguments):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "repopilot",
            *map(str, arguments),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_inspect_trajectory_writes_structured_events(
    tmp_path,
):
    trajectory_path = tmp_path / "run.traj.json"
    output_path = tmp_path / "run.events.json"

    trajectory_path.write_text(
        json.dumps(
            {
                "trajectory_format": (
                    "mini-swe-agent-v2"
                ),
                "info": {
                    "exit_status": "Submitted",
                    "model_stats": {
                        "api_calls": 1,
                        "instance_cost": 0.01,
                    },
                    "config": {
                        "model": {
                            "model_name": (
                                "example/model"
                            ),
                        }
                    },
                },
                "messages": [
                    {
                        "created_at": 100.0,
                        "output": [
                            {
                                "type": "function_call",
                                "name": "bash",
                                "call_id": "call-1",
                                "arguments": json.dumps({
                                    "command": (
                                        "python -m pytest -q"
                                    ),
                                }),
                            }
                        ],
                    },
                    {
                        "type": "function_call_output",
                        "call_id": "call-1",
                        "extra": {
                            "returncode": 0,
                            "raw_output": "1 passed",
                            "timestamp": 101.0,
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = run_cli(
        "inspect-trajectory",
        trajectory_path,
        "--output",
        output_path,
    )

    assert result.returncode == 0
    assert "Command events: 1" in result.stdout
    assert "succeeded: 1" in result.stdout
    assert output_path.is_file()

    report = json.loads(
        output_path.read_text(encoding="utf-8")
    )

    assert report["event_count"] == 1
    assert report["events"][0]["status"] == (
        "succeeded"
    )
    assert report["events"][0]["returncode"] == 0
    assert "output" not in report["events"][0]
    assert (
        report["events"][0]["output_preview"]
        == "1 passed"
    )
