import pytest
import asyncio
import os
from pathlib import Path
from typing import AsyncGenerator, Tuple, Set, Optional, List

pytestmark = pytest.mark.asyncio

from src.parser.discovery import discover_files
from src.parser.config import IGNORED_DIRS, IGNORED_FILES, SUPPORTED_EXTENSIONS

async def run_discovery_test_helper(path: str) -> list:
    results = []
    if not Path(path).exists():
         return []
    try:
        async for abs_path, rel_path, file_type in discover_files(path):
            results.append({"abs": abs_path, "rel": rel_path, "type": file_type})
    except Exception as e:
        pytest.fail(f"discover_files raised an unexpected exception: {e}")
    results.sort(key=lambda x: x["rel"])
    return results

@pytest.fixture(scope="function")
def create_test_repo_for_discovery(tmp_path: Path) -> Path:
    repo_dir = tmp_path / "test_repo_discovery"
    repo_dir.mkdir()

    (repo_dir / "main.py").touch()
    (repo_dir / "src").mkdir()
    (repo_dir / "src" / "app.js").touch()
    (repo_dir / "src" / "component.jsx").touch()
    (repo_dir / "src" / "styles.css").touch()
    (repo_dir / "lib").mkdir()
    (repo_dir / "lib" / "core.ts").touch()
    (repo_dir / "lib" / "view.tsx").touch()
    (repo_dir / "docs").mkdir()
    (repo_dir / "docs" / "guide.md").touch()
    (repo_dir / "docs" / "api.mdx").touch()
    (repo_dir / "infra").mkdir()
    (repo_dir / "infra" / "Dockerfile").touch()
    (repo_dir / "infra" / "init.dockerfile").touch()
    (repo_dir / "native").mkdir()
    (repo_dir / "native" / "utils.c").touch()
    (repo_dir / "native" / "utils.h").touch()
    (repo_dir / "native" / "processor.cpp").touch()
    (repo_dir / "native" / "processor.hpp").touch()
    (repo_dir / "native" / "main.rs").touch()
    (repo_dir / "config.xml").touch()

    for ignored_dir_name in list(IGNORED_DIRS)[:3]:
        if ignored_dir_name == "__pycache__": continue
        git_dir = repo_dir / ignored_dir_name
        git_dir.mkdir(exist_ok=True)
        (git_dir / "some_file.txt").touch()

    pycache_dir = repo_dir / "src" / "__pycache__"
    pycache_dir.mkdir(exist_ok=True)
    (pycache_dir / "app.cpython-39.pyc").touch()

    (repo_dir / "main.pyc").touch()
    (repo_dir / "temp.log").touch()
    (repo_dir / ".DS_Store").touch()
    (repo_dir / "package-lock.json").touch()
    (repo_dir / "some_file.swp").touch()
    (repo_dir / "Makefile").touch()
    return repo_dir

async def test_discover_files_finds_supported(create_test_repo_for_discovery: Path):
    repo_path_str = str(create_test_repo_for_discovery)
    results = await run_discovery_test_helper(repo_path_str)
    expected = sorted([
        {"rel": "config.xml", "type": "xml"},
        {"rel": os.path.join("docs", "api.mdx"), "type": "markdown"},
        {"rel": os.path.join("docs", "guide.md"), "type": "markdown"},
        {"rel": os.path.join("infra", "Dockerfile"), "type": "dockerfile"},
        {"rel": os.path.join("infra", "init.dockerfile"), "type": "dockerfile"},
        {"rel": os.path.join("lib", "core.ts"), "type": "typescript"},
        {"rel": os.path.join("lib", "view.tsx"), "type": "typescript"},
        {"rel": "main.py", "type": "python"},
        {"rel": os.path.join("native", "main.rs"), "type": "rust"},
        {"rel": os.path.join("native", "processor.cpp"), "type": "cpp"},
        {"rel": os.path.join("native", "processor.hpp"), "type": "cpp"},
        {"rel": os.path.join("native", "utils.c"), "type": "c"},
        {"rel": os.path.join("native", "utils.h"), "type": "c"},
        {"rel": os.path.join("src", "app.js"), "type": "javascript"},
        {"rel": os.path.join("src", "component.jsx"), "type": "javascript"},
        {"rel": os.path.join("src", "styles.css"), "type": "css"},
    ], key=lambda x: x["rel"])
    actual_rel_type = [{"rel": r["rel"], "type": r["type"]} for r in results]
    assert len(results) == len(expected), f"Expected {len(expected)}, got {len(actual_rel_type)}"
    assert actual_rel_type == expected
    for r in results:
        expected_abs = os.path.join(repo_path_str, r["rel"])
        assert os.path.normpath(r["abs"]) == os.path.normpath(expected_abs)
        assert Path(r["abs"]).is_file()

async def test_discover_files_ignores_correctly(create_test_repo_for_discovery: Path):
    repo_path_str = str(create_test_repo_for_discovery)
    results = await run_discovery_test_helper(repo_path_str)
    ignored_or_unsupported_relative_paths = set()
    for ignored_dir_name in list(IGNORED_DIRS)[:3]:
         if ignored_dir_name != "__pycache__":
             ignored_or_unsupported_relative_paths.add(os.path.join(ignored_dir_name, "some_file.txt"))
    ignored_or_unsupported_relative_paths.add(os.path.join("src", "__pycache__", "app.cpython-39.pyc"))
    ignored_or_unsupported_relative_paths.add("main.pyc")
    ignored_or_unsupported_relative_paths.add("temp.log")
    ignored_or_unsupported_relative_paths.add(".DS_Store")
    ignored_or_unsupported_relative_paths.add("package-lock.json")
    ignored_or_unsupported_relative_paths.add("some_file.swp")
    ignored_or_unsupported_relative_paths.add("Makefile")
    found_relative_paths = {r["rel"] for r in results}
    intersection = found_relative_paths.intersection(ignored_or_unsupported_relative_paths)
    assert not intersection, f"Found unexpected files: {intersection}"

async def test_discover_files_nonexistent_path():
    non_existent_path = "/path/that/absolutely/does/not/exist/at/all"
    assert not Path(non_existent_path).exists()
    results = await run_discovery_test_helper(non_existent_path)
    assert len(results) == 0

async def test_discover_files_is_file(tmp_path: Path):
    file_path = tmp_path / "just_a_file.txt"
    file_path.touch()
    results = await run_discovery_test_helper(str(file_path))
    assert len(results) == 0
