"""Split Python source files into symbol-level retrieval chunks."""

from __future__ import annotations

import ast
import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class CodeChunk:
    """A searchable Python source-code chunk."""

    chunk_id: str
    path: str
    symbol: str
    kind: str
    start_line: int
    end_line: int
    docstring: str | None
    imports: tuple[str, ...]
    content: str
    sha256: str

    def to_dict(self):
        """Return a JSON-serializable representation."""
        result = asdict(self)
        result["imports"] = list(self.imports)
        return result


def sha256_text(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def normalize_path(path):
    return str(path).replace("\\", "/")


def extract_imports(tree):
    """Extract top-level imported symbols from a parsed module."""
    imports = []

    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)

        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")

            for alias in node.names:
                if module:
                    imports.append(f"{module}.{alias.name}")
                else:
                    imports.append(alias.name)

    return tuple(dict.fromkeys(imports))


def node_start_line(node):
    """Include decorators when determining a symbol's first line."""
    lines = [node.lineno]

    for decorator in getattr(node, "decorator_list", []):
        lines.append(decorator.lineno)

    return min(lines)


def build_chunk(
    *,
    path,
    symbol,
    kind,
    start_line,
    end_line,
    docstring,
    imports,
    content,
):
    return CodeChunk(
        chunk_id=f"{path}::{symbol}",
        path=path,
        symbol=symbol,
        kind=kind,
        start_line=start_line,
        end_line=end_line,
        docstring=docstring,
        imports=imports,
        content=content,
        sha256=sha256_text(content),
    )


def module_chunk(source, path, imports=()):
    """Create a fallback chunk representing the whole module."""
    lines = source.splitlines()

    return build_chunk(
        path=path,
        symbol="<module>",
        kind="module",
        start_line=1,
        end_line=max(1, len(lines)),
        docstring=None,
        imports=imports,
        content=source,
    )


def chunk_python_source(source, path):
    """Split Python source into top-level function and class chunks."""
    normalized_path = normalize_path(path)

    if not source.strip():
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [module_chunk(source, normalized_path)]

    imports = extract_imports(tree)
    source_lines = source.splitlines()
    chunks = []

    supported_nodes = (
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
    )

    for node in tree.body:
        if not isinstance(node, supported_nodes):
            continue

        start_line = node_start_line(node)
        end_line = node.end_lineno or node.lineno
        content = "\n".join(
            source_lines[start_line - 1 : end_line]
        )

        if isinstance(node, ast.AsyncFunctionDef):
            kind = "async_function"
        elif isinstance(node, ast.FunctionDef):
            kind = "function"
        else:
            kind = "class"

        chunks.append(
            build_chunk(
                path=normalized_path,
                symbol=node.name,
                kind=kind,
                start_line=start_line,
                end_line=end_line,
                docstring=ast.get_docstring(
                    node,
                    clean=False,
                ),
                imports=imports,
                content=content,
            )
        )

    if chunks:
        return chunks

    return [module_chunk(source, normalized_path, imports)]


def chunk_python_file(file_path, project_root=None):
    """Read and chunk one Python file."""
    file_path = Path(file_path).expanduser().resolve()
    source = file_path.read_text(encoding="utf-8")

    if project_root is None:
        relative_path = file_path.name
    else:
        project_root = Path(project_root).expanduser().resolve()

        try:
            relative_path = file_path.relative_to(project_root)
        except ValueError as error:
            raise ValueError(
                f"{file_path} is outside project root "
                f"{project_root}"
            ) from error

    return chunk_python_source(source, relative_path)
