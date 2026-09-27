#!/usr/bin/env python3

import argparse

from .audit import verify
from .snapshot import start_baseline


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

    return parser


def main():
    arguments = build_parser().parse_args()

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
