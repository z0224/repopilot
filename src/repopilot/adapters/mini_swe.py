"""mini-SWE-agent subprocess adapter."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .base import AgentAdapter, AgentRunResult


class MiniSWEAgentAdapter(AgentAdapter):
    """Run mini-SWE-agent with RepoPilot context."""

    def __init__(
        self,
        *,
        executable="mini",
        config_paths=("mini.yaml",),
        model=None,
        yolo=True,
        exit_immediately=True,
        runner=subprocess.run,
    ):
        self.executable = str(executable)
        self.config_paths = tuple(
            str(path)
            for path in config_paths
        )
        self.model = model
        self.yolo = bool(yolo)
        self.exit_immediately = bool(
            exit_immediately
        )
        self.runner = runner

    def build_prompt(self, task, context):
        task = str(task).strip()

        if not task:
            raise ValueError("task must not be empty")

        return (
            f"{task}\n\n"
            "## RepoPilot retrieved context\n\n"
            f"{context.markdown}\n\n"
            "## RepoPilot execution requirements\n\n"
            "1. Use the retrieved context only as a starting point.\n"
            "2. Inspect the actual files before editing.\n"
            "3. Run the existing tests before making changes.\n"
            "4. Do not modify tests unless explicitly requested.\n"
            "5. Prefer the smallest targeted source-code change.\n"
            "6. Run the full test suite after editing.\n"
        )

    def build_command(self, prompt, output_path):
        command = [self.executable]

        for config_path in self.config_paths:
            command.extend([
                "--config",
                config_path,
            ])

        if self.model:
            command.extend([
                "--model",
                self.model,
            ])

        command.extend([
            "--task",
            prompt,
            "--output",
            str(output_path),
        ])

        if self.yolo:
            command.append("--yolo")

        if self.exit_immediately:
            command.append("--exit-immediately")

        return tuple(command)

    def run(
        self,
        project,
        task,
        context,
        output_path,
    ):
        project_path = Path(
            project
        ).expanduser().resolve()
        trajectory_path = Path(
            output_path
        ).expanduser().resolve()

        if not project_path.is_dir():
            raise ValueError(
                f"project directory not found: {project_path}"
            )

        trajectory_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        prompt = self.build_prompt(task, context)
        context_path = trajectory_path.parent / (
            trajectory_path.stem + ".context.md"
        )
        context_path.write_text(
            prompt,
            encoding="utf-8",
        )

        command = self.build_command(
            prompt,
            trajectory_path,
        )

        try:
            completed = self.runner(
                list(command),
                cwd=str(project_path),
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as error:
            raise RuntimeError(
                "mini-SWE-agent executable was not found: "
                f"{self.executable}"
            ) from error

        return AgentRunResult(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            trajectory_path=trajectory_path,
            context_path=context_path,
        )
