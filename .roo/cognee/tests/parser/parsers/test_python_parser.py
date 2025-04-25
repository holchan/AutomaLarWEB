import pytest
import asyncio
import os
import json
import hashlib
from pathlib import Path
from typing import List, TYPE_CHECKING

# Use pytest-asyncio for async tests
pytestmark = pytest.mark.asyncio

# Import the parser and entity types
try:
    from src.parser.parsers.python_parser import PythonParser
    from src.parser.entities import DataPoint, TextChunk, CodeEntity, Dependency
except ImportError as e:
    pytest.skip(f"Skipping Python parser tests: Failed to import dependencies - {e}", allow_module_level=True)


# Avoid runtime import errors if BaseParser isn't directly used
if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser

# --- Test Configuration ---
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "python"
if not TEST_DATA_DIR.is_dir():
    # If the test data directory doesn't exist, skip all tests in this file.
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

# --- Helper Function ---
# (Note: Consider moving this to tests/parser/conftest.py if used by multiple parser tests)
async def run_parser_and_save_output(
    parser: 'BaseParser',
    test_file_path: Path,
    output_dir: Path # Typically tmp_path provided by pytest fixture
) -> List['DataPoint']:
    """
    Runs the parser on a given file path, saves the payload results to a JSON
    file in output_dir, and returns the list of original DataPoint objects.
    """
    if not test_file_path.is_file():
        # Fail the test explicitly if the input file isn't found
        pytest.fail(f"Test input file not found: {test_file_path}")

    # Create a somewhat unique file ID for the test run context
    file_id_base = str(test_file_path.absolute())
    # Use a hash for a concise but relatively stable ID based on path
    file_id = f"test_file_id_{hashlib.sha1(file_id_base.encode()).hexdigest()[:10]}"

    results_objects: List[DataPoint] = []
    results_payloads: List[dict] = []

    try:
        # Execute the parser's parse method
        async for dp in parser.parse(file_path=str(test_file_path), file_id=file_id):
            results_objects.append(dp)
            # Safely get payload/dict representation
            if hasattr(dp, 'model_dump'):
                payload = dp.model_dump()
            elif hasattr(dp, 'payload'):
                payload = dp.payload
            else:
                # If neither exists, something is wrong with the DataPoint object
                payload = {"id": getattr(dp, 'id', 'unknown'), "type": "UnknownPayloadStructure"}
            results_payloads.append(payload)
    except Exception as e:
        print(f"\nERROR during parser execution for {test_file_path.name}: {e}")
        # Fail the test if the parser itself throws an unexpected error
        pytest.fail(f"Parser execution failed for {test_file_path.name}: {e}", pytrace=True)

    # Define output filename within the pytest temporary directory
    output_filename = output_dir / f"parsed_{test_file_path.stem}_output.json"
    try:
        output_dir.mkdir(parents=True, exist_ok=True) # Ensure output dir exists
        # Write the collected payloads to the JSON file
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(results_payloads, f, indent=2, ensure_ascii=False, sort_keys=True)
        # Print message to console (visible with pytest -s) indicating output location
        print(f"\n[Test Output] Saved parser results for '{test_file_path.name}' to: {output_filename}")
    except Exception as e:
        # Log an error if saving fails, but don't necessarily fail the test
        print(f"\n[Test Output] WARNING: Failed to save test output for {test_file_path.name}: {e}")

    return results_objects # Return the original DataPoint objects for assertions


# --- Parser Fixture ---
@pytest.fixture(scope="module")
def parser() -> PythonParser:
    """Provides a PythonParser instance, skipping if language not loaded."""
    try:
        # Ensure tree-sitter language is loaded/available
        from src.parser.parsers.treesitter_setup import get_language
        if get_language("python") is None:
            pytest.skip("Python tree-sitter language not loaded or available.", allow_module_level=True)
    except ImportError as e:
        pytest.skip(f"Tree-sitter setup or core library not available: {e}", allow_module_level=True)

    return PythonParser()

# --- Test Cases ---

async def test_parse_empty_file(parser: PythonParser, tmp_path: Path):
    """Test parsing an empty Python file."""
    empty_file = tmp_path / "empty.py"
    empty_file.touch()
    results = await run_parser_and_save_output(parser, empty_file, tmp_path)
    assert len(results) == 0, "Empty file should yield no DataPoints"

async def test_parse_simple_function_file(parser: PythonParser, tmp_path: Path):
    """Test parsing simple_function.py from test_data."""
    test_file = TEST_DATA_DIR / "simple_function.py"
    results = await run_parser_and_save_output(parser, test_file, tmp_path)

    # Basic checks
    assert len(results) > 0, "Expected DataPoints from non-empty file"
    payloads = [dp.payload for dp in results] # Use payloads for easier dict access in asserts

    # Check for TextChunks
    chunks = [p for p in payloads if p.get("type") == "TextChunk"]
    assert len(chunks) >= 1, "Expected at least one TextChunk"
    assert chunks[0].get("chunk_index") == 0, "First chunk index should be 0"
    assert chunks[0].get("text","").strip().startswith("# A simple function example"), "First chunk content mismatch"
    assert chunks[0].get("chunk_of", "").startswith("test_file_id_"), "Chunk parent ID missing or invalid" # Check parent link

    # Check for CodeEntity (FunctionDefinition)
    funcs = [p for p in payloads if p.get("type") == "FunctionDefinition"]
    assert len(funcs) == 1, "Expected exactly one function definition"
    func = funcs[0]
    assert func.get("name") == "process_data"
    assert func.get("start_line") == 7, "Incorrect start line for process_data"
    assert func.get("end_line") == 14, "Incorrect end line for process_data"
    assert "def process_data(file_path: str) -> bool:" in func.get("source_code_snippet", ""), "Function signature mismatch"
    assert '"""' in func.get("source_code_snippet", ""), "Docstring seems missing from snippet"
    assert func.get("defined_in_file", "").startswith("test_file_id_"), "Function parent ID missing or invalid"

    # Check for Dependency
    deps = [p for p in payloads if p.get("type") == "Dependency"]
    assert len(deps) == 2, "Expected two import dependencies"
    # Sort by line number for consistent checks
    deps.sort(key=lambda d: d.get("start_line", 0))
    dep_os = deps[0]
    dep_log = deps[1]

    assert dep_os.get("target_module") == "os"
    assert dep_os.get("start_line") == 2
    assert dep_os.get("end_line") == 2
    assert dep_os.get("source_code_snippet") == "import os"
    assert dep_os.get("used_in_file", "").startswith("test_file_id_"), "Dependency parent ID missing or invalid"

    assert dep_log.get("target_module") == "logging"
    assert dep_log.get("start_line") == 3
    assert dep_log.get("end_line") == 3
    assert dep_log.get("source_code_snippet") == "import logging"
    assert dep_log.get("used_in_file", "").startswith("test_file_id_"), "Dependency parent ID missing or invalid"

async def test_parse_class_with_imports_file(parser: PythonParser, tmp_path: Path):
    """Test parsing class_with_imports.py from test_data."""
    test_file = TEST_DATA_DIR / "class_with_imports.py"
    results = await run_parser_and_save_output(parser, test_file, tmp_path)

    assert len(results) > 0, "Expected DataPoints from non-empty file"
    payloads = [dp.payload for dp in results]

    # Check for TextChunks
    chunks = [p for p in payloads if p.get("type") == "TextChunk"]
    assert len(chunks) >= 1, "Expected at least one TextChunk"

    # Check for CodeEntity (ClassDefinition)
    classes = [p for p in payloads if p.get("type") == "ClassDefinition"]
    assert len(classes) == 1, "Expected exactly one class definition"
    cls = classes[0]
    assert cls.get("name") == "DataProcessor"
    assert cls.get("start_line") == 5, "Incorrect start line for DataProcessor class"
    assert cls.get("end_line") == 28, "Incorrect end line for DataProcessor class"
    assert '"""Processes data asynchronously."""' in cls.get("source_code_snippet", ""), "Class docstring missing"
    assert cls.get("defined_in_file", "").startswith("test_file_id_"), "Class parent ID missing or invalid"

    # Check for CodeEntity (FunctionDefinition - includes methods and standalone function)
    funcs = [p for p in payloads if p.get("type") == "FunctionDefinition"]
    assert len(funcs) == 4, "Expected 4 functions (__init__, load_data, process, main)"
    # Create a dict for easier access: {name: payload}
    func_map = {f.get("name"): f for f in funcs}

    assert "__init__" in func_map
    assert func_map["__init__"]["start_line"] == 10
    assert func_map["__init__"]["end_line"] == 12
    assert "def __init__(self, source: str):" in func_map["__init__"]["source_code_snippet"]

    assert "load_data" in func_map
    assert func_map["load_data"]["start_line"] == 14
    assert func_map["load_data"]["end_line"] == 17
    assert '"""Loads data from the source."""' in func_map["load_data"]["source_code_snippet"]
    assert "async def load_data(self):" in func_map["load_data"]["source_code_snippet"]

    assert "process" in func_map
    assert func_map["process"]["start_line"] == 19
    assert func_map["process"]["end_line"] == 28
    assert "async def process(self) -> int:" in func_map["process"]["source_code_snippet"]

    assert "main" in func_map # Standalone async function
    assert func_map["main"]["start_line"] == 31
    assert func_map["main"]["end_line"] == 34
    assert "async def main():" in func_map["main"]["source_code_snippet"]

    # Check for Dependency
    deps = [p for p in payloads if p.get("type") == "Dependency"]
    # Sort by line number for consistent checks
    deps.sort(key=lambda d: d.get("start_line", 0))
    assert len(deps) == 4, "Expected 4 dependencies"

    # Check targets and snippets (Note: 'from typing import List, Dict' might yield multiple based on query)
    assert deps[0].get("target_module") == "asyncio"
    assert deps[0].get("source_code_snippet") == "import asyncio"
    assert deps[0].get("start_line") == 1

    # Check typing imports (current query yields one target per named import)
    assert deps[1].get("target_module") == "typing.List"
    assert deps[1].get("source_code_snippet") == "from typing import List, Dict"
    assert deps[1].get("start_line") == 2

    assert deps[2].get("target_module") == "typing.Dict"
    assert deps[2].get("source_code_snippet") == "from typing import List, Dict"
    assert deps[2].get("start_line") == 2

    # Check relative import
    assert deps[3].get("target_module") == ".utils.helper_func"
    assert deps[3].get("source_code_snippet") == "from .utils import helper_func # Example relative import"
    assert deps[3].get("start_line") == 3


async def test_parse_file_with_only_comments(parser: PythonParser, tmp_path: Path):
    """Test parsing a file containing only comments and whitespace."""
    content = """
# This is a comment line.
# Another comment.

# More comments after whitespace.

""" # Added trailing newline as files often have one
    test_file = tmp_path / "comments_only.py"
    test_file.write_text(content, encoding="utf-8")
    results = await run_parser_and_save_output(parser, test_file, tmp_path)

    # Expect only TextChunks if content is not empty, otherwise empty list
    if content.strip():
        assert len(results) >= 1, "Should produce at least one chunk for non-empty comment file"
        payloads = [dp.payload for dp in results]
        assert all(p.get("type") == "TextChunk" for p in payloads), "Only TextChunks expected"
        # Check content is preserved
        full_text = "".join(p["text"] for p in payloads)
        assert "# This is a comment line." in full_text
        assert "# More comments after whitespace." in full_text
    else:
        assert len(results) == 0, "Should be empty if content was only whitespace"


# Potential future tests:
# - File with decorators
# - File with nested functions/classes
# - File with more complex import aliasing (import a.b.c as d)
# - File with syntax errors (how does tree-sitter/parser handle?)
