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

# --- Helper Function (Copied from previous step) ---
async def run_parser_and_save_output(
    parser: 'BaseParser',
    test_file_path: Path,
    output_dir: Path
) -> List['DataPoint']:
    """
    Runs the parser on a given file path, saves the payload results to a JSON
    file in output_dir, and returns the list of original DataPoint objects.
    """
    if not test_file_path.is_file():
        pytest.fail(f"Test input file not found: {test_file_path}")

    file_id_base = str(test_file_path.absolute())
    file_id = f"test_file_id_{hashlib.sha1(file_id_base.encode()).hexdigest()[:10]}"

    results_objects: List[DataPoint] = []
    results_payloads: List[dict] = []

    try:
        async for dp in parser.parse(file_path=str(test_file_path), file_id=file_id):
            results_objects.append(dp)
            if hasattr(dp, 'model_dump'):
                payload = dp.model_dump()
            elif hasattr(dp, 'payload'):
                payload = dp.payload
            else:
                payload = {"id": getattr(dp, 'id', 'unknown'), "type": "UnknownPayloadStructure"}
            results_payloads.append(payload)
    except Exception as e:
        print(f"\nERROR during parser execution for {test_file_path.name}: {e}")
        pytest.fail(f"Parser execution failed for {test_file_path.name}: {e}", pytrace=True)

    output_filename = output_dir / f"parsed_{test_file_path.stem}_output.json"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(results_payloads, f, indent=2, ensure_ascii=False, sort_keys=True)
        print(f"\n[Test Output] Saved parser results for '{test_file_path.name}' to: {output_filename}")
    except Exception as e:
        print(f"\n[Test Output] WARNING: Failed to save test output for {test_file_path.name}: {e}")

    return results_objects


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
    payloads = [dp.payload for dp in results]

    # Check for TextChunks
    chunks = [p for p in payloads if p.get("type") == "TextChunk"]
    assert len(chunks) >= 1, "Expected at least one TextChunk"
    assert chunks[0].get("text","").strip().startswith("// Simple TS types and functions"), "First chunk content mismatch"

    # Check for CodeEntity (InterfaceDefinition)
    interfaces = [p for p in payloads if p.get("type") == "InterfaceDefinition"]
    assert len(interfaces) == 1, "Expected one interface definition"
    iface = interfaces[0]
    assert iface.get("name") == "User"
    assert iface.get("start_line") == 4, "Incorrect start line for interface User"
    assert iface.get("end_line") == 8, "Incorrect end line for interface User"
    assert "export interface User" in iface.get("source_code_snippet","")

    # Check for CodeEntity (TypeDefinition)
    types = [p for p in payloads if p.get("type") == "TypeDefinition"]
    assert len(types) == 1, "Expected one type alias definition"
    type_alias = types[0]
    assert type_alias.get("name") == "Result"
    assert type_alias.get("start_line") == 10, "Incorrect start line for type Result"
    assert type_alias.get("end_line") == 12, "Incorrect end line for type Result"
    assert "export type Result<T>" in type_alias.get("source_code_snippet","")

    # Check for CodeEntity (FunctionDefinition)
    funcs = [p for p in payloads if p.get("type") == "FunctionDefinition"]
    assert len(funcs) == 2, "Expected two functions: processUser, formatResult"
    func_map = {f.get("name"): f for f in funcs if f.get("name")}

    assert "processUser" in func_map
    assert func_map["processUser"]["start_line"] == 14
    assert func_map["processUser"]["end_line"] == 19
    assert "function processUser(user: User, logger: Logger): Result<string>" in func_map["processUser"]["source_code_snippet"]

    assert "formatResult" in func_map
    assert func_map["formatResult"]["start_line"] == 21
    assert func_map["formatResult"]["end_line"] == 23
    assert "const formatResult = <T>(result: Result<T>): string =>" in func_map["formatResult"]["source_code_snippet"]

    # Check for Dependency (Type-only import)
    deps = [p for p in payloads if p.get("type") == "Dependency"]
    assert len(deps) == 1, "Expected one import dependency"
    dep = deps[0]
    assert dep.get("target_module") == "./logger"
    assert dep.get("start_line") == 2, "Incorrect start line for import"
    assert "import { type Logger } from \"./logger\"; // Type-only import" in dep.get("source_code_snippet","")


async def test_parse_class_with_interfaces_file(parser: TypescriptParser, tmp_path: Path):
    """Test parsing class_with_interfaces.tsx from test_data."""
    test_file = TEST_DATA_DIR / "class_with_interfaces.tsx" # Note .tsx extension
    results = await run_parser_and_save_output(parser, test_file, tmp_path)

    assert len(results) > 0, "Expected DataPoints from .tsx file"
    payloads = [dp.payload for dp in results]

    # Check for TextChunks
    chunks = [p for p in payloads if p.get("type") == "TextChunk"]
    assert len(chunks) >= 1, "Expected at least one TextChunk"

    # Check for CodeEntity (InterfaceDefinition)
    interfaces = [p for p in payloads if p.get("type") == "InterfaceDefinition"]
    assert len(interfaces) == 2, "Expected two interface definitions"
    iface_map = {i.get("name"): i for i in interfaces}
    assert "GreeterProps" in iface_map
    assert "ComponentState" in iface_map
    assert iface_map["GreeterProps"]["start_line"] == 4
    assert iface_map["ComponentState"]["start_line"] == 8

    # Check for CodeEntity (ClassDefinition)
    classes = [p for p in payloads if p.get("type") == "ClassDefinition"]
    assert len(classes) == 1, "Expected one class definition"
    cls = classes[0]
    assert cls.get("name") == "GreeterComponent"
    assert cls.get("start_line") == 10, "Incorrect start line for class"
    assert cls.get("end_line") == 38, "Incorrect end line for class"

    # Check for CodeEntity (FunctionDefinition - methods and functional component)
    funcs = [p for p in payloads if p.get("type") == "FunctionDefinition"]
    # Expect: componentDidMount, componentWillUnmount, render, FunctionalGreeter
    # Note: constructor might not be captured if implicit. State init isn't a function.
    assert len(funcs) == 4, "Expected 4 function definitions"
    func_map = {f.get("name"): f for f in funcs if f.get("name")}

    assert "componentDidMount" in func_map
    assert func_map["componentDidMount"]["start_line"] == 19
    assert func_map["componentDidMount"]["end_line"] == 23

    assert "componentWillUnmount" in func_map
    assert func_map["componentWillUnmount"]["start_line"] == 25
    assert func_map["componentWillUnmount"]["end_line"] == 29 # Corrected end line

    assert "render" in func_map
    assert func_map["render"]["start_line"] == 31 # Corrected start line
    assert func_map["render"]["end_line"] == 37 # Corrected end line
    assert "<h1>Hello, {name}!</h1>" in func_map["render"].get("source_code_snippet", "") # Check JSX

    assert "FunctionalGreeter" in func_map
    assert func_map["FunctionalGreeter"]["start_line"] == 40
    assert func_map["FunctionalGreeter"]["end_line"] == 45
    assert "export const FunctionalGreeter: FC<GreeterProps>" in func_map["FunctionalGreeter"].get("source_code_snippet", "")

    # Check for Dependency
    deps = [p for p in payloads if p.get("type") == "Dependency"]
    # Expecting two deps from 'react' (one value import, one type import)
    assert len(deps) == 2, "Expected two dependencies"
    deps.sort(key=lambda d: d.get("start_line", 0))

    assert deps[0].get("target_module") == "react"
    assert deps[0].get("start_line") == 1
    assert "import React, { useState, useEffect } from \"react\";" in deps[0].get("source_code_snippet","")

    assert deps[1].get("target_module") == "react" # Target is still 'react' for type import
    assert deps[1].get("start_line") == 2
    assert "import type { FC } from \"react\";" in deps[1].get("source_code_snippet","")
