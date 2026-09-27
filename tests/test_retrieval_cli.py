import json
import subprocess
import sys


def create_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()

    (project / "service.py").write_text(
        '''def calculate_total(items):
    """Calculate the total price."""
    return sum(items)
''',
        encoding="utf-8",
    )

    return project


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


def test_index_command_builds_repository_index(tmp_path):
    project = create_project(tmp_path)

    result = run_cli("index", project)

    assert result.returncode == 0
    assert "Files scanned: 1" in result.stdout
    assert "Files rebuilt: 1" in result.stdout
    assert "Chunks: 1" in result.stdout
    assert (
        project / ".repopilot" / "index.json"
    ).is_file()


def test_retrieve_command_prints_ranked_results(tmp_path):
    project = create_project(tmp_path)

    result = run_cli(
        "retrieve",
        project,
        "--query",
        "calculate total price",
        "--top-k",
        "3",
    )

    assert result.returncode == 0
    assert "Results: 1" in result.stdout
    assert (
        "service.py::calculate_total"
        in result.stdout
    )
    assert "matched:" in result.stdout


def test_retrieve_command_supports_json(tmp_path):
    project = create_project(tmp_path)

    result = run_cli(
        "retrieve",
        project,
        "--query",
        "calculate total",
        "--json",
    )

    assert result.returncode == 0

    payload = json.loads(result.stdout)

    assert len(payload) == 1
    assert payload[0]["chunk"]["symbol"] == (
        "calculate_total"
    )
    assert payload[0]["score"] > 0


def test_retrieve_rejects_invalid_top_k(tmp_path):
    project = create_project(tmp_path)

    result = run_cli(
        "retrieve",
        project,
        "--query",
        "calculate",
        "--top-k",
        "0",
    )

    assert result.returncode == 2
    assert "must be at least 1" in result.stderr
