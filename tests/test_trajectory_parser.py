from repopilot.trajectory import (
    extract_paths,
    parse_trajectory_data,
)


def make_trajectory(
    *,
    command="python -m pytest -q",
    returncode=0,
    exception_info="",
):
    return {
        "trajectory_format": "mini-swe-agent-v2",
        "info": {
            "exit_status": "Submitted",
            "model_stats": {
                "api_calls": 2,
                "instance_cost": 0.01,
            },
            "config": {
                "model": {
                    "model_name": "example/model",
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
                        "arguments": (
                            '{"command": '
                            + repr(command).replace(
                                "'",
                                '"',
                            )
                            + "}"
                        ),
                    }
                ],
            },
            {
                "type": "function_call_output",
                "call_id": "call-1",
                "extra": {
                    "returncode": returncode,
                    "raw_output": "command output",
                    "exception_info": exception_info,
                    "timestamp": 101.0,
                },
            },
        ],
    }


def test_parses_command_and_output():
    parsed = parse_trajectory_data(
        make_trajectory()
    )

    assert parsed.exit_status == "Submitted"
    assert parsed.model == "example/model"
    assert parsed.api_calls == 2
    assert parsed.cost == 0.01
    assert len(parsed.events) == 1

    event = parsed.events[0]

    assert event.command == "python -m pytest -q"
    assert event.returncode == 0
    assert event.status == "succeeded"
    assert event.output == "command output"
    assert event.started_at == 100.0
    assert event.completed_at == 101.0


def test_classifies_failed_command():
    parsed = parse_trajectory_data(
        make_trajectory(returncode=2)
    )

    assert parsed.events[0].status == "failed"


def test_classifies_unexecuted_command():
    parsed = parse_trajectory_data(
        make_trajectory(
            returncode=-1,
            exception_info="action was not executed",
        )
    )

    assert parsed.events[0].status == "not_executed"


def test_extracts_and_classifies_paths():
    references = extract_paths(
        "perl -pi -e 's/x/y/' inventory/service.py "
        "tests/test_service.py /tmp/repro.py "
        "configs/safe_patch.yaml"
    )

    assert [
        (reference.path, reference.category)
        for reference in references
    ] == [
        ("inventory/service.py", "source"),
        ("tests/test_service.py", "test"),
        ("/tmp/repro.py", "temporary"),
        ("configs/safe_patch.yaml", "other"),
    ]
