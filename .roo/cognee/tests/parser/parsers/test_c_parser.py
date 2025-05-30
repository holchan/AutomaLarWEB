import pytest
import asyncio
from pathlib import Path
from typing import List, Union, TYPE_CHECKING

from pydantic import BaseModel

pytestmark = pytest.mark.asyncio

try:
    from src.parser.entities import TextChunk, CodeEntity, Relationship, ParserOutput
    from src.parser.parsers.c_parser import CParser
    from src.parser.parsers.treesitter_setup import get_language
except ImportError as e:
    pytest.skip(f"Skipping C parser tests: Failed to import dependencies - {e}", allow_module_level=True)

if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser


TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "c"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

@pytest.fixture(scope="module")
def parser() -> CParser:
    if get_language("c") is None:
        pytest.skip("C tree-sitter language not loaded or available.", allow_module_level=True)
    return CParser()

from ..conftest import run_parser_and_save_output

async def test_parse_empty_c_file(parser: CParser, tmp_path: Path, run_parser_and_save_output):
    empty_file = tmp_path / "empty.c"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0

async def test_parse_empty_h_file(parser: CParser, tmp_path: Path, run_parser_and_save_output):
    empty_file = tmp_path / "empty.h"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0

async def test_parse_simple_function_file(parser: CParser, tmp_path: Path, run_parser_and_save_output):
    test_file = TEST_DATA_DIR / "simple_function.c"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)
    assert len(results) > 0
    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]
    assert len(chunks) >= 1
    funcs = [e for e in entities if e.type == "FunctionDefinition"]
    assert len(funcs) == 2
    func_add = next((f for f in funcs if ":FunctionDefinition:add:" in f.id), None)
    assert func_add is not None
    assert func_add.type == "FunctionDefinition"
    assert "int add(int a, int b)" in func_add.snippet_content
    func_main = next((f for f in funcs if ":FunctionDefinition:main:" in f.id), None)
    assert func_main is not None
    assert func_main.type == "FunctionDefinition"
    assert "int main(int argc, char *argv[])" in func_main.snippet_content
    typedefs = [e for e in entities if e.type == "TypeDefinition"]
    assert len(typedefs) == 1
    typedef_record = next((td for td in typedefs if ":TypeDefinition:Record:" in td.id), None)
    assert typedef_record is not None
    assert typedef_record.type == "TypeDefinition"
    assert "typedef struct {" in typedef_record.snippet_content
    assert "} Record;" in typedef_record.snippet_content
    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) == 3
    targets = sorted([r.target_id for r in import_rels])
    assert targets == ["header.h", "stdio.h", "stdlib.h"]

async def test_parse_header_file(parser: CParser, tmp_path: Path, run_parser_and_save_output):
    test_file = TEST_DATA_DIR / "header.h"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)
    assert len(results) > 0
    entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]
    typedefs = [e for e in entities if e.type == "TypeDefinition"]
    assert len(typedefs) == 1
    typedef_point = next((td for td in typedefs if ":TypeDefinition:Point:" in td.id), None)
    assert typedef_point is not None
    assert "typedef struct {" in typedef_point.snippet_content
    assert "} Point;" in typedef_point.snippet_content
    funcs = [e for e in entities if e.type == "FunctionDefinition"]
    assert len(funcs) == 0
    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) == 0

async def test_parse_file_with_only_directives(parser: CParser, tmp_path: Path, run_parser_and_save_output):
    content = """
#ifndef MY_GUARD_H
#define MY_GUARD_H
#define MY_MACRO(x) ((x) * (x))
#define ANOTHER_MACRO 123
#include <stddef.h>
#endif
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
