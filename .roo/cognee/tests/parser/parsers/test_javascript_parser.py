# .roo/cognee/tests/parser/parsers/test_javascript_parser.py
import pytest
import asyncio
import os
from pathlib import Path
from typing import List, TYPE_CHECKING

pytestmark = pytest.mark.asyncio

try:
    from src.parser.entities import TextChunk, CodeEntity, Relationship, ParserOutput
    from src.parser.parsers.javascript_parser import JavascriptParser
except ImportError as e:
    pytest.skip(f"Skipping JS parser tests: Failed to import dependencies - {e}", allow_module_level=True)

if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser
    from pydantic import BaseModel

TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "javascript"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

@pytest.fixture(scope="module")
def parser() -> JavascriptParser:
    """Provides a JavascriptParser instance, skipping if language not loaded."""
    try:
        from src.parser.parsers.treesitter_setup import get_language
        if get_language("javascript") is None:
            pytest.skip("JavaScript tree-sitter language not loaded or available.", allow_module_level=True)
    except ImportError as e:
        pytest.skip(f"Tree-sitter setup or core library not available: {e}", allow_module_level=True)
    return JavascriptParser()

from ..conftest import run_parser_and_save_output

async def test_parse_empty_js_file(parser: JavascriptParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing an empty JavaScript file."""
    empty_file = tmp_path / "empty.js"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0, "Empty file should yield no DataPoints"

async def test_parse_simple_function_file(parser: JavascriptParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing simple_function.js from test_data."""
    test_file = TEST_DATA_DIR / "simple_function.js"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    funcs = [dp for dp in results if isinstance(dp, CodeEntity) and dp.type == "FunctionDefinition"]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(chunks) >= 1
    assert chunks[0].chunk_content.strip().startswith("// Simple JS functions")

    assert len(funcs) >= 2
    func_map = {f.id.split(":")[-2]: f for f in funcs if f.id.count(":") >= 3}

    assert "add" in func_map
    assert func_map["add"].start_line == 8
    assert func_map["add"].end_line == 10
    assert "function add(a, b)" in func_map["add"].snippet_content
    assert "Adds two numbers" in func_map["add"].snippet_content

    assert "multiply" in func_map
    assert func_map["multiply"].start_line == 12
    assert func_map["multiply"].end_line == 16
    assert "const multiply = (a, b) =>" in func_map["multiply"].snippet_content

    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) == 2, "Expected 2 IMPORTS relationships (require and import)"
    import_targets = {r.target_id for r in import_rels}
    assert "path" in import_targets
    assert "./utils" in import_targets

async def test_parse_class_with_imports_file(parser: JavascriptParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing class_with_imports.js from test_data."""
    test_file = TEST_DATA_DIR / "class_with_imports.js"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    classes = [dp for dp in results if isinstance(dp, CodeEntity) and dp.type == "ClassDefinition"]
    funcs = [dp for dp in results if isinstance(dp, CodeEntity) and dp.type == "FunctionDefinition"]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(chunks) >= 1
    assert len(classes) == 1
    cls = classes[0]
    assert cls.type == "ClassDefinition"
    assert ":ClassDefinition:FileManager:" in cls.id

    assert len(funcs) == 3
    func_map = {f.id.split(":")[-2]: f for f in funcs if f.id.count(":") >= 3}
    assert "constructor" in func_map
    assert "readFile" in func_map
    assert "listDirectory" in func_map

    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) >= 2, "Expected at least 2 top-level IMPORTS"
    import_targets = {r.target_id for r in import_rels}
    assert "fs/promises" in import_targets
    assert "path" in import_targets


async def test_parse_file_with_jsx(parser: JavascriptParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing a JS file containing basic JSX."""
    content = """
import React from 'react';

function MyComponent({ name }) {
    // A simple component
    return (
        <div className="greeting">
        <h1>Hello, {name}!</h1>
        <p>Welcome to the test.</p>
        </div>
    );
}

export default MyComponent;
"""
    test_file = tmp_path / "component.jsx"
    test_file.write_text(content, encoding="utf-8")
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    funcs = [dp for dp in results if isinstance(dp, CodeEntity) and dp.type == "FunctionDefinition"]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(funcs) == 1
    func = funcs[0]
    assert func.type == "FunctionDefinition"
    assert ":FunctionDefinition:MyComponent:" in func.id
    assert "<div className=\"greeting\">" in func.snippet_content
    assert "<h1>Hello, {name}!</h1>" in func.snippet_content

    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) == 1
    assert import_rels[0].target_id == "react"
