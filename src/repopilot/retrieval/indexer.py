"""Build and cache a repository-wide Python code index."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .chunker import CodeChunk, chunk_python_file


INDEX_SCHEMA_VERSION = 1

IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    ".repopilot",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
}


@dataclass(frozen=True)
class IndexBuildResult:
    """Summary of one repository-index build."""

    index_path: Path
    files_scanned: int
    files_reused: int
    files_rebuilt: int
    files_removed: int
    chunks: tuple[CodeChunk, ...]


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def chunk_from_dict(data):
    payload = dict(data)
    payload["imports"] = tuple(payload.get("imports", []))
    return CodeChunk(**payload)


class RepositoryIndexer:
    """Create an incremental code index for one repository."""

    def __init__(self, project_path, index_path=None):
        self.project = Path(project_path).expanduser().resolve()

        if not self.project.is_dir():
            raise ValueError(
                f"Project directory does not exist: {self.project}"
            )

        if index_path is None:
            self.index_path = (
                self.project / ".repopilot" / "index.json"
            )
        else:
            self.index_path = Path(index_path).expanduser().resolve()

    def discover_python_files(self):
        files = []

        for path in self.project.rglob("*.py"):
            if not path.is_file():
                continue

            relative_path = path.relative_to(self.project)

            if any(
                part in IGNORED_DIRECTORIES
                for part in relative_path.parts
            ):
                continue

            files.append(path)

        return sorted(
            files,
            key=lambda item: item.relative_to(
                self.project
            ).as_posix(),
        )

    def load_cache(self):
        if not self.index_path.is_file():
            return {}

        try:
            data = json.loads(
                self.index_path.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            return {}

        if data.get("schema_version") != INDEX_SCHEMA_VERSION:
            return {}

        if data.get("project") != str(self.project):
            return {}

        files = data.get("files")

        if not isinstance(files, dict):
            return {}

        return files

    def build(self):
        cached_files = self.load_cache()
        indexed_files = {}
        all_chunks = []

        reused = 0
        rebuilt = 0

        discovered_files = self.discover_python_files()

        for file_path in discovered_files:
            relative_path = file_path.relative_to(
                self.project
            ).as_posix()
            file_sha256 = sha256_file(file_path)
            cached = cached_files.get(relative_path)

            if (
                isinstance(cached, dict)
                and cached.get("sha256") == file_sha256
                and isinstance(cached.get("chunks"), list)
            ):
                chunks = [
                    chunk_from_dict(chunk)
                    for chunk in cached["chunks"]
                ]
                reused += 1
            else:
                chunks = chunk_python_file(
                    file_path,
                    project_root=self.project,
                )
                rebuilt += 1

            indexed_files[relative_path] = {
                "sha256": file_sha256,
                "chunks": [
                    chunk.to_dict()
                    for chunk in chunks
                ],
            }
            all_chunks.extend(chunks)

        removed = len(
            set(cached_files) - set(indexed_files)
        )

        output = {
            "schema_version": INDEX_SCHEMA_VERSION,
            "generated_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "project": str(self.project),
            "files": indexed_files,
            "chunks": [
                chunk.to_dict()
                for chunk in all_chunks
            ],
        }

        self.index_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self.index_path.write_text(
            json.dumps(
                output,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return IndexBuildResult(
            index_path=self.index_path,
            files_scanned=len(discovered_files),
            files_reused=reused,
            files_rebuilt=rebuilt,
            files_removed=removed,
            chunks=tuple(all_chunks),
        )


def index_repository(project_path, index_path=None):
    """Build and return an incremental repository index."""
    return RepositoryIndexer(
        project_path,
        index_path=index_path,
    ).build()
