#!/usr/bin/env python3

import argparse
import json

from .audit import verify
from .retrieval import LexicalRetriever, index_repository
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

    return parser


def main():
    arguments = build_parser().parse_args()

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
