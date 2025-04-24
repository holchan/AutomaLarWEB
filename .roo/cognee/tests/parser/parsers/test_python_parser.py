# tests/parser/parsers/test_python_parser.py
import pytest
import asyncio
import os
from pathlib import Path
from src.parser.parsers.python_parser import PythonParser
from src.parser.entities import CodeEntity, Dependency, TextChunk

# Use pytest-asyncio for async tests
pytestmark = pytest.mark.asyncio

# Helper to run parser on content written to a temp file
async def run_parser_on_code(parser: PythonParser, tmp_path: Path, filename: str, code: str) -> list:
    """Writes code to a temp file and runs the parser."""
    test_file_path = tmp_path / filename
    test_file_path.write_text(code, encoding="utf-8")
    file_id = f"test_{filename}_id" # Create a dummy file ID for testing
    results = []
    async for dp in parser.parse(file_path=str(test_file_path), file_id=file_id):
        results.append(dp.payload) # Collect payloads for easier assertion
    return results

# Fixture for the parser instance
@pytest.fixture(scope="module")
def parser():
    # Ensure tree-sitter languages are loaded before running tests
    # You might need a session-scoped fixture to handle this if setup is slow
    from src.parser.parsers.treesitter_setup import LANGUAGES
    if "python" not in LANGUAGES:
        pytest.skip("Python tree-sitter language not loaded.", allow_module_level=True)
    return PythonParser()

# --- Test Cases ---

async def test_empty_python_file(parser: PythonParser, tmp_path: Path):
    filename = "empty.py"
    code = ""
    results = await run_parser_on_code(parser, tmp_path, filename, code) # Corrected helper function name
    assert len(results) == 0 # Should yield nothing for empty file (no chunks)

async def test_python_simple_function(parser: PythonParser, tmp_path: Path):
    filename = "simple_function.py"
    code = """
# A simple function example
import os
import logging

logger = logging.getLogger(__name__)

def process_data(file_path: str) -> bool:
    '''Docstring for process_data.'''
    if not os.path.exists(file_path):
        logger.error("File not found")
        return False
    # Simulate processing
    print(f"Processing {file_path}")
    return True

# End of file
"""
    results = await run_parser_on_code(parser, tmp_path, filename, code) # Corrected helper function name

    assert len(results) > 0 # Expect chunks + entities

    # Check for function
    funcs = [dp for dp in results if dp.get("type") == "FunctionDefinition"]
    assert len(funcs) == 1
    assert funcs[0]["name"] == "process_data"
    assert funcs[0]["start_line"] == 7 # Line numbers are 1-based
    assert funcs[0]["end_line"] == 14 # Includes the whole block
    assert "def process_data(file_path: str) -> bool:" in funcs[0]["source_code_snippet"]
    assert "'''Docstring for process_data.'''" in funcs[0]["source_code_snippet"] # Check if docstring included

    # Check for imports
    deps = [dp for dp in results if dp.get("type") == "Dependency"]
    targets = {dp["target_module"] for dp in deps}
    assert len(deps) == 2
    assert "os" in targets
    assert "logging" in targets

    # Check for chunks (verify at least one exists and check its start)
    chunks = [dp for dp in results if dp.get("type") == "TextChunk"]
    assert len(chunks) > 0
    assert chunks[0]["text"].strip().startswith("# A simple function example")
    assert chunks[0]["chunk_index"] == 0

async def test_python_class_and_imports(parser: PythonParser, tmp_path: Path):
    filename = "class_with_imports.py"
    code = """
import asyncio
from typing import List, Dict
from .utils import helper_func # Example relative import

class DataProcessor:
    # Class docstring
    DEFAULT_TIMEOUT = 10

    def __init__(self, source: str):
        self.source = source
        self._data: List[Dict] = []

    async def load_data(self):
        print(f"Loading from {self.source}")
        await asyncio.sleep(0.1)
        self._data = [{"id": 1, "value": "A"}, {"id": 2, "value": "B"}]

    async def process(self) -> int:
        # Method docstring
        if not self._data:
            await self.load_data()
        count = 0
        for item in self._data:
            processed_value = helper_func(item.get("value"))
            print(f"Processed item {item.get('id')}: {processed_value}")
            count += 1
        return count

async def main(): # Standalone async function
    processor = DataProcessor("http://example.com/data")
    result = await processor.process()
    print(f"Processed {result} items.")
"""
    results = await run_parser_on_code(parser, tmp_path, filename, code) # Corrected helper function name

    classes = [dp for dp in results if dp.get("type") == "ClassDefinition"]
    funcs = [dp for dp in results if dp.get("type") == "FunctionDefinition"]
    deps = [dp for dp in results if dp.get("type") == "Dependency"]

    assert len(classes) == 1
    assert classes[0]["name"] == "DataProcessor"
    assert classes[0]["start_line"] == 5 # Line number

    # Should find __init__, load_data, process, and main
    assert len(funcs) == 4
    func_names = {f["name"] for f in funcs}
    assert "__init__" in func_names
    assert "load_data" in func_names
    assert "process" in func_names
    assert "main" in func_names

    dep_targets = {dp["target_module"] for dp in deps}
    assert "asyncio" in dep_targets
    assert "typing.List" in dep_targets # Query might capture List/Dict separately
    assert "typing.Dict" in dep_targets
    assert ".utils.helper_func" in dep_targets # Check relative import target

# --- Add tests for other languages similarly ---
