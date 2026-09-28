#!/usr/bin/env python3

import argparse
import json
import shlex
from pathlib import Path
from .execution import (
    build_experiment_runtime,
    execute_experiment_batch,
    execute_prepared_experiment,
)
from .adapters import MiniSWEAgentAdapter
from .audit import verify
from .context import build_context_bundle
from .retrieval import (
    DEFAULT_MODEL,
    HybridRetriever,
    LexicalRetriever,
    SemanticRetriever,
    SentenceTransformerEmbedder,
    evaluate_hybrid_manifest,
    evaluate_lexical_manifest,
    evaluate_semantic_manifest,
    index_repository,
)
from .snapshot import start_baseline
from .summary import write_experiment_summary
from .trajectory import parse_trajectory
from .experiments import (
    EXPERIMENT_GROUPS,
    prepare_experiment_workspace,
    write_experiment_plan,
    prepare_experiment_batch,
    run_experiment_baseline,
)

def positive_int(value):
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "must be an integer"
        ) from error

    if parsed < 1:
        raise argparse.ArgumentTypeError(
            "must be at least 1"
       )

    return parsed


def build_parser():
    parser = argparse.ArgumentParser(
        prog="repopilot",
        description="Audit and verify AI coding-agent changes.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    start_parser = subparsers.add_parser(
        "start",
        help="Save the pre-agent snapshot and run baseline tests.",
    )
    start_parser.add_argument(
        "project",
        help="Path to the project being evaluated.",
    )
    start_parser.add_argument(
        "--test-command",
        default="python -m pytest -q",
    )

    verify_parser = subparsers.add_parser(
        "verify",
        help="Audit changes and run final tests.",
    )
    verify_parser.add_argument(
        "project",
        help="Path to the project being evaluated.",
    )
    verify_parser.add_argument(
        "--test-command",
        default="python -m pytest -q",
    )
    verify_parser.add_argument(
        "--trajectory",
        help="Path to the mini-SWE-agent trajectory.",
    )
    verify_parser.add_argument(
        "--policy",
        help="Path to a RepoPilot YAML policy.",
    )

    index_parser = subparsers.add_parser(
        "index",
        help="Build an incremental Python code index.",
    )
    index_parser.add_argument(
        "project",
        help="Project directory to index.",
    )
    index_parser.add_argument(
        "--index-path",
        help="Optional custom index output path.",
    )

    retrieve_parser = subparsers.add_parser(
        "retrieve",
        help="Retrieve relevant code chunks.",
    )
    retrieve_parser.add_argument(
        "project",
        help="Project directory to search.",
    )
    retrieve_parser.add_argument(
        "--query",
        required=True,
        help="Task, error message, or search query.",
    )
    retrieve_parser.add_argument(
        "--top-k",
        type=positive_int,
        default=5,
        help="Maximum number of results.",
    )
    retrieve_parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output machine-readable JSON.",
    )

    context_parser = subparsers.add_parser(
        "context",
        help="Build a bounded retrieval context bundle.",
    )
    context_parser.add_argument(
        "project",
        help="Project directory to search.",
    )
    context_parser.add_argument(
        "--query",
        required=True,
        help="Coding task or issue description.",
    )
    context_parser.add_argument(
        "--retriever",
        choices=("lexical", "semantic", "hybrid"),
        default="hybrid",
        help="Retrieval implementation to use.",
    )
    context_parser.add_argument(
        "--top-k",
        type=positive_int,
        default=5,
        help="Maximum number of context chunks.",
    )
    context_parser.add_argument(
        "--max-chars",
        type=positive_int,
        default=12000,
        help="Maximum context size in characters.",
    )
    context_parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Sentence-transformers model.",
    )
    context_parser.add_argument(
        "--output",
        help=(
            "Markdown output path. Defaults to "
            "PROJECT/.repopilot/context.md."
        ),
    )

    run_parser = subparsers.add_parser(
        "run",
        help="Retrieve context and run a coding agent.",
    )
    run_parser.add_argument(
        "project",
        help="Project directory the agent will modify.",
    )
    run_parser.add_argument(
        "--task",
        required=True,
        help="Coding task or issue description.",
    )
    run_parser.add_argument(
        "--retriever",
        choices=("lexical", "semantic", "hybrid"),
        default="hybrid",
    )
    run_parser.add_argument(
        "--top-k",
        type=positive_int,
        default=5,
    )
    run_parser.add_argument(
        "--max-chars",
        type=positive_int,
        default=12000,
    )
    run_parser.add_argument(
        "--embedding-model",
        default=DEFAULT_MODEL,
    )
    run_parser.add_argument(
        "--agent-model",
        help="Optional mini-SWE-agent model override.",
    )
    run_parser.add_argument(
        "--agent-model-class",
        default="litellm_response",
        help="mini-SWE-agent model adapter class.",
    )
    run_parser.add_argument(
        "--mini-executable",
        default="mini",
        help="Path to the mini-SWE-agent executable.",
    )
    run_parser.add_argument(
        "--agent-config",
        action="append",
        default=[],
        help=(
            "Additional mini-SWE-agent config. "
            "May be supplied multiple times."
        ),
    )
    run_parser.add_argument(
        "--output",
        help=(
            "Trajectory output path. Defaults to "
            "PROJECT/.repopilot/agent.traj.json."
        ),
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare context and command without running the agent.",
    )
    run_parser.add_argument(
        "--no-rag",
        action="store_true",
        help="Run without injecting retrieved context.",
    )
    run_parser.add_argument(
        "--no-safety-requirements",
        action="store_true",
        help="Run without RepoPilot safety requirements.",
    )

    trajectory_parser = subparsers.add_parser(
        "inspect-trajectory",
        help="Parse a trajectory into structured command events.",
    )
    trajectory_parser.add_argument(
        "trajectory",
        help="Path to a mini-SWE-agent trajectory JSON file.",
    )
    trajectory_parser.add_argument(
        "--output",
        help=(
            "Structured JSON output path. Defaults to "
            "TRAJECTORY.events.json."
        ),
    )
    trajectory_parser.add_argument(
        "--include-output",
        action="store_true",
        help="Include complete command output in the report.",
    )

    evaluation_parser = subparsers.add_parser(
        "evaluate-retrieval",
        help="Evaluate lexical retrieval from a manifest.",
    )
    evaluation_parser.add_argument(
        "manifest",
        help="Path to the retrieval ground-truth manifest.",
    )
    evaluation_parser.add_argument(
        "--output",
        help="Optional JSON report output path.",
    )
    evaluation_parser.add_argument(
        "--retriever",
        choices=("lexical", "semantic", "hybrid"),
        default="lexical",
        help="Retrieval implementation to evaluate.",
    )
    evaluation_parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Sentence-transformers model for semantic retrieval.",
    )
    experiment_parser = subparsers.add_parser(
        "prepare-experiment",
        help="Prepare an isolated buggy benchmark workspace.",
    )
    experiment_parser.add_argument(
        "manifest",
        help="Path to the benchmark manifest.",
    )
    experiment_parser.add_argument(
        "--task",
        required=True,
        help="Benchmark task id.",
    )
    experiment_parser.add_argument(
        "--group",
        required=True,
        choices=tuple(EXPERIMENT_GROUPS),
        help="Experiment group.",
    )
    experiment_parser.add_argument(
        "--output-root",
        required=True,
        help="Root directory for experiment workspaces.",
    )
    plan_parser = subparsers.add_parser(
        "plan-experiments",
        help="Write a reproducible experiment plan.",
    )
    plan_parser.add_argument(
        "manifest",
        help="Path to the benchmark manifest.",
    )
    plan_parser.add_argument(
        "--output",
        required=True,
        help="JSON experiment plan output path.",
    )
    plan_parser.add_argument(
        "--group",
        action="append",
        choices=tuple(EXPERIMENT_GROUPS),
        help=(
            "Limit the plan to a group. "
            "May be supplied multiple times."
        ),
    )
    batch_parser = subparsers.add_parser(
        "run-experiments",
        help="Prepare and run benchmark experiments.",
    )
    batch_parser.add_argument(
        "manifest",
        help="Path to the benchmark manifest.",
    )
    batch_parser.add_argument(
        "--output-root",
        required=True,
        help="Root directory for experiment outputs.",
    )
    batch_parser.add_argument(
        "--task",
        action="append",
        help=(
            "Limit execution to a task id. "
            "May be supplied multiple times."
        ),
    )
    batch_parser.add_argument(
        "--group",
        action="append",
        choices=tuple(EXPERIMENT_GROUPS),
        help=(
            "Limit execution to a group. "
            "May be supplied multiple times."
        ),
    )
    batch_parser.add_argument(
        "--limit",
        type=positive_int,
        help="Maximum number of runs.",
    )
    batch_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prepare workspaces without running agents.",
    )
    batch_parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse completed results in the output root.",
    )
    batch_parser.add_argument(
        "--mini-executable",
        default="mini",
    )
    batch_parser.add_argument(
        "--agent-model",
    )
    batch_parser.add_argument(
        "--agent-model-class",
        default="litellm_response",
    )
    batch_parser.add_argument(
        "--embedding-model",
        default=DEFAULT_MODEL,
    )
    batch_parser.add_argument(
        "--top-k",
        type=positive_int,
        default=5,
    )
    batch_parser.add_argument(
        "--max-chars",
        type=positive_int,
        default=12000,
    )
    batch_parser.add_argument(
        "--policy",
        help="Optional RepoPilot policy YAML path.",
    )
    single_parser = subparsers.add_parser(
        "run-one-experiment",
        help="Prepare and preview one experiment run.",
    )
    single_parser.add_argument(
        "manifest",
        help="Path to the benchmark manifest.",
    )
    single_parser.add_argument(
        "--task",
        required=True,
        help="Benchmark task id.",
    )
    single_parser.add_argument(
        "--group",
        required=True,
        choices=tuple(EXPERIMENT_GROUPS),
        help="Experiment group.",
    )
    single_parser.add_argument(
        "--output-root",
        required=True,
        help="Root directory for experiment output.",
    )
    single_parser.add_argument(
        "--mini-executable",
        default="mini",
    )
    single_parser.add_argument(
        "--agent-model",
    )
    single_parser.add_argument(
        "--agent-model-class",
        default="litellm_response",
        help="mini-SWE-agent model adapter class.",
    )
    single_parser.add_argument(
        "--embedding-model",
        default=DEFAULT_MODEL,
    )
    single_parser.add_argument(
        "--top-k",
        type=positive_int,
        default=5,
    )
    single_parser.add_argument(
        "--max-chars",
        type=positive_int,
        default=12000,
    )
    single_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write the prompt and command without running.",
    )
    single_parser.add_argument(
        "--policy",
        help="Optional RepoPilot policy YAML path.",
    )
    summary_parser = subparsers.add_parser(
        "summarize",
        help="Summarize structured experiment results.",
    )
    summary_parser.add_argument(
        "root",
        help="Directory containing experiment results.",
    )
    summary_parser.add_argument(
        "--output",
        required=True,
        help="Summary JSON output path.",
    )
    summary_parser.add_argument(
        "--markdown",
        help="Optional Markdown summary output path.",
    )
    summary_parser.add_argument(
        "--html",
        help="Optional self-contained HTML output path.",
    )
    return parser


def main():
    arguments = build_parser().parse_args()
    if arguments.command == "summarize":
        output_path, payload = write_experiment_summary(
            arguments.root,
            arguments.output,
            arguments.markdown,
            arguments.html,
        )
        overall = payload["overall"]
        print(f"Runs: {payload['run_count']}")
        print(
            "Repair success rate: "
            f"{overall['repair_success_rate']:.6f}"
        )
        print(
            "Policy acceptance rate: "
            f"{overall['policy_acceptance_rate']:.6f}"
        )
        print(
            f"Total API calls: {overall['total_api_calls']}"
        )
        print(f"Total cost: {overall['total_cost']:.8f}")
        print(f"Summary saved to: {output_path}")
        if arguments.markdown:
            print(
                "Markdown saved to: "
                f"{Path(arguments.markdown).expanduser().resolve()}"
            )
        if arguments.html:
            print(
                "HTML saved to: "
                f"{Path(arguments.html).expanduser().resolve()}"
            )
        return
    if arguments.command == "run-one-experiment":

        prepared = prepare_experiment_workspace(
            arguments.manifest,
            arguments.task,
            arguments.group,
            arguments.output_root,
        )
        baseline = run_experiment_baseline(
            prepared
        )

        if not baseline.matches_expected:
            print("Baseline verified: False")
            raise SystemExit(2)

        runtime = build_experiment_runtime(
            prepared,
            mini_executable=(
                arguments.mini_executable
            ),
            agent_model=arguments.agent_model,
            agent_model_class=(
                arguments.agent_model_class
            ),
            embedding_model=(
                arguments.embedding_model
            ),
            top_k=arguments.top_k,
            max_chars=arguments.max_chars,
        )
        if not arguments.dry_run:
            result_path, payload = (
                execute_prepared_experiment(
                    prepared,
                    runtime.adapter,
                    context=runtime.context,
                    policy_path=arguments.policy,
                )
            )

            print(
                f"Experiment status: "
                f"{payload['status']}"
            )
            print(
                f"Result saved to: "
                f"{result_path}"
            )

            if payload["status"] != "accepted":
                raise SystemExit(1)

            return
        state_directory = (
            prepared.workspace / ".repopilot"
        )
        state_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        trajectory_path = (
            state_directory / "agent.traj.json"
        )
        prompt_path = (
            state_directory / "agent.context.md"
        )
        preview_path = (
            state_directory / "run-preview.json"
        )

        prompt = runtime.adapter.build_prompt(
            prepared.task,
            runtime.context,
        )
        prompt_path.write_text(
            prompt,
            encoding="utf-8",
        )

        command = runtime.adapter.build_command(
            prompt,
            trajectory_path,
        )
        preview = {
            "schema_version": 1,
            "dry_run": True,
            "run_id": (
                f"{prepared.task_id}__"
                f"{prepared.group.name}"
            ),
            "group": prepared.group.name,
            "use_rag": prepared.group.use_rag,
            "use_safety_requirements": (
                prepared.group
                .use_safety_requirements
            ),
            "baseline": baseline.to_dict(),
            "retrieved_chunks": (
                runtime.retrieved_chunks
            ),
            "prompt_path": str(prompt_path),
            "trajectory_path": str(
                trajectory_path
            ),
            "command": list(command),
        }
        preview_path.write_text(
            json.dumps(
                preview,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        printable_command = list(command)
        task_position = (
            printable_command.index("--task") + 1
        )
        printable_command[task_position] = (
            f"<prompt saved to {prompt_path}>"
        )

        print("Dry run: True")
        print(
            f"Run: {preview['run_id']}"
        )
        print("Baseline verified: True")
        print(
            f"Use RAG: "
            f"{prepared.group.use_rag}"
        )
        print(
            "Use safety requirements: "
            f"{prepared.group.use_safety_requirements}"
        )
        print(
            f"Retrieved chunks: "
            f"{runtime.retrieved_chunks}"
        )
        print(f"Prompt saved to: {prompt_path}")
        print(
            "Command: "
            + shlex.join(printable_command)
        )
        print(f"Preview saved to: {preview_path}")
        return
    if arguments.command == "run-experiments":
        if arguments.dry_run:
            batch_path, payload = (
                prepare_experiment_batch(
                    arguments.manifest,
                    arguments.output_root,
                    group_names=arguments.group,
                    task_ids=arguments.task,
                    limit=arguments.limit,
                )
            )

            print("Dry run: True")
            print(
                f"Prepared runs: "
                f"{payload['run_count']}"
            )
            print(
                "Baseline verified: "
                f"{payload['baseline_verified_count']}"
            )
            print(
                "Baseline mismatches: "
                f"{payload['baseline_mismatch_count']}"
            )
            print(f"Batch saved to: {batch_path}")
            return

        batch_path, payload = execute_experiment_batch(
            arguments.manifest,
            arguments.output_root,
            group_names=arguments.group,
            task_ids=arguments.task,
            limit=arguments.limit,
            mini_executable=arguments.mini_executable,
            agent_model=arguments.agent_model,
            agent_model_class=(
                arguments.agent_model_class
            ),
            embedding_model=arguments.embedding_model,
            top_k=arguments.top_k,
            max_chars=arguments.max_chars,
            policy_path=arguments.policy,
            resume=arguments.resume,
        )
        print("Dry run: False")
        print(f"Runs attempted: {payload['run_count']}")
        print(
            f"Runs completed: "
            f"{payload['completed_count']}"
        )
        print(
            f"Runner errors: "
            f"{payload['runner_error_count']}"
        )
        print(
            "Statuses: "
            + json.dumps(
                payload["status_counts"],
                sort_keys=True,
            )
        )
        print(f"Batch saved to: {batch_path}")

        if payload["completed_count"]:
            summary_path, _ = write_experiment_summary(
                arguments.output_root,
                Path(arguments.output_root)
                / "summary.json",
                Path(arguments.output_root)
                / "summary.md",
                Path(arguments.output_root)
                / "summary.html",
            )
            print(f"Summary saved to: {summary_path}")
        return
    if arguments.command == "plan-experiments":
        output_path, payload = write_experiment_plan(
            arguments.manifest,
            arguments.output,
            arguments.group,
        )

        print(f"Tasks: {payload['task_count']}")
        print(f"Groups: {payload['group_count']}")
        print(f"Runs: {payload['run_count']}")
        print(f"Plan saved to: {output_path}")
        return
    if arguments.command == "prepare-experiment":
        prepared = prepare_experiment_workspace(
            arguments.manifest,
            arguments.task,
            arguments.group,
            arguments.output_root,
        )

        print(f"Task: {prepared.task_id}")
        print(f"Group: {prepared.group.name}")
        print(f"Use RAG: {prepared.group.use_rag}")
        print(
            "Use safety requirements: "
            f"{prepared.group.use_safety_requirements}"
        )
        print(f"Workspace: {prepared.workspace}")
        print(f"Test command: {prepared.test_command}")
        return
    if arguments.command == "inspect-trajectory":
        trajectory = parse_trajectory(
            arguments.trajectory
        )
        payload = trajectory.to_dict()

        if not arguments.include_output:
            for event in payload["events"]:
                output = event.pop("output")
                event["output_length"] = len(output)
                event["output_preview"] = output[:500]

        source_path = Path(
            arguments.trajectory
        ).expanduser().resolve()

        if arguments.output:
            output_path = Path(
                arguments.output
            ).expanduser().resolve()
        else:
            output_path = source_path.with_name(
                source_path.stem
                + ".events.json"
            )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        output_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        statuses = {}

        for event in trajectory.events:
            statuses[event.status] = (
                statuses.get(event.status, 0) + 1
            )

        print(
            f"Trajectory format: "
            f"{trajectory.trajectory_format}"
        )
        print(f"Model: {trajectory.model}")
        print(f"Exit status: {trajectory.exit_status}")
        print(f"API calls: {trajectory.api_calls}")
        print(f"Cost: {trajectory.cost}")
        print(f"Command events: {len(trajectory.events)}")

        for status in (
            "succeeded",
            "failed",
            "not_executed",
            "attempted",
        ):
            print(
                f"{status}: "
                f"{statuses.get(status, 0)}"
            )

        print(f"Events saved to: {output_path}")
        return

    if arguments.command == "run":
        project_path = Path(
            arguments.project
        ).expanduser().resolve()
        if arguments.no_rag:
            arguments.retriever = "lexical"

        index = index_repository(project_path)

        if arguments.retriever == "lexical":
            retriever = LexicalRetriever(index.chunks)
        else:
            embedder = SentenceTransformerEmbedder(
                model_name=arguments.embedding_model,
            )

            if arguments.retriever == "semantic":
                retriever = SemanticRetriever(
                    index.chunks,
                    embedder,
                )
            else:
                retriever = HybridRetriever(
                    index.chunks,
                    embedder,
                )

        results = retriever.search(
            arguments.task,
            top_k=arguments.top_k,
        )
        bundle = build_context_bundle(
            arguments.task,
            results,
            max_chars=arguments.max_chars,
            max_chunks=arguments.top_k,
        )
        if arguments.no_rag:
            bundle = None

        if arguments.output:
            trajectory_path = Path(
                arguments.output
            ).expanduser().resolve()
        else:
            trajectory_path = (
                project_path
                / ".repopilot"
                / "agent.traj.json"
            )

        config_paths = ["mini.yaml"]

        for config in arguments.agent_config:
            if config == "mini.yaml":
                continue

            config_paths.append(
                str(
                    Path(config)
                    .expanduser()
                    .resolve()
                )
            )

        adapter = MiniSWEAgentAdapter(
            executable=arguments.mini_executable,
            config_paths=config_paths,
            model=arguments.agent_model,
            model_class=arguments.agent_model_class,
            include_safety_requirements=(
                not arguments.no_safety_requirements
            ),
        )

        if arguments.dry_run:
            trajectory_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            prompt = adapter.build_prompt(
                arguments.task,
                bundle,
            )
            context_path = (
                trajectory_path.parent
                / (
                    trajectory_path.stem
                    + ".context.md"
                )
            )
            context_path.write_text(
                prompt,
                encoding="utf-8",
            )

            command = list(
                adapter.build_command(
                    prompt,
                    trajectory_path,
                )
            )
            task_position = (
                command.index("--task") + 1
            )
            command[task_position] = (
                f"<prompt saved to {context_path}>"
            )

            print("Dry run: True")
            print(
                "Retriever: "
                + (
                    "disabled"
                    if arguments.no_rag
                    else arguments.retriever
                )
            )
            print(
                f"Retrieved chunks: "
                f"{0 if arguments.no_rag else len(results)}"
            )
            print(
                f"Included chunks: "
                f"{0 if bundle is None else len(bundle.items)}"
            )
            print(
                f"Context characters: "
                f"{0 if bundle is None else bundle.char_count}"
            )
            print(f"Context saved to: {context_path}")
            print(
                "Command: "
                + shlex.join(command)
            )
            return

        result = adapter.run(
            project_path,
            arguments.task,
            bundle,
            trajectory_path,
        )

        print(f"Agent return code: {result.returncode}")
        print(
            f"Trajectory: {result.trajectory_path}"
        )
        print(
            f"Injected context: {result.context_path}"
        )

        if result.stdout:
            print(result.stdout)

        if result.stderr:
            print(result.stderr)

        if not result.succeeded:
            raise SystemExit(result.returncode)

        return

    if arguments.command == "context":
        project_path = Path(
            arguments.project
        ).expanduser().resolve()

        index = index_repository(project_path)
        model_name = None

        if arguments.retriever == "lexical":
            retriever = LexicalRetriever(index.chunks)
        else:
            embedder = SentenceTransformerEmbedder(
                model_name=arguments.model,
            )
            model_name = getattr(
                embedder,
                "model_name",
                arguments.model,
            )

            if arguments.retriever == "semantic":
                retriever = SemanticRetriever(
                    index.chunks,
                    embedder,
                )
            else:
                retriever = HybridRetriever(
                    index.chunks,
                    embedder,
                )

        results = retriever.search(
            arguments.query,
            top_k=arguments.top_k,
        )

        bundle = build_context_bundle(
            arguments.query,
            results,
            max_chars=arguments.max_chars,
            max_chunks=arguments.top_k,
        )

        if arguments.output:
            output_path = Path(
                arguments.output
            ).expanduser().resolve()
        else:
            output_path = (
                project_path
                / ".repopilot"
                / "context.md"
            )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        output_path.write_text(
            bundle.markdown,
            encoding="utf-8",
        )

        metadata_path = output_path.with_suffix(
            ".json"
        )
        metadata = {
            "schema_version": 1,
            "retriever": arguments.retriever,
            "model": model_name,
            "index": str(index.index_path),
            "context": bundle.to_dict(),
        }
        metadata_path.write_text(
            json.dumps(
                metadata,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(f"Retriever: {arguments.retriever}")
        print(f"Retrieved chunks: {len(results)}")
        print(f"Included chunks: {len(bundle.items)}")
        print(f"Context characters: {bundle.char_count}")
        print(f"Context truncated: {bundle.truncated}")
        print(f"Context saved to: {output_path}")
        print(f"Metadata saved to: {metadata_path}")
        return

    if arguments.command == "evaluate-retrieval":
        if arguments.retriever == "semantic":
            embedder = SentenceTransformerEmbedder(
                model_name=arguments.model,
            )
            report = evaluate_semantic_manifest(
                arguments.manifest,
                embedder=embedder,
            )
        elif arguments.retriever == "hybrid":
            embedder = SentenceTransformerEmbedder(
                model_name=arguments.model,
            )
            report = evaluate_hybrid_manifest(
                arguments.manifest,
                embedder=embedder,
            )
        else:
            report = evaluate_lexical_manifest(
                arguments.manifest
            )
        serialized = json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        )

        if arguments.output:
            output_path = Path(
                arguments.output
            ).expanduser().resolve()
            output_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            output_path.write_text(
                serialized,
                encoding="utf-8",
            )
        else:
            output_path = None

        aggregate = report["aggregate"]

        print(f"Retriever: {report['retriever']}")
        print(f"Tasks: {aggregate['task_count']}")

        for k, value in aggregate[
            "mean_recall_at"
        ].items():
            print(f"Mean Recall@{k}: {value}")

        print(
            "Mean Reciprocal Rank: "
            f"{aggregate['mean_reciprocal_rank']}"
        )

        if output_path:
            print(f"Report saved to: {output_path}")

        return

    if arguments.command == "index":
        result = index_repository(
            arguments.project,
            index_path=arguments.index_path,
        )

        print(f"Index saved to: {result.index_path}")
        print(f"Files scanned: {result.files_scanned}")
        print(f"Files rebuilt: {result.files_rebuilt}")
        print(f"Files reused: {result.files_reused}")
        print(f"Files removed: {result.files_removed}")
        print(f"Chunks: {len(result.chunks)}")
        return

    if arguments.command == "retrieve":
        index = index_repository(arguments.project)
        retriever = LexicalRetriever(index.chunks)
        results = retriever.search(
            arguments.query,
            top_k=arguments.top_k,
        )

        if arguments.as_json:
            print(
                json.dumps(
                    [
                        result.to_dict()
                        for result in results
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return

        print(f"Query: {arguments.query}")
        print(f"Results: {len(results)}")

        for position, result in enumerate(
            results,
            start=1,
        ):
            print(
                f"{position}. {result.chunk.chunk_id}"
            )
            print(f"   score: {result.score}")
            print(
                "   matched: "
                + ", ".join(result.matched_terms)
            )

        return

    if arguments.command == "start":
        start_baseline(
            arguments.project,
            arguments.test_command,
        )
        return

    if arguments.command == "verify":
        verify(
            arguments.project,
            arguments.test_command,
            arguments.trajectory,
            arguments.policy,
        )


if __name__ == "__main__":
    main()
