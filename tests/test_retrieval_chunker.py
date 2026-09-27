from repopilot.retrieval.chunker import (
    chunk_python_file,
    chunk_python_source,
)


def test_chunks_top_level_function_with_metadata():
    source = '''from inventory.errors import InsufficientStockError


def reserve_inventory(repository, items):
    """Reserve requested inventory."""
    return repository.reserve(items)
'''

    chunks = chunk_python_source(
        source,
        "inventory/service.py",
    )

    assert len(chunks) == 1

    chunk = chunks[0]

    assert chunk.chunk_id == (
        "inventory/service.py::reserve_inventory"
    )
    assert chunk.symbol == "reserve_inventory"
    assert chunk.kind == "function"
    assert chunk.start_line == 4
    assert chunk.end_line == 6
    assert chunk.docstring == "Reserve requested inventory."
    assert chunk.imports == (
        "inventory.errors.InsufficientStockError",
    )
    assert "def reserve_inventory" in chunk.content
    assert len(chunk.sha256) == 64


def test_chunks_class_and_includes_decorator():
    source = '''def register(value):
    return value


@register
class InventoryService:
    """Inventory operations."""

    def reserve(self):
        return True
'''

    chunks = chunk_python_source(source, "service.py")

    assert [chunk.symbol for chunk in chunks] == [
        "register",
        "InventoryService",
    ]

    class_chunk = chunks[1]

    assert class_chunk.kind == "class"
    assert class_chunk.start_line == 5
    assert class_chunk.end_line == 10
    assert class_chunk.content.startswith("@register")


def test_creates_module_chunk_without_symbols():
    source = '''DEFAULT_LIMIT = 10
FEATURE_ENABLED = True
'''

    chunks = chunk_python_source(source, "settings.py")

    assert len(chunks) == 1
    assert chunks[0].symbol == "<module>"
    assert chunks[0].kind == "module"
    assert chunks[0].content == source


def test_invalid_python_falls_back_to_module_chunk():
    source = "def broken(:\n    pass\n"

    chunks = chunk_python_source(source, "broken.py")

    assert len(chunks) == 1
    assert chunks[0].kind == "module"
    assert chunks[0].content == source


def test_chunks_file_using_project_relative_path(tmp_path):
    project = tmp_path / "project"
    package = project / "inventory"
    package.mkdir(parents=True)

    source_file = package / "service.py"
    source_file.write_text(
        "def reserve():\n    return True\n",
        encoding="utf-8",
    )

    chunks = chunk_python_file(
        source_file,
        project_root=project,
    )

    assert len(chunks) == 1
    assert chunks[0].path == "inventory/service.py"
    assert chunks[0].chunk_id == (
        "inventory/service.py::reserve"
    )
