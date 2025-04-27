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
    from src.parser.parsers.c_parser import CParser
    # Assuming C entities map to these generic types
    from src.parser.entities import DataPoint, TextChunk, CodeEntity, Dependency
except ImportError as e:
    pytest.skip(f"Skipping C parser tests: Failed to import dependencies - {e}", allow_module_level=True)

# Avoid runtime import errors if BaseParser isn't directly used
if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser

# --- Test Configuration ---
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "c"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

# Helper fixture `run_parser_and_save_output` is defined in tests/parser/conftest.py
# and injected by pytest into test functions that request it.
# --- Parser Fixture ---
@pytest.fixture(scope="module")
def parser() -> CParser:
    """Provides a CParser instance, skipping if language not loaded."""
    try:
        from src.parser.parsers.treesitter_setup import get_language
        if get_language("c") is None:
            pytest.skip("C tree-sitter language not loaded or available.", allow_module_level=True)
    except ImportError as e:
        pytest.skip(f"Tree-sitter setup or core library not available: {e}", allow_module_level=True)

    return CParser()

# --- Test Cases ---

async def test_parse_empty_c_file(parser: CParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing an empty C file."""
    empty_file = tmp_path / "empty.c"
    empty_file.touch()
    results = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0, "Empty .c file should yield no DataPoints"

async def test_parse_empty_h_file(parser: CParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing an empty C header file."""
    empty_file = tmp_path / "empty.h"
    empty_file.touch()
    results = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0, "Empty .h file should yield no DataPoints"

async def test_parse_simple_function_file(parser: CParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing simple_function.c from test_data."""
    test_file = TEST_DATA_DIR / "simple_function.c"
    results = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0, "Expected DataPoints from non-empty file"
    # Use model_dump to get payloads
    payloads = [dp.model_dump(mode='json') for dp in results]

    # Check for TextChunks (Type is top-level)
    chunks = [p for p in payloads if p.get("type") == "TextChunk"]
    assert len(chunks) >= 1, "Expected at least one TextChunk"
    # Example check on chunk content if needed
    # assert any("int main" in chunk.get("text_content", "") for chunk in chunks)

    # Check for CodeEntity (FunctionDefinition - Type is top-level)
    funcs = [p for p in payloads if p.get("type") == "FunctionDefinition"]
    assert len(funcs) == 2, "Expected two function definitions: add, main"
    # Access metadata for specific fields
    func_map = {f.get("metadata", {}).get("name"): f for f in funcs}

    assert "add" in func_map
    add_meta = func_map["add"].get("metadata", {})
    assert add_meta.get("start_line") == 9
    assert add_meta.get("end_line") == 11
    assert "int add(int a, int b)" in func_map["add"].get("text_content", "") # Check main content field

    assert "main" in func_map
    main_meta = func_map["main"].get("metadata", {})
    assert main_meta.get("start_line") == 18
    assert main_meta.get("end_line") == 35
    assert "int main(int argc, char *argv[])" in func_map["main"].get("text_content", "") # Check main content field

    # Check for CodeEntity (TypeDefinition - Type is top-level)
    typedefs = [p for p in payloads if p.get("type") == "TypeDefinition"]
    assert len(typedefs) == 1, "Expected one TypeDefinition for Record"
    typedef_record = typedefs[0]
    typedef_meta = typedef_record.get("metadata", {})
    assert typedef_meta.get("name") == "Record"
    assert typedef_meta.get("start_line") == 13, "Incorrect start line for typedef Record"
    assert typedef_meta.get("end_line") == 16, "Incorrect end line for typedef Record"
    assert "typedef struct {" in typedef_record.get("text_content", "") # Check main content field
    assert "} Record;" in typedef_record.get("text_content", "") # Check main content field

    # Check for Dependency (Type is top-level)
    deps = [p for p in payloads if p.get("type") == "Dependency"]
    assert len(deps) == 3, "Expected three include dependencies"
    # Access metadata for sorting and checking fields
    deps.sort(key=lambda d: d.get("metadata", {}).get("start_line", 0)) # Sort by line in metadata

    dep0_meta = deps[0].get("metadata", {})
    assert dep0_meta.get("target_module") == "stdio.h"
    assert dep0_meta.get("start_line") == 1
    assert deps[0].get("text_content") == "#include <stdio.h>" # Check main content field

    dep1_meta = deps[1].get("metadata", {})
    assert dep1_meta.get("target_module") == "stdlib.h"
    assert dep1_meta.get("start_line") == 2
    assert deps[1].get("text_content") == "#include <stdlib.h>" # Check main content field

    dep2_meta = deps[2].get("metadata", {})
    assert dep2_meta.get("target_module") == "header.h"
    assert dep2_meta.get("start_line") == 3
    assert deps[2].get("text_content") == '#include "header.h" // Local header include' # Check main content field

async def test_parse_header_file(parser: CParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing header.h from test_data."""
    test_file = TEST_DATA_DIR / "header.h"
    results = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0, "Expected DataPoints from non-empty header file"
    payloads = [dp.model_dump(mode='json') for dp in results]

    # Check for TextChunks
    chunks = [p for p in payloads if p.get("type") == "TextChunk"]
    assert len(chunks) >= 1, "Expected at least one TextChunk"

    # Check for CodeEntity (TypeDefinition - via typedef struct)
    typedefs = [p for p in payloads if p.get("type") == "TypeDefinition"]
    assert len(typedefs) == 1, "Expected one TypeDefinition for Point"
    typedef_point = typedefs[0]
    typedef_meta = typedef_point.get("metadata", {})
    assert typedef_meta.get("name") == "Point"
    assert typedef_meta.get("start_line") == 5, "Incorrect start line for typedef Point"
    assert typedef_meta.get("end_line") == 8, "Incorrect end line for typedef Point"
    assert "typedef struct {" in typedef_point.get("text_content","") # Check main content
    assert "} Point;" in typedef_point.get("text_content","") # Check main content

    # Check for Absence of Function Definitions (Prototypes are not definitions)
    # The current C query only finds function_definition nodes.
    funcs = [p for p in payloads if p.get("type") == "FunctionDefinition"]
    assert len(funcs) == 0, "Parser should not currently find function prototypes/declarations as definitions"

    # Check for Absence of Dependencies (no #include in this header)
    deps = [p for p in payloads if p.get("type") == "Dependency"]
    assert len(deps) == 0, "No include dependencies expected in header.h"

async def test_parse_file_with_only_directives(parser: CParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing a file containing only preprocessor directives and includes."""
    content = """
#ifndef MY_GUARD_H
#define MY_GUARD_H

#define MY_MACRO(x) ((x) * (x))
#define ANOTHER_MACRO 123

#include <stddef.h> // Should still be found

#endif // MY_GUARD_H
"""
    test_file = tmp_path / "directives.h"
    test_file.write_text(content, encoding="utf-8")
    results = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0, "Expected DataPoints from directives file"
    payloads = [dp.model_dump(mode='json') for dp in results]

    # Expect TextChunks
    chunks = [p for p in payloads if p.get("type") == "TextChunk"]
    assert len(chunks) >= 1, "Expected at least one chunk"

    # Expect the include Dependency
    deps = [p for p in payloads if p.get("type") == "Dependency"]
    assert len(deps) == 1, "Expected one include dependency"
    dep0_meta = deps[0].get("metadata", {})
    assert dep0_meta.get("target_module") == "stddef.h"
    assert dep0_meta.get("start_line") == 7
    assert deps[0].get("text_content") == "#include <stddef.h>" # Check main content

    # Expect no Function, Struct, Typedef etc. defined by current queries
    entity_types = {p.get("type") for p in payloads} # Check top-level type
    assert "FunctionDefinition" not in entity_types
    # The C queries don't define these specific types yet
    # assert "StructDefinition" not in entity_types
    assert "TypeDefinition" not in entity_types
    # assert "EnumDefinition" not in entity_types
    # assert "UnionDefinition" not in entity_types
