import pytest
import asyncio
import os
from pathlib import Path

# Ensure pytest-asyncio is installed and usable
pytestmark = pytest.mark.asyncio

# Import the function to test
from src.parser.discovery import discover_files
# Import config to verify against expected behavior
from src.parser.config import IGNORED_DIRS, IGNORED_FILES, SUPPORTED_EXTENSIONS

# Helper to run discovery and collect results
async def run_discovery(path: str) -> list:
    """Runs discover_files and returns a sorted list of results."""
    results = []
    # Check if path exists before calling, as discover_files handles non-dir path internally
    if not Path(path).exists():
         print(f"Warning: Test path does not exist: {path}")
         return []
    try:
        async for abs_path, rel_path, file_type in discover_files(path):
            results.append({"abs": abs_path, "rel": rel_path, "type": file_type})
    except Exception as e:
        # Catch unexpected errors during discovery itself
        pytest.fail(f"discover_files raised an unexpected exception: {e}")

    # Sort results by relative path for consistent testing order
    results.sort(key=lambda x: x["rel"])
    return results

@pytest.fixture(scope="function") # Use function scope for test isolation via tmp_path
def create_test_repo(tmp_path: Path) -> Path:
    """Creates a sample directory structure within tmp_path for testing discovery."""
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()

    # --- Supported Files (Use various extensions from config) ---
    (repo_dir / "main.py").touch()                  # .py -> python
    (repo_dir / "src").mkdir()
    (repo_dir / "src" / "app.js").touch()           # .js -> javascript
    (repo_dir / "src" / "component.jsx").touch()    # .jsx -> javascript
    (repo_dir / "src" / "styles.css").touch()       # .css -> css
    (repo_dir / "lib").mkdir()
    (repo_dir / "lib" / "core.ts").touch()          # .ts -> typescript
    (repo_dir / "lib" / "view.tsx").touch()         # .tsx -> typescript
    (repo_dir / "docs").mkdir()
    (repo_dir / "docs" / "guide.md").touch()        # .md -> markdown
    (repo_dir / "docs" / "api.mdx").touch()         # .mdx -> markdown
    (repo_dir / "infra").mkdir()
    (repo_dir / "infra" / "Dockerfile").touch()     # Dockerfile -> dockerfile (exact name)
    (repo_dir / "infra" / "init.dockerfile").touch() # .dockerfile -> dockerfile (extension)
    (repo_dir / "native").mkdir()
    (repo_dir / "native" / "utils.c").touch()       # .c -> c
    (repo_dir / "native" / "utils.h").touch()       # .h -> c
    (repo_dir / "native" / "processor.cpp").touch() # .cpp -> cpp
    (repo_dir / "native" / "processor.hpp").touch() # .hpp -> cpp
    (repo_dir / "native" / "main.rs").touch()       # .rs -> rust

    # --- Ignored Dirs (Check names from IGNORED_DIRS) ---
    for ignored_dir_name in list(IGNORED_DIRS)[:3]: # Test a few from config
        if ignored_dir_name == "__pycache__": continue # Handled separately
        git_dir = repo_dir / ignored_dir_name
        git_dir.mkdir(exist_ok=True)
        (git_dir / "some_file.txt").touch() # File inside ignored dir

    pycache_dir = repo_dir / "src" / "__pycache__" # Specific common ignored dir
    pycache_dir.mkdir()
    (pycache_dir / "app.cpython-39.pyc").touch() # Ignored file type in ignored dir

    # --- Ignored Files (Check names/patterns from IGNORED_FILES) ---
    (repo_dir / "main.pyc").touch() # Ignored file type (*.pyc)
    (repo_dir / "temp.log").touch() # Ignored file name (*.log)
    (repo_dir / ".DS_Store").touch() # Ignored exact file name
    (repo_dir / "package-lock.json").touch() # Ignored exact file name
    (repo_dir / "some_file.swp").touch() # Ignored pattern (*.swp)

    # --- Unsupported Files (by extension or lack thereof) ---
    (repo_dir / "config.xml").touch() # Unsupported extension
    (repo_dir / "Makefile").touch() # No extension, not explicitly supported by name

    return repo_dir

# --- Test Cases ---

async def test_discover_files_finds_supported(create_test_repo: Path):
    """Test that discovery finds all expected files with correct types."""
    repo_path_str = str(create_test_repo)
    results = await run_discovery(repo_path_str)

    # Define expected files based on the fixture setup
    # IMPORTANT: Keep this list in sync with the `create_test_repo` fixture
    # Order by relative path for comparison
    expected = sorted([
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

    # Extract details from actual results for comparison
    actual_rel_type = [{"rel": r["rel"], "type": r["type"]} for r in results]

    # Assertions
    assert len(results) == len(expected), f"Expected {len(expected)} files, but found {len(results)}"
    assert actual_rel_type == expected, "Mismatch in discovered relative paths or types"

    # Verify absolute paths
    for r in results:
        expected_abs = os.path.join(repo_path_str, r["rel"])
        # Normalize paths for cross-platform compatibility before comparing
        assert os.path.normpath(r["abs"]) == os.path.normpath(expected_abs), \
            f"Absolute path mismatch for {r['rel']}. Expected: {expected_abs}, Got: {r['abs']}"
        assert Path(r["abs"]).is_file(), f"Absolute path {r['abs']} is not a file"

async def test_discover_files_ignores_correctly(create_test_repo: Path):
    """Test that ignored files and directories are skipped."""
    repo_path_str = str(create_test_repo)
    results = await run_discovery(repo_path_str)

    # Define paths that should NOT be in the results based on fixture
    ignored_or_unsupported_relative_paths = set()

    # Files inside ignored dirs (add based on fixture logic)
    for ignored_dir_name in list(IGNORED_DIRS)[:3]:
         if ignored_dir_name != "__pycache__":
             ignored_or_unsupported_relative_paths.add(os.path.join(ignored_dir_name, "some_file.txt"))
    ignored_or_unsupported_relative_paths.add(os.path.join("src", "__pycache__", "app.cpython-39.pyc"))

    # Ignored file patterns/names
    ignored_or_unsupported_relative_paths.add("main.pyc")
    ignored_or_unsupported_relative_paths.add("temp.log")
    ignored_or_unsupported_relative_paths.add(".DS_Store")
    ignored_or_unsupported_relative_paths.add("package-lock.json")
    ignored_or_unsupported_relative_paths.add("some_file.swp")

    # Unsupported types
    ignored_or_unsupported_relative_paths.add("config.xml")
    ignored_or_unsupported_relative_paths.add("Makefile")

    found_relative_paths = {r["rel"] for r in results}

    # Check that none of the ignored/unsupported paths were found
    intersection = found_relative_paths.intersection(ignored_or_unsupported_relative_paths)
    assert not intersection, f"Found unexpected ignored/unsupported files: {intersection}"

async def test_discover_files_nonexistent_path():
    """Test discovery on a path that doesn't exist."""
    non_existent_path = "/path/that/absolutely/does/not/exist/at/all"
    # Explicitly check existence before calling run_discovery which wraps the call
    assert not Path(non_existent_path).exists()
    results = await run_discovery(non_existent_path)
    assert len(results) == 0, "Should not yield results for a non-existent path"

async def test_discover_files_is_file(tmp_path: Path):
    """Test discovery on a path that is a file, not a directory."""
    file_path = tmp_path / "just_a_file.txt"
    file_path.touch()
    results = await run_discovery(str(file_path))
    # discover_files logs an error and returns if path is not a directory
    assert len(results) == 0, "Should not yield results when run on a file path"
