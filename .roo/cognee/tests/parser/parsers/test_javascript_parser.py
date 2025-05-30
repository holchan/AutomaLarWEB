import pytest
import asyncio
from pathlib import Path
from typing import List, Union, TYPE_CHECKING

from pydantic import BaseModel

pytestmark = pytest.mark.asyncio

try:
    from src.parser.entities import TextChunk, CodeEntity, Relationship, ParserOutput
    from src.parser.parsers.javascript_parser import JavascriptParser
    from src.parser.parsers.treesitter_setup import get_language
except ImportError as e:
    pytest.skip(f"Skipping JS parser tests: Failed to import dependencies - {e}", allow_module_level=True)

if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser


TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "javascript"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

@pytest.fixture(scope="module")
def parser() -> JavascriptParser:
    if get_language("javascript") is None:
        pytest.skip("JavaScript tree-sitter language not loaded or available.", allow_module_level=True)
    return JavascriptParser()

from ..conftest import run_parser_and_save_output

async def test_parse_empty_js_file(parser: JavascriptParser, tmp_path: Path, run_parser_and_save_output):
    empty_file = tmp_path / "empty.js"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0

async def test_parse_simple_function_file(parser: JavascriptParser, tmp_path: Path, run_parser_and_save_output):
    test_file = TEST_DATA_DIR / "simple_function.js"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)
    assert len(results) > 0
    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    code_entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]
    assert len(chunks) >= 1
    assert chunks[0].chunk_content.strip().startswith("// Simple JS functions")
    funcs = [ce for ce in code_entities if ce.type == "FunctionDefinition"]
    assert len(funcs) >= 2
    func_add = next((f for f in funcs if ":FunctionDefinition:add:" in f.id), None)
    assert func_add is not None and "function add(a, b)" in func_add.snippet_content
    func_multiply = next((f for f in funcs if ":FunctionDefinition:multiply:" in f.id), None)
    assert func_multiply is not None and "const multiply = (a, b) =>" in func_multiply.snippet_content
    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) == 2
    import_targets = {r.target_id for r in import_rels}
    assert "path" in import_targets and "./utils" in import_targets

async def test_parse_class_with_imports_file(parser: JavascriptParser, tmp_path: Path, run_parser_and_save_output):
    test_file = TEST_DATA_DIR / "class_with_imports.js"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)
    assert len(results) > 0
    code_entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]
    classes = [ce for ce in code_entities if ce.type == "ClassDefinition"]
    assert len(classes) == 1
    assert next((c for c in classes if ":ClassDefinition:FileManager:" in c.id), None) is not None
    funcs = [ce for ce in code_entities if ce.type == "FunctionDefinition"]
    assert len(funcs) == 3
    func_ids_components = {tuple(f.id.split(":")[2:4]) for f in funcs}
    assert ("FunctionDefinition", "constructor") in func_ids_components
    assert ("FunctionDefinition", "readFile") in func_ids_components
    assert ("FunctionDefinition", "listDirectory") in func_ids_components
    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) >= 2
    import_targets = {r.target_id for r in import_rels}
    assert "fs/promises" in import_targets and "path" in import_targets

async def test_parse_file_with_jsx(parser: JavascriptParser, tmp_path: Path, run_parser_and_save_output):
    content = "import React from 'react';\nfunction MyComponent({ name }) {\n    return (<div className=\"greeting\"><h1>Hello, {name}!</h1></div>);\n}\nexport default MyComponent;"
    test_file = tmp_path / "component.jsx"
    test_file.write_text(content, encoding="utf-8")
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)
    assert len(results) > 0
    code_entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]
    funcs = [ce for ce in code_entities if ce.type == "FunctionDefinition"]
    assert len(funcs) == 1
    func_my_component = next((f for f in funcs if ":FunctionDefinition:MyComponent:" in f.id), None)
    assert func_my_component is not None
    assert "<div className=\"greeting\">" in func_my_component.snippet_content
    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) == 1 and import_rels[0].target_id == "react"
