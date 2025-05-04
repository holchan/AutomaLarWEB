# .roo/cognee/tests/parser/parsers/test_cpp_parser.py
import pytest
import asyncio
import os
from pathlib import Path
from typing import List, TYPE_CHECKING

pytestmark = pytest.mark.asyncio

try:
    from src.parser.entities import TextChunk, CodeEntity, Relationship, ParserOutput
    from src.parser.parsers.cpp_parser import CppParser
except ImportError as e:
    pytest.skip(f"Skipping C++ parser tests: Failed to import dependencies - {e}", allow_module_level=True)

if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser
    from pydantic import BaseModel

TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "cpp"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

@pytest.fixture(scope="module")
def parser() -> CppParser:
    """Provides a CppParser instance, skipping if language not loaded."""
    try:
        from src.parser.parsers.treesitter_setup import get_language
        if get_language("cpp") is None:
            pytest.skip("C++ tree-sitter language not loaded or available.", allow_module_level=True)
    except ImportError as e:
        pytest.skip(f"Tree-sitter setup or core library not available: {e}", allow_module_level=True)
    return CppParser()

from ..conftest import run_parser_and_save_output

async def test_parse_empty_cpp_file(parser: CppParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing an empty C++ file."""
    empty_file = tmp_path / "empty.cpp"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0, "Empty .cpp file should yield no DataPoints"

async def test_parse_empty_hpp_file(parser: CppParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing an empty C++ header file."""
    empty_file = tmp_path / "empty.hpp"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0, "Empty .hpp file should yield no DataPoints"

async def test_parse_simple_class_file(parser: CppParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing simple_class.cpp from test_data."""
    test_file = TEST_DATA_DIR / "simple_class.cpp"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(chunks) >= 1

    namespaces = [e for e in entities if e.type == "NamespaceDefinition"]
    assert len(namespaces) == 1
    assert namespaces[0].type == "NamespaceDefinition"
    assert ":NamespaceDefinition:Processing:" in namespaces[0].id
    assert namespaces[0].start_line == 10
    assert namespaces[0].end_line == 24

    funcs = [e for e in entities if e.type == "FunctionDefinition"]
    assert len(funcs) == 3
    func_map = {f.id.split(":")[-2]: f for f in funcs if f.id.count(":") >= 3}

    assert "processVector" in func_map
    assert func_map["processVector"].start_line == 13
    assert func_map["processVector"].end_line == 18
    assert "void MyDataProcessor::processVector" in func_map["processVector"].snippet_content

    assert "helperFunction" in func_map
    assert func_map["helperFunction"].start_line == 21
    assert func_map["helperFunction"].end_line == 23

    assert "main" in func_map
    assert func_map["main"].start_line == 28
    assert func_map["main"].end_line == 35

    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) == 5
    targets = sorted([r.target_id for r in import_rels])
    assert targets == ["iostream", "my_class.hpp", "std", "string", "vector"]

async def test_parse_header_file(parser: CppParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing my_class.hpp from test_data."""
    test_file = TEST_DATA_DIR / "my_class.hpp"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    namespaces = [e for e in entities if e.type == "NamespaceDefinition"]
    assert len(namespaces) == 1
    assert ":NamespaceDefinition:Processing:" in namespaces[0].id

    classes = [e for e in entities if e.type == "ClassDefinition"]
    assert len(classes) == 1
    cls = classes[0]
    assert cls.type == "ClassDefinition"
    assert ":ClassDefinition:MyDataProcessor:" in cls.id
    assert cls.start_line == 9
    assert cls.end_line == 22

    funcs = [e for e in entities if e.type == "FunctionDefinition"]
    assert len(funcs) >= 5
    func_map = {f.id.split(":")[-2]: f for f in funcs if f.id.count(":") >= 3}
    assert "MyDataProcessor" in func_map
    assert "~MyDataProcessor" in func_map
    assert "processVector" in func_map
    assert "identity" in func_map
    assert "helperFunction" in func_map

    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) == 2
    targets = sorted([r.target_id for r in import_rels])
    assert targets == ["string", "vector"]

async def test_parse_file_with_enums_structs(parser: CppParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing C++ file with enums and structs within a namespace."""
    content = """
#include <string> // Include dep

namespace DataTypes { // Namespace def

    struct Point { // Struct def
        int x, y;
    };

    enum Status { // Enum def
        Active,
        Inactive
    };

    enum class ErrorCode { // Enum class def
        None = 0,
        IOError,
        NetworkError
    };
} // End namespace

struct GlobalStruct { float val; }; // Global struct def
"""
    test_file = tmp_path / "types.cpp"
    test_file.write_text(content, encoding="utf-8")
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)
    assert len(results) > 0

    entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    namespaces = [e for e in entities if e.type == "NamespaceDefinition"]
    assert len(namespaces) == 1
    assert ":NamespaceDefinition:DataTypes:" in namespaces[0].id

    structs = [e for e in entities if e.type == "StructDefinition"]
    assert len(structs) == 2
    struct_map = {s.id.split(":")[-2]: s for s in structs if s.id.count(":") >= 3}
    assert "Point" in struct_map
    assert struct_map["Point"].start_line == 4
    assert "GlobalStruct" in struct_map
    assert struct_map["GlobalStruct"].start_line == 19

    enums = [e for e in entities if e.type == "EnumDefinition"]
    assert len(enums) == 2
    enum_map = {e.id.split(":")[-2]: e for e in enums if e.id.count(":") >= 3}
    assert "Status" in enum_map
    assert enum_map["Status"].start_line == 8
    assert "ErrorCode" in enum_map
    assert enum_map["ErrorCode"].start_line == 13

    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) == 1
    assert import_rels[0].target_id == "string"
