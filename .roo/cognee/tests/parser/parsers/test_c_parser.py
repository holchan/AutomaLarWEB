# .roo/cognee/tests/parser/parsers/test_c_parser.py
import pytest
import asyncio
import os
from pathlib import Path
from typing import List, TYPE_CHECKING

pytestmark = pytest.mark.asyncio

try:
    from src.parser.entities import TextChunk, CodeEntity, Relationship, ParserOutput
    from src.parser.parsers.c_parser import CParser
except ImportError as e:
    pytest.skip(f"Skipping C parser tests: Failed to import dependencies - {e}", allow_module_level=True)

if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser
    from pydantic import BaseModel

TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "c"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

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

from ..conftest import run_parser_and_save_output

async def test_parse_empty_c_file(parser: CParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing an empty C file."""
    empty_file = tmp_path / "empty.c"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0, "Empty .c file should yield no DataPoints"

async def test_parse_empty_h_file(parser: CParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing an empty C header file."""
    empty_file = tmp_path / "empty.h"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0, "Empty .h file should yield no DataPoints"

async def test_parse_simple_function_file(parser: CParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing simple_function.c from test_data."""
    test_file = TEST_DATA_DIR / "simple_function.c"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(chunks) >= 1

    funcs = [e for e in entities if e.type == "FunctionDefinition"]
    assert len(funcs) == 2
    func_map = {f.id.split(":")[-2]: f for f in funcs if f.id.count(":") >= 3}
    assert "add" in func_map
    assert func_map["add"].start_line == 9
    assert func_map["add"].end_line == 11
    assert "int add(int a, int b)" in func_map["add"].snippet_content

    assert "main" in func_map
    assert func_map["main"].start_line == 18
    assert func_map["main"].end_line == 35
    assert "int main(int argc, char *argv[])" in func_map["main"].snippet_content

    typedefs = [e for e in entities if e.type == "TypeDefinition"]
    assert len(typedefs) == 1
    assert typedefs[0].type == "TypeDefinition"
    assert ":TypeDefinition:Record:" in typedefs[0].id
    assert typedefs[0].start_line == 13
    assert typedefs[0].end_line == 16
    assert "typedef struct {" in typedefs[0].snippet_content
    assert "} Record;" in typedefs[0].snippet_content

    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) == 3
    targets = sorted([r.target_id for r in import_rels])
    assert targets == ["header.h", "stdio.h", "stdlib.h"]

async def test_parse_header_file(parser: CParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing header.h from test_data."""
    test_file = TEST_DATA_DIR / "header.h"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(chunks) >= 1

    typedefs = [e for e in entities if e.type == "TypeDefinition"]
    assert len(typedefs) == 1
    assert typedefs[0].type == "TypeDefinition"
    assert ":TypeDefinition:Point:" in typedefs[0].id
    assert typedefs[0].start_line == 5
    assert typedefs[0].end_line == 8
    assert "typedef struct {" in typedefs[0].snippet_content
    assert "} Point;" in typedefs[0].snippet_content

    funcs = [e for e in entities if e.type == "FunctionDefinition"]
    assert len(funcs) == 0

    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) == 0

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
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(chunks) >= 1
    assert len(entities) == 0

    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) == 1
    assert import_rels[0].target_id == "stddef.h"
