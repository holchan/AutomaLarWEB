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

# Helper fixture `run_parser_and_save_output` is defined in tests/parser/conftest.py
# and injected by pytest into test functions that request it.
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

async def test_parse_empty_file(parser: PythonParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing an empty Python file."""
    empty_file = tmp_path / "empty.py"
    empty_file.touch()
    results = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0, "Empty file should yield no DataPoints"

async def test_parse_simple_function_file(parser: PythonParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing simple_function.py from test_data."""
    test_file = TEST_DATA_DIR / "simple_function.py"
    results = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    # Basic checks
    assert len(results) > 0, "Expected DataPoints from non-empty file"
    payloads = [dp.model_dump(mode='json') for dp in results] # Use model_dump

    # Check for TextChunks
    chunks = [p for p in payloads if p.get("type") == "TextChunk"]
    assert len(chunks) >= 1, "Expected at least one TextChunk"
    chunk0_meta = chunks[0].get("metadata", {})
    assert chunk0_meta.get("chunk_index") == 0, "First chunk index should be 0"
    assert chunks[0].get("text_content","").strip().startswith("# A simple function example"), "First chunk content mismatch"
    assert chunk0_meta.get("chunk_of", "").startswith("test_file_id_"), "Chunk parent ID missing or invalid" # Check parent link

    # Check for CodeEntity (FunctionDefinition)
    funcs = [p for p in payloads if p.get("type") == "FunctionDefinition"]
    assert len(funcs) == 1, "Expected exactly one function definition"
    func = funcs[0]
    func_meta = func.get("metadata", {})
    assert func_meta.get("name") == "process_data"
    assert func_meta.get("start_line") == 7, "Incorrect start line for process_data"
    assert func_meta.get("end_line") == 14, "Incorrect end line for process_data"
    assert "def process_data(file_path: str) -> bool:" in func.get("text_content", ""), "Function signature mismatch"
    assert '"""' in func.get("text_content", ""), "Docstring seems missing from snippet"
    assert func_meta.get("defined_in_file", "").startswith("test_file_id_"), "Function parent ID missing or invalid"

    # Check for Dependency
    deps = [p for p in payloads if p.get("type") == "Dependency"]
    assert len(deps) == 2, "Expected two import dependencies"
    # Sort by line number for consistent checks
    deps.sort(key=lambda d: d.get("metadata", {}).get("start_line", 0))
    dep_os = deps[0]
    dep_log = deps[1]
    dep_os_meta = dep_os.get("metadata", {})
    dep_log_meta = dep_log.get("metadata", {})

    assert dep_os_meta.get("target_module") == "os"
    assert dep_os_meta.get("start_line") == 2
    assert dep_os_meta.get("end_line") == 2
    assert dep_os.get("text_content") == "import os" # Check main content
    assert dep_os_meta.get("used_in_file", "").startswith("test_file_id_"), "Dependency parent ID missing or invalid"

    assert dep_log_meta.get("target_module") == "logging"
    assert dep_log_meta.get("start_line") == 3
    assert dep_log_meta.get("end_line") == 3
    assert dep_log.get("text_content") == "import logging" # Check main content
    assert dep_log_meta.get("used_in_file", "").startswith("test_file_id_"), "Dependency parent ID missing or invalid"

async def test_parse_class_with_imports_file(parser: PythonParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing class_with_imports.py from test_data."""
    test_file = TEST_DATA_DIR / "class_with_imports.py"
    results = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0, "Expected DataPoints from non-empty file"
    payloads = [dp.model_dump(mode='json') for dp in results] # Use model_dump

    # Check for TextChunks
    chunks = [p for p in payloads if p.get("type") == "TextChunk"]
    assert len(chunks) >= 1, "Expected at least one TextChunk"

    # Check for CodeEntity (ClassDefinition)
    classes = [p for p in payloads if p.get("type") == "ClassDefinition"]
    assert len(classes) == 1, "Expected exactly one class definition"
    cls = classes[0]
    cls_meta = cls.get("metadata", {})
    assert cls_meta.get("name") == "DataProcessor"
    assert cls_meta.get("start_line") == 5, "Incorrect start line for DataProcessor class"
    assert cls_meta.get("end_line") == 28, "Incorrect end line for DataProcessor class"
    assert '"""Processes data asynchronously."""' in cls.get("text_content", ""), "Class docstring missing"
    assert cls_meta.get("defined_in_file", "").startswith("test_file_id_"), "Class parent ID missing or invalid"

    # Check for CodeEntity (FunctionDefinition - includes methods and standalone function)
    funcs = [p for p in payloads if p.get("type") == "FunctionDefinition"]
    assert len(funcs) == 4, "Expected 4 functions (__init__, load_data, process, main)"
    # Create a dict for easier access: {name: payload}
    func_map = {f.get("metadata", {}).get("name"): f for f in funcs}

    assert "__init__" in func_map
    init_meta = func_map["__init__"].get("metadata", {})
    assert init_meta.get("start_line") == 10
    assert init_meta.get("end_line") == 12
    assert "def __init__(self, source: str):" in func_map["__init__"].get("text_content", "")

    assert "load_data" in func_map
    load_data_meta = func_map["load_data"].get("metadata", {})
    assert load_data_meta.get("start_line") == 14
    assert load_data_meta.get("end_line") == 17
    assert '"""Loads data from the source."""' in func_map["load_data"].get("text_content", "")
    assert "async def load_data(self):" in func_map["load_data"].get("text_content", "")

    assert "process" in func_map
    process_meta = func_map["process"].get("metadata", {})
    assert process_meta.get("start_line") == 19
    assert process_meta.get("end_line") == 28
    assert "async def process(self) -> int:" in func_map["process"].get("text_content", "")

    assert "main" in func_map # Standalone async function
    main_meta = func_map["main"].get("metadata", {})
    assert main_meta.get("start_line") == 31
    assert main_meta.get("end_line") == 34
    assert "async def main():" in func_map["main"].get("text_content", "")

    # Check for Dependency
    deps = [p for p in payloads if p.get("type") == "Dependency"]
    # Sort by line number for consistent checks
    deps.sort(key=lambda d: d.get("metadata", {}).get("start_line", 0))
    assert len(deps) == 4, "Expected 4 dependencies"

    # Check targets and snippets (Note: 'from typing import List, Dict' might yield multiple based on query)
    dep0_meta = deps[0].get("metadata", {})
    assert dep0_meta.get("target_module") == "asyncio"
    assert deps[0].get("text_content") == "import asyncio" # Check main content
    assert dep0_meta.get("start_line") == 1

    # Check typing imports (current query yields one target per named import)
    dep1_meta = deps[1].get("metadata", {})
    assert dep1_meta.get("target_module") == "typing.List"
    assert deps[1].get("text_content") == "from typing import List, Dict" # Check main content
    assert dep1_meta.get("start_line") == 2

    dep2_meta = deps[2].get("metadata", {})
    assert dep2_meta.get("target_module") == "typing.Dict"
    assert deps[2].get("text_content") == "from typing import List, Dict" # Check main content
    assert dep2_meta.get("start_line") == 2

    # Check relative import
    dep3_meta = deps[3].get("metadata", {})
    assert dep3_meta.get("target_module") == ".utils.helper_func"
    assert deps[3].get("text_content") == "from .utils import helper_func # Example relative import" # Check main content
    assert dep3_meta.get("start_line") == 3


async def test_parse_file_with_only_comments(parser: PythonParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing a file containing only comments and whitespace."""
    content = """
# This is a comment line.
# Another comment.

# More comments after whitespace.

""" # Added trailing newline as files often have one
    test_file = tmp_path / "comments_only.py"
    test_file.write_text(content, encoding="utf-8")
    results = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    # Expect only TextChunks if content is not empty, otherwise empty list
    if content.strip():
        assert len(results) >= 1, "Should produce at least one chunk for non-empty comment file"
        payloads = [dp.model_dump(mode='json') for dp in results] # Use model_dump
        assert all(p.get("type") == "TextChunk" for p in payloads), "Only TextChunks expected"
        # Check content is preserved
        full_text = "".join(p.get("text_content", "") for p in payloads) # Use text_content
        assert "# This is a comment line." in full_text
        assert "# More comments after whitespace." in full_text
    else:
        assert len(results) == 0, "Should be empty if content was only whitespace"


# Potential future tests:
# - File with decorators
# - File with nested functions/classes
# - File with more complex import aliasing (import a.b.c as d)
# - File with syntax errors (how does tree-sitter/parser handle?)
