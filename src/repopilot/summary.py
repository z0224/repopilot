import json
from collections import Counter
from html import escape
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


def render_experiment_summary_html(payload):
    overall = payload["overall"]
    labels = {
        "baseline": "Baseline",
        "safe": "Safe",
        "rag": "RAG",
        "rag_safe": "RAG + Safe",
    }
    group_cards = []
    group_rows = []

    for group in GROUP_ORDER:
        metrics = payload["groups"].get(group)

        if metrics is None:
            continue

        acceptance = metrics["policy_acceptance_rate"]
        group_cards.append(
            "".join([
                '<article class="group-card">',
                f"<h3>{escape(labels[group])}</h3>",
                '<div class="group-value">',
                _percentage(acceptance),
                "</div>",
                '<div class="muted">policy acceptance</div>',
                '<div class="bar" aria-label="Policy acceptance">',
                (
                    '<span style="width:'
                    f"{acceptance * 100:.1f}%"
                    '"></span>'
                ),
                "</div>",
                '<div class="group-meta">',
                (
                    f"{metrics['total_api_calls']} API calls · "
                    f"${metrics['total_cost']:.5f}"
                ),
                "</div>",
                "</article>",
            ])
        )
        group_rows.append(
            "<tr>"
            f"<th>{escape(labels[group])}</th>"
            f"<td>{metrics['run_count']}</td>"
            f"<td>{_percentage(metrics['repair_success_rate'])}</td>"
            f"<td>{_percentage(acceptance)}</td>"
            f"<td>{_percentage(metrics['unsafe_overwrite_rate'])}</td>"
            f"<td>{_percentage(metrics['temporary_file_rate'])}</td>"
            f"<td>{_percentage(metrics['test_modification_rate'])}</td>"
            f"<td>{metrics['total_api_calls']}</td>"
            f"<td>${metrics['total_cost']:.5f}</td>"
            "</tr>"
        )

    task_ids = sorted({
        run["task_id"]
        for run in payload["runs"]
        if run["task_id"] is not None
    })
    lookup = {
        (run["task_id"], run["group"]): run
        for run in payload["runs"]
    }
    task_rows = []

    for task_id in task_ids:
        cells = []

        for group in GROUP_ORDER:
            run = lookup.get((task_id, group))

            if run is None:
                cells.append(
                    '<td><span class="badge missing">—</span></td>'
                )
            elif run["accepted"]:
                cells.append(
                    '<td><span class="badge accepted">Accepted</span></td>'
                )
            else:
                status = escape(
                    run["status"].replace("_", " ").title()
                )
                cells.append(
                    '<td><span class="badge rejected">'
                    f"{status}</span></td>"
                )

        task_rows.append(
            f"<tr><th>{escape(task_id)}</th>"
            + "".join(cells)
            + "</tr>"
        )

    reason_counts = Counter(
        reason
        for run in payload["runs"]
        for reason in run["rejection_reasons"]
    )

    if reason_counts:
        reason_items = "".join(
            '<li><span>'
            + escape(reason)
            + f"</span><strong>{count}</strong></li>"
            for reason, count in reason_counts.most_common()
        )
    else:
        reason_items = "<li><span>None</span><strong>0</strong></li>"

    styles = """
    :root {
      color-scheme: light;
      --ink: #172033;
      --muted: #687287;
      --line: #dfe4ec;
      --panel: #ffffff;
      --canvas: #f5f7fb;
      --brand: #3157d5;
      --brand-soft: #e9edff;
      --good: #137a52;
      --good-soft: #e4f6ee;
      --bad: #b63c4a;
      --bad-soft: #fdecef;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--canvas);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system,
        BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.55;
    }
    main { width: min(1180px, calc(100% - 32px)); margin: 0 auto; }
    header {
      padding: 72px 0 54px;
      background: linear-gradient(135deg, #17275d, #3157d5 64%, #6684eb);
      color: #fff;
    }
    header .inner { width: min(1180px, calc(100% - 32px)); margin: auto; }
    .eyebrow { letter-spacing: .14em; text-transform: uppercase; opacity: .72; font-size: 12px; }
    h1 { margin: 10px 0 12px; font-size: clamp(36px, 6vw, 64px); line-height: 1.05; }
    header p { max-width: 720px; margin: 0; font-size: 18px; opacity: .88; }
    section { margin: 32px 0; }
    h2 { margin: 0 0 16px; font-size: 25px; }
    h3 { margin: 0; font-size: 16px; }
    .kpis, .group-grid { display: grid; gap: 16px; }
    .kpis { grid-template-columns: repeat(4, 1fr); margin-top: -28px; }
    .group-grid { grid-template-columns: repeat(4, 1fr); }
    .card, .group-card, .table-panel, .reason-panel, .scope {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      box-shadow: 0 8px 24px rgba(31, 42, 68, .06);
    }
    .card { padding: 20px; }
    .card .value { font-size: 30px; font-weight: 750; margin-top: 4px; }
    .muted { color: var(--muted); font-size: 13px; }
    .group-card { padding: 20px; }
    .group-value { font-size: 32px; font-weight: 750; margin-top: 18px; }
    .group-meta { color: var(--muted); font-size: 13px; margin-top: 14px; }
    .bar { height: 8px; margin-top: 12px; border-radius: 8px; background: #e9edf4; overflow: hidden; }
    .bar span { display: block; height: 100%; border-radius: inherit; background: var(--brand); }
    .table-panel { overflow: hidden; }
    .table-scroll { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; min-width: 780px; }
    th, td { padding: 14px 16px; border-bottom: 1px solid var(--line); text-align: right; white-space: nowrap; }
    th:first-child, td:first-child { text-align: left; }
    thead th { background: #f0f3f9; color: #4c576d; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; }
    tbody tr:last-child th, tbody tr:last-child td { border-bottom: 0; }
    .badge { display: inline-block; min-width: 78px; padding: 4px 9px; border-radius: 999px; text-align: center; font-size: 12px; font-weight: 700; }
    .accepted { color: var(--good); background: var(--good-soft); }
    .rejected { color: var(--bad); background: var(--bad-soft); }
    .missing { color: var(--muted); background: #eef1f5; }
    .reason-panel { padding: 8px 22px; }
    .reason-panel ul { padding: 0; margin: 0; list-style: none; }
    .reason-panel li { display: flex; justify-content: space-between; gap: 20px; padding: 15px 0; border-bottom: 1px solid var(--line); }
    .reason-panel li:last-child { border-bottom: 0; }
    .scope { padding: 22px; color: var(--muted); }
    footer { padding: 20px 0 48px; color: var(--muted); font-size: 13px; }
    @media (max-width: 860px) {
      .kpis, .group-grid { grid-template-columns: repeat(2, 1fr); }
    }
    @media (max-width: 520px) {
      header { padding-top: 48px; }
      .kpis, .group-grid { grid-template-columns: 1fr; }
    }
    """
    return "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>RepoPilot Experiment Summary</title>",
        f"<style>{styles}</style>",
        "</head>",
        "<body>",
        "<header><div class=\"inner\">",
        '<div class="eyebrow">Deterministic agent evaluation</div>',
        "<h1>RepoPilot</h1>",
        (
            "<p>Functional repair results, execution risks, policy "
            "decisions, and model cost across recorded experiment groups.</p>"
        ),
        "</div></header>",
        "<main>",
        '<section class="kpis" aria-label="Overall metrics">',
        (
            '<article class="card"><div class="muted">Runs</div>'
            f'<div class="value">{overall["run_count"]}</div></article>'
        ),
        (
            '<article class="card"><div class="muted">Repair success</div>'
            f'<div class="value">{_percentage(overall["repair_success_rate"])}</div></article>'
        ),
        (
            '<article class="card"><div class="muted">Policy acceptance</div>'
            f'<div class="value">{_percentage(overall["policy_acceptance_rate"])}</div></article>'
        ),
        (
            '<article class="card"><div class="muted">Model cost</div>'
            f'<div class="value">${overall["total_cost"]:.5f}</div></article>'
        ),
        "</section>",
        "<section><h2>Experiment groups</h2>",
        '<div class="group-grid">',
        "".join(group_cards),
        "</div></section>",
        "<section><h2>Group comparison</h2>",
        '<div class="table-panel"><div class="table-scroll"><table>',
        (
            "<thead><tr><th>Group</th><th>Runs</th><th>Repair</th>"
            "<th>Acceptance</th><th>Overwrite</th><th>Temporary</th>"
            "<th>Test changes</th><th>API calls</th><th>Cost</th></tr></thead>"
        ),
        "<tbody>",
        "".join(group_rows),
        "</tbody></table></div></div></section>",
        "<section><h2>Task acceptance matrix</h2>",
        '<div class="table-panel"><div class="table-scroll"><table>',
        (
            "<thead><tr><th>Task</th><th>Baseline</th><th>Safe</th>"
            "<th>RAG</th><th>RAG + Safe</th></tr></thead>"
        ),
        "<tbody>",
        "".join(task_rows),
        "</tbody></table></div></div></section>",
        "<section><h2>Rejection reasons</h2>",
        f'<div class="reason-panel"><ul>{reason_items}</ul></div></section>',
        "<section><h2>Scope</h2>",
        (
            '<div class="scope">These measurements describe only the '
            "recorded benchmark runs in this report. They do not establish "
            "general model performance or causal improvements.</div></section>"
        ),
        (
            "<footer>Generated by RepoPilot · "
            f"{overall['total_api_calls']} API calls recorded</footer>"
        ),
        "</main>",
        "</body>",
        "</html>",
    ])


def write_experiment_summary(
    root,
    output,
    markdown_output=None,
    html_output=None,
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

    if html_output is not None:
        html_path = Path(
            html_output
        ).expanduser().resolve()
        html_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        html_path.write_text(
            render_experiment_summary_html(payload),
            encoding="utf-8",
        )

    return output_path, payload
