import json

from repopilot.retrieval.indexer import (
    RepositoryIndexer,
    index_repository,
)


def create_project(tmp_path):
    project = tmp_path / "project"
    tests = project / "tests"
    ignored = project / ".venv"

    tests.mkdir(parents=True)
    ignored.mkdir()

    (project / "service.py").write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    (tests / "test_service.py").write_text(
        "def test_add():\n    assert True\n",
        encoding="utf-8",
    )
    (ignored / "ignored.py").write_text(
        "def ignored():\n    return True\n",
        encoding="utf-8",
    )

    return project


def test_indexes_python_files_and_ignores_cache_directories(
    tmp_path,
):
    project = create_project(tmp_path)

    result = index_repository(project)

    assert result.files_scanned == 2
    assert result.files_rebuilt == 2
    assert result.files_reused == 0
    assert result.files_removed == 0

    chunk_paths = {
        chunk.path
        for chunk in result.chunks
    }

    assert chunk_paths == {
        "service.py",
        "tests/test_service.py",
    }
    assert result.index_path.is_file()


def test_second_build_reuses_unchanged_files(tmp_path):
    project = create_project(tmp_path)

    index_repository(project)
    result = index_repository(project)

    assert result.files_scanned == 2
    assert result.files_reused == 2
    assert result.files_rebuilt == 0


def test_rebuilds_only_changed_file(tmp_path):
    project = create_project(tmp_path)

    index_repository(project)

    (project / "service.py").write_text(
        "def add(a, b):\n    return a - b\n",
        encoding="utf-8",
    )

    result = index_repository(project)

    assert result.files_scanned == 2
    assert result.files_reused == 1
    assert result.files_rebuilt == 1


def test_removes_deleted_file_from_index(tmp_path):
    project = create_project(tmp_path)

    index_repository(project)
    (project / "tests" / "test_service.py").unlink()

    result = index_repository(project)

    assert result.files_scanned == 1
    assert result.files_removed == 1

    index_data = json.loads(
        result.index_path.read_text(encoding="utf-8")
    )

    assert set(index_data["files"]) == {"service.py"}


def test_corrupt_cache_is_rebuilt(tmp_path):
    project = create_project(tmp_path)
    indexer = RepositoryIndexer(project)

    indexer.index_path.parent.mkdir(parents=True)
    indexer.index_path.write_text(
        "{not valid json",
        encoding="utf-8",
    )

    result = indexer.build()

    assert result.files_scanned == 2
    assert result.files_rebuilt == 2
    assert result.files_reused == 0
