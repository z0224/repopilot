#!/usr/bin/env python3

import argparse
import json
from pathlib import Path

from .audit import verify
from .retrieval import (
    DEFAULT_MODEL,
    LexicalRetriever,
    SentenceTransformerEmbedder,
    evaluate_hybrid_manifest,
    evaluate_lexical_manifest,
    evaluate_semantic_manifest,
    index_repository,
)
from .snapshot import start_baseline


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

    return parser


def main():
    arguments = build_parser().parse_args()

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
        )


if __name__ == "__main__":
    main()
