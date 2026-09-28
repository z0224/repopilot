import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from repopilot.adapters.base import AgentRunResult
from repopilot.execution import (
    build_experiment_runtime,
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
def test_builds_baseline_runtime_without_rag(
    tmp_path,
):
    prepared = prepare_experiment_workspace(
        MANIFEST,
        "task-001",
        "baseline",
        tmp_path,
    )

    def unexpected_context_builder(prepared):
        raise AssertionError(
            "baseline must not build RAG context"
        )

    runtime = build_experiment_runtime(
        prepared,
        mini_executable="/missing/mini",
        context_factory=unexpected_context_builder,
    )

    assert runtime.context is None
    assert runtime.retrieved_chunks == 0
    assert (
        runtime.adapter.include_safety_requirements
        is False
    )


def test_builds_rag_safe_runtime_with_context(
    tmp_path,
):
    prepared = prepare_experiment_workspace(
        MANIFEST,
        "task-001",
        "rag_safe",
        tmp_path,
    )
    captured = {}

    def fake_context_builder(prepared):
        captured["task_id"] = prepared.task_id

        return SimpleNamespace(
            markdown="# Retrieved context",
            items=("first", "second"),
        )

    runtime = build_experiment_runtime(
        prepared,
        mini_executable="/missing/mini",
        context_factory=fake_context_builder,
    )

    assert captured["task_id"] == "task-001"
    assert runtime.context.markdown == (
        "# Retrieved context"
    )
    assert runtime.retrieved_chunks == 2
    assert (
        runtime.adapter.include_safety_requirements
        is True
    )
    assert (
        runtime.adapter.model_class
        == "litellm_response"

    )
def test_run_one_experiment_cli_dry_run(
    tmp_path,
):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "repopilot",
            "run-one-experiment",
            str(MANIFEST),
            "--task",
            "task-001",
            "--group",
            "baseline",
            "--output-root",
            str(tmp_path),
            "--mini-executable",
            "/missing/mini",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    workspace = (
        tmp_path / "baseline" / "task-001"
    )
    preview_path = (
        workspace
        / ".repopilot"
        / "run-preview.json"
    )
    prompt_path = (
        workspace
        / ".repopilot"
        / "agent.context.md"
    )

    assert result.returncode == 0
    assert "Baseline verified: True" in result.stdout
    assert "Use RAG: False" in result.stdout
    assert (
        "Use safety requirements: False"
        in result.stdout
    )
    assert preview_path.is_file()
    assert prompt_path.is_file()

    preview = json.loads(
        preview_path.read_text(
            encoding="utf-8"
        )
    )
    prompt = prompt_path.read_text(
        encoding="utf-8"
    )

    assert preview["dry_run"] is True
    assert preview["run_id"] == (
        "task-001__baseline"
    )
    assert preview["retrieved_chunks"] == 0
    assert prompt.strip() == (
        "Fix the add function so addition "
        "returns the correct result. "
        "Do not modify tests."
    )
    assert not (
        workspace
        / ".repopilot"
        / "agent.traj.json"
    ).exists()
def test_run_one_experiment_with_fake_executable(
    tmp_path,
):
    fake_agent = tmp_path / "fake-mini"
    fake_agent.write_text(
        f"""#!{sys.executable}
from pathlib import Path

path = Path("calculator.py")
source = path.read_text(encoding="utf-8")
path.write_text(
    source.replace(
        "return a - b",
        "return a + b",
        1,
    ),
    encoding="utf-8",
)
""",
        encoding="utf-8",
    )
    fake_agent.chmod(0o755)

    output_root = tmp_path / "runs"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "repopilot",
            "run-one-experiment",
            str(MANIFEST),
            "--task",
            "task-001",
            "--group",
            "baseline",
            "--output-root",
            str(output_root),
            "--mini-executable",
            str(fake_agent),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    workspace = (
        output_root / "baseline" / "task-001"
    )
    result_path = (
        workspace
        / ".repopilot"
        / "experiment-result.json"
    )

    assert result.returncode == 0
    assert "Experiment status: accepted" in (
        result.stdout
    )
    assert result_path.is_file()

    payload = json.loads(
        result_path.read_text(encoding="utf-8")
    )

    assert payload["status"] == "accepted"
    assert payload["agent"]["succeeded"] is True
    assert payload["verification"][
        "final_test"
    ]["returncode"] == 0
