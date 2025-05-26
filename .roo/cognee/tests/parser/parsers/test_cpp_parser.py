import pytest
import asyncio
from pathlib import Path
from typing import List, Union, TYPE_CHECKING

from pydantic import BaseModel

pytestmark = pytest.mark.asyncio

try:
    from src.parser.entities import TextChunk, CodeEntity, Relationship
    ParserOutput = Union[TextChunk, CodeEntity, Relationship]
    from src.parser.parsers.cpp_parser import CppParser
except ImportError as e:
    pytest.skip(f"Skipping C++ parser tests: Failed to import dependencies - {e}", allow_module_level=True)

if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser

TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "cpp"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

@pytest.fixture(scope="module")
def parser() -> CppParser:
    try:
        from src.parser.parsers.treesitter_setup import get_language
        if get_language("cpp") is None:
            pytest.skip("C++ tree-sitter language not loaded or available.", allow_module_level=True)
    except ImportError as e:
        pytest.skip(f"Tree-sitter setup or core library not available: {e}", allow_module_level=True)
    return CppParser()

from ..conftest import run_parser_and_save_output

async def test_parse_empty_cpp_file(parser: CppParser, tmp_path: Path, run_parser_and_save_output):
    empty_file = tmp_path / "empty.cpp"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0

async def test_parse_empty_hpp_file(parser: CppParser, tmp_path: Path, run_parser_and_save_output):
    empty_file = tmp_path / "empty.hpp"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0

async def test_parse_simple_class_file(parser: CppParser, tmp_path: Path, run_parser_and_save_output):
    test_file = TEST_DATA_DIR / "simple_class.cpp"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    namespaces = [e for e in entities if e.type == "NamespaceDefinition"]
    assert len(namespaces) == 1
    ns_processing = next((ns for ns in namespaces if ":NamespaceDefinition:Processing:" in ns.id), None)
    assert ns_processing is not None
    assert ns_processing.type == "NamespaceDefinition"

    funcs = [e for e in entities if e.type == "FunctionDefinition"]
    assert len(funcs) == 3

    func_process_vector = next((f for f in funcs if ":FunctionDefinition:processVector:" in f.id), None)
    assert func_process_vector is not None
    assert "void MyDataProcessor::processVector" in func_process_vector.snippet_content

    func_helper = next((f for f in funcs if ":FunctionDefinition:helperFunction:" in f.id), None)
    assert func_helper is not None

    func_main = next((f for f in funcs if ":FunctionDefinition:main:" in f.id), None)
    assert func_main is not None

    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) >= 3
    targets = {r.target_id for r in import_rels}
    assert "iostream" in targets
    assert "my_class.hpp" in targets
    assert "std" in targets

async def test_parse_header_file(parser: CppParser, tmp_path: Path, run_parser_and_save_output):
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
    cls_my_data_proc = next((c for c in classes if ":ClassDefinition:MyDataProcessor:" in c.id), None)
    assert cls_my_data_proc is not None
    assert cls_my_data_proc.type == "ClassDefinition"

    funcs = [e for e in entities if e.type == "FunctionDefinition"]
    assert len(funcs) >= 5

    func_ids_components = {tuple(f.id.split(":")[2:4]) for f in funcs}
    assert ("FunctionDefinition", "MyDataProcessor") in func_ids_components
    assert ("FunctionDefinition", "~MyDataProcessor") in func_ids_components
    assert ("FunctionDefinition", "processVector") in func_ids_components
    assert ("FunctionDefinition", "identity") in func_ids_components
    assert ("FunctionDefinition", "helperFunction") in func_ids_components

    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) == 2
    targets = sorted([r.target_id for r in import_rels])
    assert targets == ["string", "vector"]

async def test_parse_file_with_enums_structs(parser: CppParser, tmp_path: Path, run_parser_and_save_output):
    content = """
#include <string>
namespace DataTypes {
    struct Point { int x, y; };
    enum Status { Active, Inactive };
    enum class ErrorCode { None = 0, IOError, NetworkError };
}
struct GlobalStruct { float val; };
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
    struct_ids_components = {tuple(s.id.split(":")[2:4]) for s in structs}
    assert ("StructDefinition", "Point") in struct_ids_components
    assert ("StructDefinition", "GlobalStruct") in struct_ids_components

    enums = [e for e in entities if e.type == "EnumDefinition"]
    assert len(enums) == 2
    enum_ids_components = {tuple(e.id.split(":")[2:4]) for e in enums}
    assert ("EnumDefinition", "Status") in enum_ids_components
    assert ("EnumDefinition", "ErrorCode") in enum_ids_components

    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) == 1
    assert import_rels[0].target_id == "string"
