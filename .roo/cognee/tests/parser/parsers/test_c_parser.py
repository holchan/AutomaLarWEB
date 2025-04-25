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

async def test_parse_empty_c_file(parser: CParser, tmp_path: Path):
    """Test parsing an empty C file."""
    empty_file = tmp_path / "empty.c"
    empty_file.touch()
    results = await run_parser_and_save_output(parser, empty_file, tmp_path)
    assert len(results) == 0, "Empty .c file should yield no DataPoints"

async def test_parse_empty_h_file(parser: CParser, tmp_path: Path):
    """Test parsing an empty C header file."""
    empty_file = tmp_path / "empty.h"
    empty_file.touch()
    results = await run_parser_and_save_output(parser, empty_file, tmp_path)
    assert len(results) == 0, "Empty .h file should yield no DataPoints"

async def test_parse_simple_function_file(parser: CParser, tmp_path: Path):
    """Test parsing simple_function.c from test_data."""
    test_file = TEST_DATA_DIR / "simple_function.c"
    results = await run_parser_and_save_output(parser, test_file, tmp_path)

    assert len(results) > 0, "Expected DataPoints from non-empty file"
    payloads = [dp.payload for dp in results]

    # Check for TextChunks
    chunks = [p for p in payloads if p.get("type") == "TextChunk"]
    assert len(chunks) >= 1, "Expected at least one TextChunk"

    # Check for CodeEntity (FunctionDefinition)
    funcs = [p for p in payloads if p.get("type") == "FunctionDefinition"]
    assert len(funcs) == 2, "Expected two function definitions: add, main"
    func_map = {f.get("name"): f for f in funcs}

    assert "add" in func_map
    assert func_map["add"]["start_line"] == 9
    assert func_map["add"]["end_line"] == 11
    assert "int add(int a, int b)" in func_map["add"]["source_code_snippet"]

    assert "main" in func_map
    assert func_map["main"]["start_line"] == 18
    assert func_map["main"]["end_line"] == 35
    assert "int main(int argc, char *argv[])" in func_map["main"]["source_code_snippet"]

    # Check for CodeEntity (TypeDefinition - via typedef struct)
    # The query `(type_definition ... declarator: (type_identifier) @name)` captures 'Record'
    typedefs = [p for p in payloads if p.get("type") == "TypeDefinition"]
    assert len(typedefs) == 1, "Expected one TypeDefinition for Record"
    typedef_record = typedefs[0]
    assert typedef_record.get("name") == "Record"
    assert typedef_record.get("start_line") == 13, "Incorrect start line for typedef Record"
    assert typedef_record.get("end_line") == 16, "Incorrect end line for typedef Record"
    assert "typedef struct {" in typedef_record.get("source_code_snippet","")
    assert "} Record;" in typedef_record.get("source_code_snippet","")

    # Check for Dependency (Includes)
    deps = [p for p in payloads if p.get("type") == "Dependency"]
    assert len(deps) == 3, "Expected three include dependencies"
    deps.sort(key=lambda d: d.get("start_line", 0)) # Sort by line

    assert deps[0].get("target_module") == "stdio.h"
    assert deps[0].get("start_line") == 1
    assert deps[0].get("source_code_snippet") == "#include <stdio.h>"

    assert deps[1].get("target_module") == "stdlib.h"
    assert deps[1].get("start_line") == 2
    assert deps[1].get("source_code_snippet") == "#include <stdlib.h>"

    assert deps[2].get("target_module") == "header.h"
    assert deps[2].get("start_line") == 3
    assert deps[2].get("source_code_snippet") == '#include "header.h" // Local header include'

async def test_parse_header_file(parser: CParser, tmp_path: Path):
    """Test parsing header.h from test_data."""
    test_file = TEST_DATA_DIR / "header.h"
    results = await run_parser_and_save_output(parser, test_file, tmp_path)

    assert len(results) > 0, "Expected DataPoints from non-empty header file"
    payloads = [dp.payload for dp in results]

    # Check for TextChunks
    chunks = [p for p in payloads if p.get("type") == "TextChunk"]
    assert len(chunks) >= 1, "Expected at least one TextChunk"

    # Check for CodeEntity (TypeDefinition - via typedef struct)
    typedefs = [p for p in payloads if p.get("type") == "TypeDefinition"]
    assert len(typedefs) == 1, "Expected one TypeDefinition for Point"
    typedef_point = typedefs[0]
    assert typedef_point.get("name") == "Point"
    assert typedef_point.get("start_line") == 5, "Incorrect start line for typedef Point"
    assert typedef_point.get("end_line") == 8, "Incorrect end line for typedef Point"
    assert "typedef struct {" in typedef_point.get("source_code_snippet","")
    assert "} Point;" in typedef_point.get("source_code_snippet","")

    # Check for Absence of Function Definitions (Prototypes are not definitions)
    # The current C query only finds function_definition nodes.
    funcs = [p for p in payloads if p.get("type") == "FunctionDefinition"]
    assert len(funcs) == 0, "Parser should not currently find function prototypes/declarations as definitions"

    # Check for Absence of Dependencies (no #include in this header)
    deps = [p for p in payloads if p.get("type") == "Dependency"]
    assert len(deps) == 0, "No include dependencies expected in header.h"

async def test_parse_file_with_only_directives(parser: CParser, tmp_path: Path):
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
    results = await run_parser_and_save_output(parser, test_file, tmp_path)

    assert len(results) > 0, "Expected DataPoints from directives file"
    payloads = [dp.payload for dp in results]

    # Expect TextChunks
    chunks = [p for p in payloads if p.get("type") == "TextChunk"]
    assert len(chunks) >= 1, "Expected at least one chunk"

    # Expect the include Dependency
    deps = [p for p in payloads if p.get("type") == "Dependency"]
    assert len(deps) == 1, "Expected one include dependency"
    assert deps[0].get("target_module") == "stddef.h"
    assert deps[0].get("start_line") == 7
    assert deps[0].get("source_code_snippet") == "#include <stddef.h>"

    # Expect no Function, Struct, Typedef etc. defined by current queries
    entity_types = {p.get("type") for p in payloads}
    assert "FunctionDefinition" not in entity_types
    assert "StructDefinition" not in entity_types
    assert "TypeDefinition" not in entity_types
    assert "EnumDefinition" not in entity_types
    assert "UnionDefinition" not in entity_types
