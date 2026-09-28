"""Execute one isolated RepoPilot experiment."""

from __future__ import annotations
from dataclasses import dataclass

from .adapters import MiniSWEAgentAdapter
from .context import build_context_bundle
from .retrieval import (
    DEFAULT_MODEL,
    HybridRetriever,
    SentenceTransformerEmbedder,
    index_repository,
)
import json
from pathlib import Path

from .audit import verify
from .experiments import (
    PreparedExperiment,
    build_experiment_plan,
    prepare_experiment_workspace,
    run_experiment_baseline,
)
from .snapshot import start_baseline


def _write_result(workspace, payload):
    state_directory = (
        Path(workspace) / ".repopilot"
    )
    state_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    result_path = (
        state_directory
        / "experiment-result.json"
    )
    result_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return result_path

@dataclass(frozen=True)
class ExperimentRuntime:
    adapter: MiniSWEAgentAdapter
    context: object | None
    retrieved_chunks: int


def build_experiment_runtime(
    prepared: PreparedExperiment,
    *,
    mini_executable="mini",
    agent_model=None,
    agent_model_class="litellm_response",
    config_paths=("mini.yaml",),
    embedding_model=DEFAULT_MODEL,
    top_k=5,
    max_chars=12000,
    context_factory=None,
):
    adapter = MiniSWEAgentAdapter(
        executable=mini_executable,
        config_paths=config_paths,
        model=agent_model,
        model_class=agent_model_class,
        include_safety_requirements=(
            prepared.group.use_safety_requirements
        ),
    )

    if not prepared.group.use_rag:
        return ExperimentRuntime(
            adapter=adapter,
            context=None,
            retrieved_chunks=0,
        )

    if context_factory is not None:
        context = context_factory(prepared)
    else:
        index = index_repository(
            prepared.workspace
        )
        embedder = SentenceTransformerEmbedder(
            model_name=embedding_model,
        )
        retriever = HybridRetriever(
            index.chunks,
            embedder,
        )
        results = retriever.search(
            prepared.task,
            top_k=top_k,
        )
        context = build_context_bundle(
            prepared.task,
            results,
            max_chars=max_chars,
            max_chunks=top_k,
        )

    if context is None:
        raise ValueError(
            "RAG experiment requires a context bundle"
        )

    return ExperimentRuntime(
        adapter=adapter,
        context=context,
        retrieved_chunks=len(context.items),
    )

def execute_prepared_experiment(
    prepared: PreparedExperiment,
    adapter,
    *,
    context=None,
    policy_path=None,
):
    expected_rag = prepared.group.use_rag
    actual_rag = context is not None

    if expected_rag != actual_rag:
        raise ValueError(
            "experiment context does not match "
            f"group {prepared.group.name!r}"
        )

    actual_safety = getattr(
        adapter,
        "include_safety_requirements",
        None,
    )

    if actual_safety is None:
        raise ValueError(
            "agent adapter does not expose "
            "include_safety_requirements"
        )

    if (
        bool(actual_safety)
        != prepared.group.use_safety_requirements
    ):
        raise ValueError(
            "agent safety setting does not match "
            f"group {prepared.group.name!r}"
        )

    baseline = run_experiment_baseline(
        prepared
    )
    payload = {
        "schema_version": 1,
        "run_id": (
            f"{prepared.task_id}__"
            f"{prepared.group.name}"
        ),
        "task_id": prepared.task_id,
        "group": prepared.group.name,
        "use_rag": expected_rag,
        "use_safety_requirements": (
            prepared.group.use_safety_requirements
        ),
        "workspace": str(prepared.workspace),
        "baseline": baseline.to_dict(),
        "agent": None,
        "verification": None,
    }

    if not baseline.matches_expected:
        payload["status"] = "baseline_mismatch"
        result_path = _write_result(
            prepared.workspace,
            payload,
        )
        return result_path, payload

    start_baseline(
        prepared.workspace,
        prepared.test_command,
    )

    trajectory_path = (
        prepared.workspace
        / ".repopilot"
        / "agent.traj.json"
    )

    agent_result = adapter.run(
        prepared.workspace,
        prepared.task,
        context,
        trajectory_path,
    )
    payload["agent"] = agent_result.to_dict()

    if not agent_result.succeeded:
        payload["status"] = "agent_failed"
        result_path = _write_result(
            prepared.workspace,
            payload,
        )
        return result_path, payload

    if agent_result.trajectory_path.is_file():
        trajectory_for_audit = (
            agent_result.trajectory_path
        )
    else:
        trajectory_for_audit = None

    report = verify(
        prepared.workspace,
        prepared.test_command,
        trajectory_for_audit,
        policy_path,
    )

    payload["verification"] = report
    payload["status"] = (
        "accepted"
        if report["accepted"]
        else "rejected"
    )

    result_path = _write_result(
        prepared.workspace,
        payload,
    )
    return result_path, payload


def _select_batch_plan(
    manifest_path,
    *,
    group_names=None,
    task_ids=None,
    limit=None,
):
    plan = list(
        build_experiment_plan(
            manifest_path,
            group_names,
        )
    )

    if task_ids is not None:
        requested_tasks = tuple(task_ids)
        available_tasks = {
            item.task_id for item in plan
        }
        unknown_tasks = (
            set(requested_tasks) - available_tasks
        )

        if unknown_tasks:
            raise ValueError(
                "unknown benchmark tasks: "
                + ", ".join(sorted(unknown_tasks))
            )

        plan = [
            item
            for item in plan
            if item.task_id in requested_tasks
        ]

    if limit is not None:
        if limit < 1:
            raise ValueError(
                "experiment limit must be at least 1"
            )

        plan = plan[:limit]

    if not plan:
        raise ValueError(
            "experiment selection is empty"
        )

    return tuple(plan)


def _write_batch_state(batch_path, runs, *, resume):
    status_counts = {}

    for run in runs:
        status = run["status"]
        status_counts[status] = (
            status_counts.get(status, 0) + 1
        )

    payload = {
        "schema_version": 1,
        "dry_run": False,
        "resume": bool(resume),
        "run_count": len(runs),
        "completed_count": sum(
            bool(run.get("result_path"))
            for run in runs
        ),
        "resumed_count": sum(
            bool(run.get("resumed"))
            for run in runs
        ),
        "runner_error_count": status_counts.get(
            "runner_error",
            0,
        ),
        "status_counts": status_counts,
        "runs": runs,
    }
    batch_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return payload


def execute_experiment_batch(
    manifest_path,
    output_root,
    *,
    group_names=None,
    task_ids=None,
    limit=None,
    mini_executable="mini",
    agent_model=None,
    agent_model_class="litellm_response",
    embedding_model=DEFAULT_MODEL,
    top_k=5,
    max_chars=12000,
    policy_path=None,
    resume=False,
    runtime_factory=build_experiment_runtime,
    executor=execute_prepared_experiment,
):
    """Execute selected experiments and persist progress after each run."""
    plan = _select_batch_plan(
        manifest_path,
        group_names=group_names,
        task_ids=task_ids,
        limit=limit,
    )
    output_root = Path(
        output_root
    ).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    batch_path = output_root / "batch.json"
    runs = []

    for item in plan:
        existing_result = (
            output_root
            / item.group.name
            / item.task_id
            / ".repopilot"
            / "experiment-result.json"
        )

        if resume and existing_result.is_file():
            existing_payload = json.loads(
                existing_result.read_text(
                    encoding="utf-8"
                )
            )
            runs.append({
                "run_id": item.run_id,
                "task_id": item.task_id,
                "group": item.group.name,
                "status": existing_payload.get(
                    "status",
                    "unknown",
                ),
                "result_path": str(existing_result),
                "resumed": True,
            })
            _write_batch_state(
                batch_path,
                runs,
                resume=resume,
            )
            continue

        try:
            prepared = prepare_experiment_workspace(
                manifest_path,
                item.task_id,
                item.group.name,
                output_root,
            )
            runtime = runtime_factory(
                prepared,
                mini_executable=mini_executable,
                agent_model=agent_model,
                agent_model_class=agent_model_class,
                embedding_model=embedding_model,
                top_k=top_k,
                max_chars=max_chars,
            )
            result_path, result = executor(
                prepared,
                runtime.adapter,
                context=runtime.context,
                policy_path=policy_path,
            )
            runs.append({
                "run_id": item.run_id,
                "task_id": item.task_id,
                "group": item.group.name,
                "status": result["status"],
                "result_path": str(result_path),
                "retrieved_chunks": (
                    runtime.retrieved_chunks
                ),
                "resumed": False,
            })
        except Exception as error:
            runs.append({
                "run_id": item.run_id,
                "task_id": item.task_id,
                "group": item.group.name,
                "status": "runner_error",
                "result_path": None,
                "resumed": False,
                "error_type": type(error).__name__,
                "error": str(error),
            })

        _write_batch_state(
            batch_path,
            runs,
            resume=resume,
        )

    payload = _write_batch_state(
        batch_path,
        runs,
        resume=resume,
    )

    return batch_path, payload
