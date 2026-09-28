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
