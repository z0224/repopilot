import json
from collections import Counter
from pathlib import Path


GROUP_ORDER = (
    "baseline",
    "safe",
    "rag",
    "rag_safe",
)


def _rate(count, total):
    if total == 0:
        return 0.0

    return round(count / total, 6)


def _trajectory_stats(result_path):
    trajectory_path = result_path.with_name(
        "agent.traj.json"
    )

    if not trajectory_path.is_file():
        return 0, 0.0

    trajectory = json.loads(
        trajectory_path.read_text(encoding="utf-8")
    )
    model_stats = (
        trajectory.get("info", {})
        .get("model_stats", {})
    )

    return (
        int(model_stats.get("api_calls", 0) or 0),
        float(model_stats.get("instance_cost", 0.0) or 0.0),
    )


def _load_run(result_path):
    payload = json.loads(
        result_path.read_text(encoding="utf-8")
    )
    verification = payload.get("verification") or {}
    final_test = verification.get("final_test") or {}
    audit = verification.get("trajectory_audit") or {}
    status_counts = audit.get("event_status_counts") or {}
    policy = verification.get("policy") or {}
    api_calls, cost = _trajectory_stats(result_path)

    return {
        "result_path": str(result_path),
        "run_id": payload.get("run_id"),
        "task_id": payload.get("task_id"),
        "group": payload.get("group"),
        "status": payload.get("status"),
        "rejection_reasons": list(
            policy.get("rejection_reasons") or []
        ),
        "repair_succeeded": final_test.get("returncode") == 0,
        "accepted": payload.get("status") == "accepted",
        "test_files_modified": bool(
            verification.get("changed_test_files") or []
        ),
        "overwrite_operations": len(
            audit.get("overwrite_operations") or []
        ),
        "temporary_file_operations": len(
            audit.get("temporary_file_operations") or []
        ),
        "targeted_rewrite_operations": len(
            audit.get("targeted_rewrite_operations") or []
        ),
        "commands_checked": int(
            audit.get("commands_checked", 0) or 0
        ),
        "failed_commands": int(
            status_counts.get("failed", 0) or 0
        ),
        "api_calls": api_calls,
        "cost": cost,
    }


def _aggregate(runs):
    run_count = len(runs)
    repair_count = sum(
        run["repair_succeeded"] for run in runs
    )
    accepted_count = sum(run["accepted"] for run in runs)
    overwrite_run_count = sum(
        run["overwrite_operations"] > 0 for run in runs
    )
    temporary_run_count = sum(
        run["temporary_file_operations"] > 0
        for run in runs
    )
    test_modification_run_count = sum(
        run["test_files_modified"] for run in runs
    )
    total_api_calls = sum(run["api_calls"] for run in runs)
    total_cost = sum(run["cost"] for run in runs)

    return {
        "run_count": run_count,
        "repair_success_count": repair_count,
        "repair_success_rate": _rate(repair_count, run_count),
        "accepted_count": accepted_count,
        "policy_acceptance_rate": _rate(
            accepted_count,
            run_count,
        ),
        "overwrite_run_count": overwrite_run_count,
        "unsafe_overwrite_rate": _rate(
            overwrite_run_count,
            run_count,
        ),
        "temporary_file_run_count": temporary_run_count,
        "temporary_file_rate": _rate(
            temporary_run_count,
            run_count,
        ),
        "test_modification_run_count": (
            test_modification_run_count
        ),
        "test_modification_rate": _rate(
            test_modification_run_count,
            run_count,
        ),
        "total_api_calls": total_api_calls,
        "mean_api_calls": (
            round(total_api_calls / run_count, 6)
            if run_count
            else 0.0
        ),
        "total_cost": round(total_cost, 8),
        "mean_cost": (
            round(total_cost / run_count, 8)
            if run_count
            else 0.0
        ),
    }


def summarize_experiments(root):
    root_path = Path(root).expanduser().resolve()

    if not root_path.is_dir():
        raise ValueError(
            f"Experiment directory not found: {root_path}"
        )

    result_paths = sorted(
        root_path.rglob("experiment-result.json")
    )

    if not result_paths:
        raise ValueError(
            f"No experiment results found in: {root_path}"
        )

    runs = [_load_run(path) for path in result_paths]

    for run, path in zip(runs, result_paths):
        run["result_path"] = str(
            path.relative_to(root_path)
        )
    groups = {}

    for group in GROUP_ORDER:
        group_runs = [
            run for run in runs if run["group"] == group
        ]

        if group_runs:
            groups[group] = _aggregate(group_runs)

    return {
        "schema_version": 1,
        "source_root": str(root_path),
        "run_count": len(runs),
        "groups": groups,
        "overall": _aggregate(runs),
        "runs": runs,
    }


def _percentage(value):
    return f"{value * 100:.1f}%"


def render_experiment_summary_markdown(payload):
    overall = payload["overall"]
    lines = [
        "# RepoPilot Experiment Summary",
        "",
        "## Overall",
        "",
        f"- Runs: {overall['run_count']}",
        (
            "- Repair success rate: "
            + _percentage(
                overall["repair_success_rate"]
            )
        ),
        (
            "- Policy acceptance rate: "
            + _percentage(
                overall["policy_acceptance_rate"]
            )
        ),
        f"- Total API calls: {overall['total_api_calls']}",
        f"- Total model cost: ${overall['total_cost']:.5f}",
        "",
        "## Group Comparison",
        "",
        (
            "| Group | Runs | Repair | Acceptance | "
            "Unsafe overwrite | Temporary files | "
            "Test modification | API calls | Cost |"
        ),
        (
            "|---|---:|---:|---:|---:|---:|---:|"
            "---:|---:|"
        ),
    ]
    labels = {
        "baseline": "Baseline",
        "safe": "Safe",
        "rag": "RAG",
        "rag_safe": "RAG + Safe",
    }

    for group in GROUP_ORDER:
        metrics = payload["groups"].get(group)

        if metrics is None:
            continue

        lines.append(
            "| "
            + " | ".join([
                labels[group],
                str(metrics["run_count"]),
                _percentage(
                    metrics["repair_success_rate"]
                ),
                _percentage(
                    metrics["policy_acceptance_rate"]
                ),
                _percentage(
                    metrics["unsafe_overwrite_rate"]
                ),
                _percentage(
                    metrics["temporary_file_rate"]
                ),
                _percentage(
                    metrics["test_modification_rate"]
                ),
                str(metrics["total_api_calls"]),
                f"${metrics['total_cost']:.5f}",
            ])
            + " |"
        )

    lines.extend([
        "",
        "## Task Acceptance Matrix",
        "",
        "| Task | Baseline | Safe | RAG | RAG + Safe |",
        "|---|---|---|---|---|",
    ])
    task_ids = sorted({
        run["task_id"]
        for run in payload["runs"]
        if run["task_id"] is not None
    })
    lookup = {
        (run["task_id"], run["group"]): run
        for run in payload["runs"]
    }

    for task_id in task_ids:
        cells = []

        for group in GROUP_ORDER:
            run = lookup.get((task_id, group))

            if run is None:
                cells.append("—")
            elif run["accepted"]:
                cells.append("Accepted")
            else:
                cells.append(run["status"].replace("_", " ").title())

        lines.append(
            f"| {task_id} | "
            + " | ".join(cells)
            + " |"
        )

    reason_counts = Counter(
        reason
        for run in payload["runs"]
        for reason in run["rejection_reasons"]
    )
    lines.extend([
        "",
        "## Rejection Reasons",
        "",
    ])

    if reason_counts:
        for reason, count in reason_counts.most_common():
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- None")

    lines.extend([
        "",
        "## Scope",
        "",
        (
            "These measurements describe only the recorded "
            "benchmark runs in this summary. They do not establish "
            "general model performance or causal improvements."
        ),
        "",
    ])

    return "\n".join(lines)


def write_experiment_summary(
    root,
    output,
    markdown_output=None,
):
    payload = summarize_experiments(root)
    output_path = Path(output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if markdown_output is not None:
        markdown_path = Path(
            markdown_output
        ).expanduser().resolve()
        markdown_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        markdown_path.write_text(
            render_experiment_summary_markdown(payload),
            encoding="utf-8",
        )

    return output_path, payload
