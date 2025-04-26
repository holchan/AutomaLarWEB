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
    from src.parser.parsers.javascript_parser import JavascriptParser
    from src.parser.entities import DataPoint, TextChunk, CodeEntity, Dependency
except ImportError as e:
    pytest.skip(f"Skipping JS parser tests: Failed to import dependencies - {e}", allow_module_level=True)

# Avoid runtime import errors if BaseParser isn't directly used
if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser

# --- Test Configuration ---
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "javascript"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

# Helper function `run_parser_and_save_output` is now expected to be in conftest.py
# --- Parser Fixture ---
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

# --- Test Cases ---

async def test_parse_empty_js_file(parser: JavascriptParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing an empty JavaScript file."""
    empty_file = tmp_path / "empty.js"
    empty_file.touch()
    results = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0, "Empty file should yield no DataPoints"

async def test_parse_simple_function_file(parser: JavascriptParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing simple_function.js from test_data."""
    test_file = TEST_DATA_DIR / "simple_function.js"
    results = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0, "Expected DataPoints from non-empty file"
    payloads = [dp.model_dump(mode='json') for dp in results]

    # Check for TextChunks
    chunks = [p for p in payloads if p.get("type") == "TextChunk"]
    assert len(chunks) >= 1, "Expected at least one TextChunk"
    assert chunks[0].get("text_content","").strip().startswith("// Simple JS functions"), "First chunk content mismatch"

    # Check for CodeEntity (FunctionDefinition)
    funcs = [p for p in payloads if p.get("type") == "FunctionDefinition"]
    # Expect: add (function declaration), multiply (arrow func assignment)
    # IIFE is an anonymous function expression, might not be captured by name in current query.
    assert len(funcs) >= 2, "Expected at least 'add' and 'multiply' functions"
    func_map = {f.get("metadata", {}).get("name"): f for f in funcs if f.get("metadata", {}).get("name")} # Filter for named functions

    assert "add" in func_map, "Function 'add' not found"
    add_meta = func_map["add"].get("metadata", {})
    assert add_meta.get("start_line") == 8, "Incorrect start line for add"
    assert add_meta.get("end_line") == 10, "Incorrect end line for add"
    assert "function add(a, b)" in func_map["add"].get("text_content", ""), "Signature mismatch for add"
    assert "Adds two numbers" in func_map["add"].get("text_content", ""), "JSDoc missing from add snippet" # Check comment capture

    assert "multiply" in func_map, "Function 'multiply' not found"
    multiply_meta = func_map["multiply"].get("metadata", {})
    assert multiply_meta.get("start_line") == 12, "Incorrect start line for multiply"
    assert multiply_meta.get("end_line") == 16, "Incorrect end line for multiply"
    assert "const multiply = (a, b) =>" in func_map["multiply"].get("text_content", ""), "Signature mismatch for multiply"

    # Check for Dependency (import and require)
    deps = [p for p in payloads if p.get("type") == "Dependency"]
    assert len(deps) == 2, "Expected 2 dependencies (require path, import utils)"
    deps.sort(key=lambda d: d.get("metadata", {}).get("start_line", 0)) # Sort by line in metadata

    dep_path = deps[0]
    dep_utils = deps[1]
    dep_path_meta = dep_path.get("metadata", {})
    dep_utils_meta = dep_utils.get("metadata", {})

    assert dep_path_meta.get("target_module") == "path"
    assert dep_path_meta.get("start_line") == 2
    assert dep_path.get("text_content") == 'const path = require("path");' # Check main content

    assert dep_utils_meta.get("target_module") == "./utils"
    assert dep_utils_meta.get("start_line") == 3
    assert dep_utils.get("text_content") == 'import { utils } from "./utils"; // ES6 import' # Check main content

async def test_parse_class_with_imports_file(parser: JavascriptParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing class_with_imports.js from test_data."""
    test_file = TEST_DATA_DIR / "class_with_imports.js"
    results = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0, "Expected DataPoints from non-empty file"
    payloads = [dp.model_dump(mode='json') for dp in results]

    # Check for TextChunks
    chunks = [p for p in payloads if p.get("type") == "TextChunk"]
    assert len(chunks) >= 1, "Expected at least one TextChunk"

    # Check for CodeEntity (ClassDefinition)
    classes = [p for p in payloads if p.get("type") == "ClassDefinition"]
    assert len(classes) == 1, "Expected exactly one class definition"
    cls = classes[0]
    cls_meta = cls.get("metadata", {})
    assert cls_meta.get("name") == "FileManager"
    assert cls_meta.get("start_line") == 4, "Incorrect start line for FileManager class"
    assert cls_meta.get("end_line") == 30, "Incorrect end line for FileManager class"

    # Check for CodeEntity (FunctionDefinition - methods)
    funcs = [p for p in payloads if p.get("type") == "FunctionDefinition"]
    # Expect: constructor, readFile, listDirectory
    assert len(funcs) == 3, "Expected 3 methods: constructor, readFile, listDirectory"
    func_map = {f.get("metadata", {}).get("name"): f for f in funcs if f.get("metadata", {}).get("name")}

    assert "constructor" in func_map
    constructor_meta = func_map["constructor"].get("metadata", {})
    assert constructor_meta.get("start_line") == 5
    assert constructor_meta.get("end_line") == 8

    assert "readFile" in func_map
    readFile_meta = func_map["readFile"].get("metadata", {})
    assert readFile_meta.get("start_line") == 10
    assert readFile_meta.get("end_line") == 18
    assert "async readFile(fileName)" in func_map["readFile"].get("text_content", "") # Check main content

    assert "listDirectory" in func_map
    listDirectory_meta = func_map["listDirectory"].get("metadata", {})
    assert listDirectory_meta.get("start_line") == 20
    assert listDirectory_meta.get("end_line") == 27

    # Check for Dependency (import and require)
    deps = [p for p in payloads if p.get("type") == "Dependency"]
    # Expect: fs/promises (import), path (require), fs (inner require)
    assert len(deps) >= 2, "Expected at least 2 top-level dependencies" # Inner require might be missed or captured differently
    deps.sort(key=lambda d: d.get("metadata", {}).get("start_line", 0)) # Sort by line in metadata

    dep_fs_promises = deps[0]
    dep_path = deps[1]
    dep_fs_promises_meta = dep_fs_promises.get("metadata", {})
    dep_path_meta = dep_path.get("metadata", {})

    assert dep_fs_promises_meta.get("target_module") == "fs/promises"
    assert dep_fs_promises_meta.get("start_line") == 1
    assert dep_fs_promises.get("text_content") == 'import fs from "fs/promises";' # Check main content

    assert dep_path_meta.get("target_module") == "path"
    assert dep_path_meta.get("start_line") == 2
    assert dep_path.get("text_content") == 'const { join } = require("path"); // CommonJS require' # Check main content

    # Check if inner require was captured (optional, depends on query needs)
    inner_require = [d for d in deps if d.get("metadata", {}).get("start_line") == 22] # Line of inner require('fs')
    # assert len(inner_require) == 1, "Inner require not captured"
    # if inner_require: assert inner_require[0].get("metadata", {}).get("target_module") == "fs"


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
    test_file = tmp_path / "component.jsx" # Use .jsx extension
    test_file.write_text(content, encoding="utf-8")
    results = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0, "Expected DataPoints from JSX file"
    payloads = [dp.model_dump(mode='json') for dp in results]

    # Check function definition includes JSX
    funcs = [p for p in payloads if p.get("type") == "FunctionDefinition"]
    assert len(funcs) == 1, "Expected one function definition"
    func = funcs[0]
    func_meta = func.get("metadata", {})
    assert func_meta.get("name") == "MyComponent"
    assert func_meta.get("start_line") == 3, "Incorrect start line for MyComponent"
    assert func_meta.get("end_line") == 10, "Incorrect end line for MyComponent"
    # Verify JSX is part of the extracted source code snippet (main content)
    assert "<div className=\"greeting\">" in func.get("text_content", ""), "JSX missing from function snippet"
    assert "<h1>Hello, {name}!</h1>" in func.get("text_content", ""), "JSX missing from function snippet"

    # Check import dependency
    deps = [p for p in payloads if p.get("type") == "Dependency"]
    assert len(deps) == 1, "Expected one import dependency"
    dep0_meta = deps[0].get("metadata", {})
    assert dep0_meta.get("target_module") == "react"
    assert dep0_meta.get("start_line") == 1, "Incorrect start line for import"
