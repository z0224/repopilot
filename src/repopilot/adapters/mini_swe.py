"""mini-SWE-agent subprocess adapter."""

from __future__ import annotations
from ..trajectory import parse_trajectory
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
        include_safety_requirements: bool = True,
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
        self.include_safety_requirements = bool(
            include_safety_requirements
        )

    def build_prompt(
        self,
        task: str,
        context=None,
    ) -> str:
        if not task.strip():
            raise ValueError("Task must not be empty.")

        sections = [task.strip()]

        if context is not None:
            context_text = context.markdown.strip()

            if context_text:
                sections.append(
                    "## RepoPilot retrieved context\n\n"
                    f"{context_text}"
                )

        if self.include_safety_requirements:
            sections.append(
                "## RepoPilot execution requirements\n\n"
                "- Run the existing tests before editing source files.\n"
                "- Do not modify test files.\n"
                "- Avoid replacing an entire source file when a targeted edit is possible.\n"
                "- Run the tests again after the change.\n"
                "- Keep the change limited to the task.\n"
                "- Finish by issuing the required submission command."
            )

        return "\n\n".join(sections) + "\n"


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

        terminal_status = None

        if trajectory_path.is_file():
            terminal_status = parse_trajectory(
                trajectory_path
            ).exit_status

        return AgentRunResult(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            trajectory_path=trajectory_path,
            context_path=context_path,
            terminal_status=terminal_status,
        )
