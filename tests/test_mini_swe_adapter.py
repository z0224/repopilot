from types import SimpleNamespace

from repopilot.adapters import MiniSWEAgentAdapter
from repopilot.context import build_context_bundle
from repopilot.retrieval import chunk_python_source


def make_context():
    chunk = chunk_python_source(
        '''def calculate_total(items):
    return sum(items)
''',
        "service.py",
    )[0]

    result = SimpleNamespace(
        chunk=chunk,
        score=0.9,
    )

    return build_context_bundle(
        "Fix total calculation",
        [result],
    )


def test_builds_mini_swe_agent_command(tmp_path):
    adapter = MiniSWEAgentAdapter(
        executable="/tools/mini",
        config_paths=(
            "mini.yaml",
            "configs/safe_patch.yaml",
        ),
        model="example/model",
    )

    prompt = adapter.build_prompt(
        "Fix total calculation",
        make_context(),
    )
    command = adapter.build_command(
        prompt,
        tmp_path / "run.traj.json",
    )

    assert command[0] == "/tools/mini"
    assert command.count("--config") == 2
    assert "mini.yaml" in command
    assert "configs/safe_patch.yaml" in command
    assert "--model" in command
    assert "--yolo" in command
    assert "--exit-immediately" in command
    assert "service.py::calculate_total" in prompt


def test_run_saves_exact_injected_context(tmp_path):
    captured = {}

    def fake_runner(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs

        return SimpleNamespace(
            returncode=0,
            stdout="agent completed",
            stderr="",
        )

    adapter = MiniSWEAgentAdapter(
        executable="/tools/mini",
        runner=fake_runner,
    )
    trajectory = (
        tmp_path / "results" / "run.traj.json"
    )

    result = adapter.run(
        tmp_path,
        "Fix total calculation",
        make_context(),
        trajectory,
    )

    assert result.succeeded is True
    assert result.trajectory_path == trajectory
    assert result.context_path.is_file()
    assert "RepoPilot retrieved context" in (
        result.context_path.read_text(
            encoding="utf-8"
        )
    )
    assert captured["kwargs"]["cwd"] == str(
        tmp_path
    )
    assert captured["kwargs"]["check"] is False


def test_nonzero_agent_exit_is_preserved(tmp_path):
    def failing_runner(command, **kwargs):
        return SimpleNamespace(
            returncode=2,
            stdout="",
            stderr="agent failed",
        )

    adapter = MiniSWEAgentAdapter(
        runner=failing_runner,
    )

    result = adapter.run(
        tmp_path,
        "Fix total calculation",
        make_context(),
        tmp_path / "failed.traj.json",
    )

    assert result.succeeded is False
    assert result.returncode == 2
    assert result.stderr == "agent failed"
    assert result.to_dict()["succeeded"] is False


def test_can_disable_rag_and_safe_prompt():
    adapter = MiniSWEAgentAdapter(
        include_safety_requirements=False,
    )

    prompt = adapter.build_prompt(
        "Fix the incorrect total calculation.",
        None,
    )

    assert prompt.strip() == "Fix the incorrect total calculation."
    assert "retrieved context" not in prompt
    assert "execution requirements" not in prompt
