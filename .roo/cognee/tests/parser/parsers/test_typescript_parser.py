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
    from src.parser.parsers.typescript_parser import TypescriptParser
    # Use generic CodeEntity and check the 'type' field in payload
    from src.parser.entities import DataPoint, TextChunk, CodeEntity, Dependency
except ImportError as e:
    pytest.skip(f"Skipping TS parser tests: Failed to import dependencies - {e}", allow_module_level=True)

# Avoid runtime import errors if BaseParser isn't directly used
if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser

# --- Test Configuration ---
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "typescript"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

# Helper function `run_parser_and_save_output` is now expected to be in conftest.py
# --- Parser Fixture ---
@pytest.fixture(scope="module")
def parser() -> TypescriptParser:
    """Provides a TypescriptParser instance, skipping if language not loaded."""
    try:
        from src.parser.parsers.treesitter_setup import get_language
        # Check for the correct language key used in setup ('typescript')
        if get_language("typescript") is None:
            pytest.skip("TypeScript tree-sitter language not loaded or available.", allow_module_level=True)
    except ImportError as e:
        pytest.skip(f"Tree-sitter setup or core library not available: {e}", allow_module_level=True)

    return TypescriptParser()

# --- Test Cases ---

async def test_parse_empty_ts_file(parser: TypescriptParser, tmp_path: Path):
    """Test parsing an empty TypeScript file."""
    empty_file = tmp_path / "empty.ts"
    empty_file.touch()
    results = await run_parser_and_save_output(parser, empty_file, tmp_path)
    assert len(results) == 0, "Empty file should yield no DataPoints"

async def test_parse_simple_function_file(parser: TypescriptParser, tmp_path: Path):
    """Test parsing simple_function.ts from test_data."""
    test_file = TEST_DATA_DIR / "simple_function.ts"
    results = await run_parser_and_save_output(parser, test_file, tmp_path)

    assert len(results) > 0, "Expected DataPoints from non-empty file"
    payloads = [dp.model_dump(mode='json') for dp in results]

    # Check for TextChunks
    chunks = [p for p in payloads if p.get("type") == "TextChunk"]
    assert len(chunks) >= 1, "Expected at least one TextChunk"
    assert chunks[0].get("text_content","").strip().startswith("// Simple TS types and functions"), "First chunk content mismatch"

    # Check for CodeEntity (InterfaceDefinition)
    interfaces = [p for p in payloads if p.get("type") == "InterfaceDefinition"]
    assert len(interfaces) == 1, "Expected one interface definition"
    iface = interfaces[0]
    iface_meta = iface.get("metadata", {})
    assert iface_meta.get("name") == "User"
    assert iface_meta.get("start_line") == 4, "Incorrect start line for interface User"
    assert iface_meta.get("end_line") == 8, "Incorrect end line for interface User"
    assert "export interface User" in iface.get("text_content","") # Check main content

    # Check for CodeEntity (TypeDefinition)
    types = [p for p in payloads if p.get("type") == "TypeDefinition"]
    assert len(types) == 1, "Expected one type alias definition"
    type_alias = types[0]
    type_alias_meta = type_alias.get("metadata", {})
    assert type_alias_meta.get("name") == "Result"
    assert type_alias_meta.get("start_line") == 10, "Incorrect start line for type Result"
    assert type_alias_meta.get("end_line") == 12, "Incorrect end line for type Result"
    assert "export type Result<T>" in type_alias.get("text_content","") # Check main content

    # Check for CodeEntity (FunctionDefinition)
    funcs = [p for p in payloads if p.get("type") == "FunctionDefinition"]
    assert len(funcs) == 2, "Expected two functions: processUser, formatResult"
    func_map = {f.get("metadata", {}).get("name"): f for f in funcs if f.get("metadata", {}).get("name")}

    assert "processUser" in func_map
    pu_meta = func_map["processUser"].get("metadata", {})
    assert pu_meta.get("start_line") == 14
    assert pu_meta.get("end_line") == 19
    assert "function processUser(user: User, logger: Logger): Result<string>" in func_map["processUser"].get("text_content", "") # Check main content

    assert "formatResult" in func_map
    fr_meta = func_map["formatResult"].get("metadata", {})
    assert fr_meta.get("start_line") == 21
    assert fr_meta.get("end_line") == 23
    assert "const formatResult = <T>(result: Result<T>): string =>" in func_map["formatResult"].get("text_content", "") # Check main content

    # Check for Dependency (Type-only import)
    deps = [p for p in payloads if p.get("type") == "Dependency"]
    assert len(deps) == 1, "Expected one import dependency"
    dep = deps[0]
    dep_meta = dep.get("metadata", {})
    assert dep_meta.get("target_module") == "./logger"
    assert dep_meta.get("start_line") == 2, "Incorrect start line for import"
    assert "import { type Logger } from \"./logger\"; // Type-only import" in dep.get("text_content","") # Check main content


async def test_parse_class_with_interfaces_file(parser: TypescriptParser, tmp_path: Path):
    """Test parsing class_with_interfaces.tsx from test_data."""
    test_file = TEST_DATA_DIR / "class_with_interfaces.tsx" # Note .tsx extension
    results = await run_parser_and_save_output(parser, test_file, tmp_path)

    assert len(results) > 0, "Expected DataPoints from .tsx file"
    payloads = [dp.model_dump(mode='json') for dp in results]

    # Check for TextChunks
    chunks = [p for p in payloads if p.get("type") == "TextChunk"]
    assert len(chunks) >= 1, "Expected at least one TextChunk"

    # Check for CodeEntity (InterfaceDefinition)
    interfaces = [p for p in payloads if p.get("type") == "InterfaceDefinition"]
    assert len(interfaces) == 2, "Expected two interface definitions"
    iface_map = {i.get("metadata", {}).get("name"): i for i in interfaces}
    assert "GreeterProps" in iface_map
    assert "ComponentState" in iface_map
    assert iface_map["GreeterProps"].get("metadata", {}).get("start_line") == 4
    assert iface_map["ComponentState"].get("metadata", {}).get("start_line") == 8

    # Check for CodeEntity (ClassDefinition)
    classes = [p for p in payloads if p.get("type") == "ClassDefinition"]
    assert len(classes) == 1, "Expected one class definition"
    cls = classes[0]
    cls_meta = cls.get("metadata", {})
    assert cls_meta.get("name") == "GreeterComponent"
    assert cls_meta.get("start_line") == 10, "Incorrect start line for class"
    assert cls_meta.get("end_line") == 38, "Incorrect end line for class"

    # Check for CodeEntity (FunctionDefinition - methods and functional component)
    funcs = [p for p in payloads if p.get("type") == "FunctionDefinition"]
    # Expect: componentDidMount, componentWillUnmount, render, FunctionalGreeter
    # Note: constructor might not be captured if implicit. State init isn't a function.
    assert len(funcs) == 4, "Expected 4 function definitions"
    func_map = {f.get("metadata", {}).get("name"): f for f in funcs if f.get("metadata", {}).get("name")}

    assert "componentDidMount" in func_map
    cdm_meta = func_map["componentDidMount"].get("metadata", {})
    assert cdm_meta.get("start_line") == 19
    assert cdm_meta.get("end_line") == 23

    assert "componentWillUnmount" in func_map
    cwu_meta = func_map["componentWillUnmount"].get("metadata", {})
    assert cwu_meta.get("start_line") == 25
    assert cwu_meta.get("end_line") == 29 # Corrected end line

    assert "render" in func_map
    render_meta = func_map["render"].get("metadata", {})
    assert render_meta.get("start_line") == 31 # Corrected start line
    assert render_meta.get("end_line") == 37 # Corrected end line
    assert "<h1>Hello, {name}!</h1>" in func_map["render"].get("text_content", "") # Check JSX in main content

    assert "FunctionalGreeter" in func_map
    fg_meta = func_map["FunctionalGreeter"].get("metadata", {})
    assert fg_meta.get("start_line") == 40
    assert fg_meta.get("end_line") == 45
    assert "export const FunctionalGreeter: FC<GreeterProps>" in func_map["FunctionalGreeter"].get("text_content", "") # Check main content

    # Check for Dependency
    deps = [p for p in payloads if p.get("type") == "Dependency"]
    # Expecting two deps from 'react' (one value import, one type import)
    assert len(deps) == 2, "Expected two dependencies"
    deps.sort(key=lambda d: d.get("metadata", {}).get("start_line", 0)) # Sort by line in metadata

    dep0_meta = deps[0].get("metadata", {})
    assert dep0_meta.get("target_module") == "react"
    assert dep0_meta.get("start_line") == 1
    assert "import React, { useState, useEffect } from \"react\";" in deps[0].get("text_content","") # Check main content

    dep1_meta = deps[1].get("metadata", {})
    assert dep1_meta.get("target_module") == "react" # Target is still 'react' for type import
    assert dep1_meta.get("start_line") == 2
    assert "import type { FC } from \"react\";" in deps[1].get("text_content","") # Check main content
