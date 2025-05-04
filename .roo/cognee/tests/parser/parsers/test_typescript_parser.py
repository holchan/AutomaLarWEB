# .roo/cognee/tests/parser/parsers/test_typescript_parser.py
import pytest
import asyncio
import os
from pathlib import Path
from typing import List, TYPE_CHECKING

pytestmark = pytest.mark.asyncio

try:
    from src.parser.entities import TextChunk, CodeEntity, Relationship, ParserOutput
    from src.parser.parsers.typescript_parser import TypescriptParser
except ImportError as e:
    pytest.skip(f"Skipping TS parser tests: Failed to import dependencies - {e}", allow_module_level=True)

if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser
    from pydantic import BaseModel

TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "typescript"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

from ..conftest import run_parser_and_save_output

@pytest.fixture(scope="module")
def parser() -> TypescriptParser:
    """Provides a TypescriptParser instance, skipping if language not loaded."""
    try:
        from src.parser.parsers.treesitter_setup import get_language
        if get_language("typescript") is None:
            pytest.skip("TypeScript tree-sitter language not loaded or available.", allow_module_level=True)
    except ImportError as e:
        pytest.skip(f"Tree-sitter setup or core library not available: {e}", allow_module_level=True)
    return TypescriptParser()

async def test_parse_empty_ts_file(parser: TypescriptParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing an empty TypeScript file."""
    empty_file = tmp_path / "empty.ts"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0, "Empty file should yield no DataPoints"

async def test_parse_simple_function_file(parser: TypescriptParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing simple_function.ts from test_data."""
    test_file = TEST_DATA_DIR / "simple_function.ts"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(chunks) >= 1
    assert chunks[0].chunk_content.strip().startswith("// Simple TS types and functions")

    interfaces = [e for e in entities if e.type == "InterfaceDefinition"]
    assert len(interfaces) == 1
    iface = interfaces[0]
    assert iface.type == "InterfaceDefinition"
    assert ":InterfaceDefinition:User:" in iface.id
    assert iface.start_line == 4
    assert iface.end_line == 8
    assert "export interface User" in iface.snippet_content

    types = [e for e in entities if e.type == "TypeDefinition"]
    assert len(types) == 1
    type_alias = types[0]
    assert type_alias.type == "TypeDefinition"
    assert ":TypeDefinition:Result:" in type_alias.id
    assert type_alias.start_line == 10
    assert type_alias.end_line == 12
    assert "export type Result<T>" in type_alias.snippet_content

    funcs = [e for e in entities if e.type == "FunctionDefinition"]
    assert len(funcs) == 2
    func_map = {f.id.split(":")[-2]: f for f in funcs if f.id.count(":") >= 3}

    assert "processUser" in func_map
    assert func_map["processUser"].start_line == 14
    assert func_map["processUser"].end_line == 19
    assert "function processUser(user: User, logger: Logger): Result<string>" in func_map["processUser"].snippet_content

    assert "formatResult" in func_map
    assert func_map["formatResult"].start_line == 21
    assert func_map["formatResult"].end_line == 23
    assert "const formatResult = <T>(result: Result<T>): string =>" in func_map["formatResult"].snippet_content

    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) == 1
    assert import_rels[0].target_id == "./logger"

async def test_parse_class_with_interfaces_file(parser: TypescriptParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing class_with_interfaces.tsx from test_data."""
    test_file = TEST_DATA_DIR / "class_with_interfaces.tsx"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    interfaces = [e for e in entities if e.type == "InterfaceDefinition"]
    assert len(interfaces) == 2
    iface_map = {i.id.split(":")[-2]: i for i in interfaces if i.id.count(":") >= 3}
    assert "GreeterProps" in iface_map
    assert "ComponentState" in iface_map
    assert iface_map["GreeterProps"].start_line == 4
    assert iface_map["ComponentState"].start_line == 8

    classes = [e for e in entities if e.type == "ClassDefinition"]
    assert len(classes) == 1
    cls = classes[0]
    assert cls.type == "ClassDefinition"
    assert ":ClassDefinition:GreeterComponent:" in cls.id
    assert cls.start_line == 10
    assert cls.end_line == 38

    extends_rels = [r for r in rels if r.type == "EXTENDS" and r.source_id == cls.id]
    implements_rels = [r for r in rels if r.type == "IMPLEMENTS" and r.source_id == cls.id]
    assert len(extends_rels) >= 1

    funcs = [e for e in entities if e.type == "FunctionDefinition"]
    assert len(funcs) >= 4
    func_map = {f.id.split(":")[-2]: f for f in funcs if f.id.count(":") >= 3}

    assert "componentDidMount" in func_map
    assert func_map["componentDidMount"].start_line == 19
    assert func_map["componentDidMount"].end_line == 23

    assert "componentWillUnmount" in func_map
    assert func_map["componentWillUnmount"].start_line == 25
    assert func_map["componentWillUnmount"].end_line == 29

    assert "render" in func_map
    assert func_map["render"].start_line == 31
    assert func_map["render"].end_line == 37
    assert "<h1>Hello, {name}!</h1>" in func_map["render"].snippet_content

    assert "FunctionalGreeter" in func_map
    assert func_map["FunctionalGreeter"].start_line == 40
    assert func_map["FunctionalGreeter"].end_line == 45

    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) == 2
    import_targets = {r.target_id for r in import_rels}
    assert "react" in import_targets
