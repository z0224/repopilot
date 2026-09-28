from dataclasses import replace
from pathlib import Path

from repopilot.adapters.base import AgentRunResult
from repopilot.execution import (
    execute_prepared_experiment,
)
from repopilot.experiments import (
    prepare_experiment_workspace,
)


MANIFEST = (
    Path(__file__).parent.parent
    / "benchmarks"
    / "benchmark-manifest.json"
)


class FakeFixingAdapter:
    include_safety_requirements = False

    def __init__(self):
        self.called = False

    def run(
        self,
        project,
        task,
        context,
        output_path,
    ):
        self.called = True
        project = Path(project)
        source_path = project / "calculator.py"
        source = source_path.read_text(
            encoding="utf-8"
        )
        source_path.write_text(
            source.replace(
                "return a - b",
                "return a + b",
                1,
            ),
            encoding="utf-8",
        )

        output_path = Path(output_path)

        return AgentRunResult(
            command=("fake-agent",),
            returncode=0,
            stdout="fixed",
            stderr="",
            trajectory_path=output_path,
            context_path=output_path.with_suffix(
                ".context.md"
            ),
        )


def test_executes_and_verifies_single_experiment(
    tmp_path,
):
    prepared = prepare_experiment_workspace(
        MANIFEST,
        "task-001",
        "baseline",
        tmp_path,
    )
    adapter = FakeFixingAdapter()

    result_path, payload = (
        execute_prepared_experiment(
            prepared,
            adapter,
        )
    )

    assert adapter.called is True
    assert result_path.is_file()
    assert payload["status"] == "accepted"
    assert payload["baseline"][
        "matches_expected"
    ] is True
    assert payload["verification"][
        "final_test"
    ]["returncode"] == 0


def test_stops_when_baseline_is_unexpected(
    tmp_path,
):
    prepared = prepare_experiment_workspace(
        MANIFEST,
        "task-001",
        "baseline",
        tmp_path,
    )
    prepared = replace(
        prepared,
        expected_baseline={
            "failed": 99,
            "passed": 0,
        },
    )
    adapter = FakeFixingAdapter()

    _, payload = execute_prepared_experiment(
        prepared,
        adapter,
    )

    assert adapter.called is False
    assert payload["status"] == "baseline_mismatch"
    assert payload["agent"] is None
