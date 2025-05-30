import pytest
import asyncio
from pathlib import Path
from typing import List, Union, TYPE_CHECKING

from pydantic import BaseModel

pytestmark = pytest.mark.asyncio

try:
    from src.parser.entities import TextChunk, CodeEntity, Relationship, ParserOutput
    from src.parser.parsers.typescript_parser import TypescriptParser
    from src.parser.parsers.treesitter_setup import get_language
except ImportError as e:
    pytest.skip(f"Skipping TS parser tests: Failed to import dependencies - {e}", allow_module_level=True)

if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser


TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "typescript"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

@pytest.fixture(scope="module")
def parser() -> TypescriptParser:
    if get_language("typescript") is None:
        pytest.skip("TypeScript tree-sitter language not loaded or available.", allow_module_level=True)
    return TypescriptParser()

from ..conftest import run_parser_and_save_output

async def test_parse_empty_ts_file(parser: TypescriptParser, tmp_path: Path, run_parser_and_save_output):
    empty_file = tmp_path / "empty.ts"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0

async def test_parse_simple_function_file(parser: TypescriptParser, tmp_path: Path, run_parser_and_save_output):
    test_file = TEST_DATA_DIR / "simple_function.ts"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)
    assert len(results) > 0
    code_entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]
    interfaces = [e for e in code_entities if e.type == "InterfaceDefinition"]
    assert len(interfaces) == 1
    assert next((i for i in interfaces if ":InterfaceDefinition:User:" in i.id and "export interface User" in i.snippet_content), None) is not None
    types = [e for e in code_entities if e.type == "TypeDefinition"]
    assert len(types) == 1
    assert next((t for t in types if ":TypeDefinition:Result:" in t.id and "export type Result<T>" in t.snippet_content), None) is not None
    funcs = [e for e in code_entities if e.type == "FunctionDefinition"]
    assert len(funcs) == 2
    assert next((f for f in funcs if ":FunctionDefinition:processUser:" in f.id and "function processUser(user: User, logger: Logger): Result<string>" in f.snippet_content), None) is not None
    assert next((f for f in funcs if ":FunctionDefinition:formatResult:" in f.id and "const formatResult = <T>(result: Result<T>): string =>" in f.snippet_content), None) is not None
    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) == 1 and import_rels[0].target_id == "./logger"

async def test_parse_class_with_interfaces_file(parser: TypescriptParser, tmp_path: Path, run_parser_and_save_output):
    test_file = TEST_DATA_DIR / "class_with_interfaces.tsx"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)
    assert len(results) > 0
    code_entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]
    interfaces = [e for e in code_entities if e.type == "InterfaceDefinition"]
    assert len(interfaces) == 2
    assert next((i for i in interfaces if ":InterfaceDefinition:GreeterProps:" in i.id), None) is not None
    assert next((i for i in interfaces if ":InterfaceDefinition:ComponentState:" in i.id), None) is not None
    classes = [e for e in code_entities if e.type == "ClassDefinition"]
    assert len(classes) == 1
    cls_greeter_comp = next((c for c in classes if ":ClassDefinition:GreeterComponent:" in c.id), None)
    assert cls_greeter_comp is not None
    extends_rels = [r for r in rels if r.type == "EXTENDS" and r.source_id == cls_greeter_comp.id]
    assert len(extends_rels) >= 1
    funcs = [e for e in code_entities if e.type == "FunctionDefinition"]
    assert len(funcs) >= 4
    func_ids_components = {tuple(f.id.split(":")[2:4]) for f in funcs}
    assert ("FunctionDefinition", "componentDidMount") in func_ids_components
    assert ("FunctionDefinition", "componentWillUnmount") in func_ids_components
    assert ("FunctionDefinition", "render") in func_ids_components
    assert ("FunctionDefinition", "FunctionalGreeter") in func_ids_components
    render_func = next((f for f in funcs if ":FunctionDefinition:render:" in f.id), None)
    assert render_func is not None and "<h1>Hello, {name}!</h1>" in render_func.snippet_content
    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) >= 1 and "react" in {r.target_id for r in import_rels}
