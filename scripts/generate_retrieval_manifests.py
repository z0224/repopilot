#!/usr/bin/env python3

import argparse

from repopilot.benchmarks import (
    write_retrieval_manifests,
)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate English and Chinese retrieval "
            "ground-truth manifests."
        )
    )
    parser.add_argument(
        "manifest",
        help="Path to benchmark-manifest.json.",
    )
    parser.add_argument(
        "--output-directory",
        help="Optional output directory.",
    )
    arguments = parser.parse_args()

    outputs = write_retrieval_manifests(
        arguments.manifest,
        output_directory=(
            arguments.output_directory
        ),
    )

    for language, path in outputs.items():
        print(f"{language}: {path}")


if __name__ == "__main__":
    main()
