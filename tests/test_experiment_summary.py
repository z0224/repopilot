import json

import pytest

from repopilot.summary import (
    render_experiment_summary_markdown,
    summarize_experiments,
    write_experiment_summary,
)


def write_run(
    root,
    name,
    *,
    group,
    status,
    overwrite=0,
    temporary=0,
    api_calls=0,
    cost=0.0,
):
    run_directory = root / name
    run_directory.mkdir()
    result = {
        "run_id": name,
        "task_id": "task-001",
        "group": group,
        "status": status,
        "verification": {
            "changed_test_files": [],
            "final_test": {"returncode": 0},
            "trajectory_audit": {
                "commands_checked": 3,
                "event_status_counts": {"failed": 1},
                "overwrite_operations": [{}] * overwrite,
                "temporary_file_operations": [{}] * temporary,
                "targeted_rewrite_operations": [{}],
            },
        },
    }
    trajectory = {
        "info": {
            "model_stats": {
                "api_calls": api_calls,
                "instance_cost": cost,
            }
        }
    }
    (run_directory / "experiment-result.json").write_text(
        json.dumps(result),
        encoding="utf-8",
    )
    (run_directory / "agent.traj.json").write_text(
        json.dumps(trajectory),
        encoding="utf-8",
    )


def test_summarizes_experiments_by_group(tmp_path):
    write_run(
        tmp_path,
        "baseline",
        group="baseline",
        status="rejected",
        temporary=1,
        api_calls=5,
        cost=0.2,
    )
    write_run(
        tmp_path,
        "safe",
        group="safe",
        status="accepted",
        api_calls=3,
        cost=0.1,
    )

    summary = summarize_experiments(tmp_path)

    assert summary["run_count"] == 2
    assert summary["overall"]["repair_success_rate"] == 1.0
    assert summary["overall"]["policy_acceptance_rate"] == 0.5
    assert summary["overall"]["temporary_file_rate"] == 0.5
    assert summary["overall"]["total_api_calls"] == 8
    assert summary["overall"]["total_cost"] == 0.3
    assert summary["groups"]["baseline"]["accepted_count"] == 0
    assert summary["groups"]["safe"]["accepted_count"] == 1


def test_writes_summary_json(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    write_run(
        runs,
        "rag-safe",
        group="rag_safe",
        status="accepted",
    )

    output_path, payload = write_experiment_summary(
        runs,
        tmp_path / "summary.json",
        tmp_path / "summary.md",
    )

    assert output_path.is_file()
    assert json.loads(output_path.read_text()) == payload
    assert (tmp_path / "summary.md").is_file()


def test_renders_group_and_task_tables(tmp_path):
    write_run(
        tmp_path,
        "safe",
        group="safe",
        status="accepted",
        api_calls=3,
        cost=0.1,
    )
    payload = summarize_experiments(tmp_path)

    markdown = render_experiment_summary_markdown(payload)

    assert "# RepoPilot Experiment Summary" in markdown
    assert "| Safe | 1 | 100.0% | 100.0%" in markdown
    assert "| task-001 | — | Accepted | — | — |" in markdown
    assert "These measurements describe only" in markdown


def test_rejects_directory_without_results(tmp_path):
    with pytest.raises(ValueError, match="No experiment results"):
        summarize_experiments(tmp_path)
