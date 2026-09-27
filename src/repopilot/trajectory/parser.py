"""Parse mini-SWE-agent trajectories into command events."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .models import (
    CommandEvent,
    ParsedTrajectory,
    PathReference,
)


PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"("
    r"(?:/|\./|\.\./)?"
    r"(?:[A-Za-z0-9_.-]+/)*"
    r"[A-Za-z0-9_.-]+"
    r"\.(?:py|json|toml|yaml|yml|md|txt|ini|cfg)"
    r")"
)


def classify_path(path):
    normalized = path.replace("\\", "/")
    parts = tuple(
        part
        for part in normalized.split("/")
        if part
    )
    name = parts[-1] if parts else normalized

    if (
        normalized.startswith("/tmp/")
        or normalized.startswith("/var/tmp/")
    ):
        return "temporary"

    if (
        "tests" in parts
        or name.startswith("test_")
        or name.endswith("_test.py")
    ):
        return "test"

    if name.endswith(".py"):
        return "source"

    return "other"


def extract_paths(command):
    """Extract likely file paths from a shell command."""
    references = []
    seen = set()

    for match in PATH_PATTERN.finditer(command):
        path = match.group(1).rstrip(".,:;)")

        if path in seen:
            continue

        seen.add(path)
        references.append(
            PathReference(
                path=path,
                category=classify_path(path),
            )
        )

    return tuple(references)


def decode_arguments(arguments):
    if isinstance(arguments, dict):
        return arguments

    if not isinstance(arguments, str):
        return {}

    try:
        decoded = json.loads(arguments)
    except json.JSONDecodeError:
        return {}

    return decoded if isinstance(decoded, dict) else {}


def collect_tool_outputs(messages):
    outputs = {}

    for message in messages:
        if not isinstance(message, dict):
            continue

        if message.get("type") != "function_call_output":
            continue

        call_id = message.get("call_id")

        if not call_id:
            continue

        extra = message.get("extra")

        if not isinstance(extra, dict):
            extra = {}

        payload = {}

        if isinstance(message.get("output"), str):
            try:
                decoded = json.loads(message["output"])

                if isinstance(decoded, dict):
                    payload = decoded
            except json.JSONDecodeError:
                payload = {
                    "output": message["output"],
                }

        outputs[call_id] = {
            "returncode": extra.get(
                "returncode",
                payload.get("returncode"),
            ),
            "output": extra.get(
                "raw_output",
                payload.get("output", ""),
            ),
            "exception_info": (
                extra.get("exception_info")
                or payload.get("exception_info")
                or None
            ),
            "completed_at": extra.get("timestamp"),
        }

    return outputs


def collect_function_calls(messages):
    calls = []
    legacy_number = 0

    for message in messages:
        if not isinstance(message, dict):
            continue

        found_function_call = False
        output = message.get("output")

        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue

                if (
                    item.get("type") != "function_call"
                    or item.get("name") != "bash"
                ):
                    continue

                arguments = decode_arguments(
                    item.get("arguments")
                )
                command = arguments.get("command")

                if not isinstance(command, str):
                    continue

                found_function_call = True
                calls.append({
                    "call_id": (
                        item.get("call_id")
                        or item.get("id")
                    ),
                    "command": command,
                    "started_at": message.get(
                        "created_at"
                    ),
                })

        if found_function_call:
            continue

        extra = message.get("extra")

        if not isinstance(extra, dict):
            continue

        actions = extra.get("actions", [])

        if isinstance(actions, dict):
            actions = [actions]

        if not isinstance(actions, list):
            continue

        for action in actions:
            if not isinstance(action, dict):
                continue

            command = action.get("command")

            if not isinstance(command, str):
                continue

            legacy_number += 1
            calls.append({
                "call_id": (
                    action.get("tool_call_id")
                    or f"legacy-{legacy_number}"
                ),
                "command": command,
                "started_at": extra.get("timestamp"),
            })

    return calls


def event_status(returncode, exception_info):
    if returncode is None:
        return "attempted"

    if (
        returncode == -1
        or (
            exception_info
            and "not executed" in exception_info.lower()
        )
    ):
        return "not_executed"

    if returncode == 0:
        return "succeeded"

    return "failed"


def parse_trajectory_data(data, source_path="<memory>"):
    """Parse an already-loaded trajectory dictionary."""
    if not isinstance(data, dict):
        raise ValueError(
            "trajectory root must be a JSON object"
        )

    messages = data.get("messages", [])

    if not isinstance(messages, list):
        raise ValueError(
            "trajectory messages must be a list"
        )

    outputs = collect_tool_outputs(messages)
    calls = collect_function_calls(messages)
    events = []

    for index, call in enumerate(calls, start=1):
        call_id = call["call_id"] or f"call-{index}"
        result = outputs.get(call_id, {})
        returncode = result.get("returncode")
        exception_info = result.get("exception_info")

        events.append(
            CommandEvent(
                index=index,
                call_id=call_id,
                command=call["command"],
                status=event_status(
                    returncode,
                    exception_info,
                ),
                returncode=returncode,
                output=str(result.get("output", "")),
                exception_info=exception_info,
                started_at=call.get("started_at"),
                completed_at=result.get(
                    "completed_at"
                ),
                paths=extract_paths(
                    call["command"]
                ),
            )
        )

    info = data.get("info")

    if not isinstance(info, dict):
        info = {}

    model_stats = info.get("model_stats")

    if not isinstance(model_stats, dict):
        model_stats = {}

    config = info.get("config")

    if not isinstance(config, dict):
        config = {}

    model_config = config.get("model")

    if not isinstance(model_config, dict):
        model_config = {}

    return ParsedTrajectory(
        source_path=str(source_path),
        trajectory_format=data.get(
            "trajectory_format"
        ),
        exit_status=info.get("exit_status"),
        model=model_config.get("model_name"),
        api_calls=model_stats.get("api_calls"),
        cost=model_stats.get("instance_cost"),
        events=tuple(events),
    )


def parse_trajectory(path):
    path = Path(path).expanduser().resolve()

    if not path.is_file():
        raise FileNotFoundError(
            f"trajectory not found: {path}"
        )

    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    return parse_trajectory_data(
        data,
        source_path=path,
    )
