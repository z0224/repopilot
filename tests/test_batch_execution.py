import json
from pathlib import Path
from types import SimpleNamespace

from repopilot.execution import execute_experiment_batch


MANIFEST = (
    Path(__file__).parent.parent
    / "benchmarks"
    / "benchmark-manifest.json"
)


def fake_runtime(prepared, **kwargs):
    return SimpleNamespace(
        adapter=object(),
        context=None,
        retrieved_chunks=0,
    )


def test_batch_continues_after_runner_error(tmp_path):
    def executor(
        prepared,
        adapter,
        *,
        context,
        policy_path,
    ):
        if prepared.group.name == "safe":
            raise RuntimeError("simulated agent failure")

        state = prepared.workspace / ".repopilot"
        state.mkdir()
        result_path = state / "experiment-result.json"
        payload = {
            "run_id": "task-001__baseline",
            "task_id": "task-001",
            "group": "baseline",
            "status": "accepted",
            "verification": {
                "changed_test_files": [],
                "final_test": {"returncode": 0},
                "trajectory_audit": {},
            },
        }
        result_path.write_text(
            json.dumps(payload),
            encoding="utf-8",
        )
        return result_path, payload

    batch_path, payload = execute_experiment_batch(
        MANIFEST,
        tmp_path,
        group_names=("baseline", "safe"),
        task_ids=("task-001",),
        runtime_factory=fake_runtime,
        executor=executor,
    )

    assert batch_path.is_file()
    assert payload["run_count"] == 2
    assert payload["completed_count"] == 1
    assert payload["runner_error_count"] == 1
    assert payload["status_counts"] == {
        "accepted": 1,
        "runner_error": 1,
    }
    assert payload["runs"][1]["error_type"] == "RuntimeError"


def test_batch_resume_reuses_completed_result(tmp_path):
    calls = []

    def executor(
        prepared,
        adapter,
        *,
        context,
        policy_path,
    ):
        calls.append(prepared.task_id)
        state = prepared.workspace / ".repopilot"
        state.mkdir()
        result_path = state / "experiment-result.json"
        payload = {
            "run_id": "task-001__baseline",
            "task_id": "task-001",
            "group": "baseline",
            "status": "rejected",
            "verification": None,
        }
        result_path.write_text(
            json.dumps(payload),
            encoding="utf-8",
        )
        return result_path, payload

    execute_experiment_batch(
        MANIFEST,
        tmp_path,
        group_names=("baseline",),
        task_ids=("task-001",),
        runtime_factory=fake_runtime,
        executor=executor,
    )
    _, resumed = execute_experiment_batch(
        MANIFEST,
        tmp_path,
        group_names=("baseline",),
        task_ids=("task-001",),
        resume=True,
        runtime_factory=fake_runtime,
        executor=executor,
    )

    assert calls == ["task-001"]
    assert resumed["resumed_count"] == 1
    assert resumed["status_counts"] == {"rejected": 1}
