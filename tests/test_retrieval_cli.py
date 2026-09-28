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


def test_evaluate_retrieval_command_writes_report(tmp_path):
    benchmark_root = tmp_path / "benchmarks"
    project = benchmark_root / "task-001"
    project.mkdir(parents=True)

    (project / "service.py").write_text(
        '''def calculate_total(items):
    """Calculate the total price."""
    return sum(items)
''',
        encoding="utf-8",
    )

    manifest = benchmark_root / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "task-001",
                        "project": "task-001",
                        "query": "calculate total price",
                        "relevant_files": ["service.py"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    output = tmp_path / "results" / "retrieval.json"

    result = run_cli(
        "evaluate-retrieval",
        manifest,
        "--output",
        output,
    )

    assert result.returncode == 0
    assert "Retriever: lexical" in result.stdout
    assert "Tasks: 1" in result.stdout
    assert "Mean Recall@1: 1.0" in result.stdout
    assert output.is_file()

    report = json.loads(
        output.read_text(encoding="utf-8")
    )

    assert report["aggregate"]["task_count"] == 1
    assert (
        report["aggregate"]["mean_recall_at"]["1"]
        == 1.0
    )


def test_context_command_writes_context_bundle(tmp_path):
    project = create_project(tmp_path)

    result = run_cli(
        "context",
        project,
        "--query",
        "calculate total price",
        "--retriever",
        "lexical",
        "--top-k",
        "3",
        "--max-chars",
        "2000",
    )

    assert result.returncode == 0
    assert "Retriever: lexical" in result.stdout
    assert "Included chunks: 1" in result.stdout

    markdown_path = (
        project / ".repopilot" / "context.md"
    )
    metadata_path = (
        project / ".repopilot" / "context.json"
    )

    assert markdown_path.is_file()
    assert metadata_path.is_file()

    markdown = markdown_path.read_text(
        encoding="utf-8"
    )
    metadata = json.loads(
        metadata_path.read_text(encoding="utf-8")
    )

    assert "service.py::calculate_total" in markdown
    assert metadata["retriever"] == "lexical"
    assert (
        metadata["context"]["items"][0]["symbol"]
        == "calculate_total"
    )


def test_run_command_supports_dry_run(tmp_path):
    project = create_project(tmp_path)
    trajectory = (
        tmp_path / "results" / "agent.traj.json"
    )

    result = run_cli(
        "run",
        project,
        "--task",
        "Fix total calculation",
        "--retriever",
        "lexical",
        "--mini-executable",
        "/missing/mini",
        "--output",
        trajectory,
        "--dry-run",
    )

    assert result.returncode == 0
    assert "Dry run: True" in result.stdout
    assert "Retriever: lexical" in result.stdout
    assert "<prompt saved to" in result.stdout
    assert "--model-class litellm_response" in result.stdout
    assert not trajectory.exists()

    context_path = (
        trajectory.parent
        / "agent.traj.context.md"
    )

    assert context_path.is_file()

    prompt = context_path.read_text(
        encoding="utf-8"
    )

    assert "Fix total calculation" in prompt
    assert "service.py::calculate_total" in prompt
    assert "Run the existing tests" in prompt
def test_run_dry_run_can_disable_rag_and_safety(
    tmp_path,
):
    project = create_project(tmp_path)
    trajectory = tmp_path / "baseline.traj.json"

    result = run_cli(
        "run",
        project,
        "--task",
        "Fix total calculation",
        "--mini-executable",
        "/missing/mini",
        "--output",
        trajectory,
        "--no-rag",
        "--no-safety-requirements",
        "--dry-run",
    )

    assert result.returncode == 0
    assert "Retriever: disabled" in result.stdout
    assert "Included chunks: 0" in result.stdout

    prompt_path = (
        tmp_path / "baseline.traj.context.md"
    )
    prompt = prompt_path.read_text(
        encoding="utf-8"
    )

    assert prompt.strip() == "Fix total calculation"
    assert "retrieved context" not in prompt
    assert "execution requirements" not in prompt
