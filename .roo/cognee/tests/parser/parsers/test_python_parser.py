import pytest
import asyncio
from pathlib import Path
from typing import List, Union, TYPE_CHECKING

from pydantic import BaseModel

pytestmark = pytest.mark.asyncio

try:
    from src.parser.entities import TextChunk, CodeEntity, Relationship
    ParserOutput = Union[TextChunk, CodeEntity, Relationship]
    from src.parser.parsers.python_parser import PythonParser
except ImportError as e:
    pytest.skip(f"Skipping Python parser tests: Failed to import dependencies - {e}", allow_module_level=True)

if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser


TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "python"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

@pytest.fixture(scope="module")
def parser() -> PythonParser:
    try:
        from src.parser.parsers.treesitter_setup import get_language
        if get_language("python") is None:
            pytest.skip("Python tree-sitter language not loaded or available.", allow_module_level=True)
    except ImportError as e:
        pytest.skip(f"Tree-sitter setup or core library not available: {e}", allow_module_level=True)
    return PythonParser()

from ..conftest import run_parser_and_save_output

async def test_parse_empty_file(parser: PythonParser, tmp_path: Path, run_parser_and_save_output):
    empty_file = tmp_path / "empty.py"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0

async def test_parse_simple_function_file(parser: PythonParser, tmp_path: Path, run_parser_and_save_output):
    test_file = TEST_DATA_DIR / "simple_function.py"

    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    code_entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    relationships = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(chunks) >= 1
    first_chunk = chunks[0]
    assert isinstance(first_chunk.id, str) and first_chunk.id.endswith(":0")
    assert first_chunk.chunk_content.strip().startswith("# A simple function example")
    assert isinstance(first_chunk.start_line, int)
    assert isinstance(first_chunk.end_line, int)

    funcs = [ce for ce in code_entities if ce.type == "FunctionDefinition"]
    assert len(funcs) == 1

    func_process_data = None
    for f in funcs:
        if ":FunctionDefinition:process_data:" in f.id:
            func_process_data = f
            break

    assert func_process_data is not None, "Function 'process_data' not found"
    assert func_process_data.type == "FunctionDefinition"
    assert "def process_data(file_path: str) -> bool:" in func_process_data.snippet_content
    assert '"""' in func_process_data.snippet_content

    import_rels = [r for r in relationships if r.type == "IMPORTS"]
    assert len(import_rels) == 2

    import_targets = {r.target_id for r in import_rels}
    assert "os" in import_targets
    assert "logging" in import_targets

    file_id_from_chunk = first_chunk.id.rsplit(":",1)[0] if ":" in first_chunk.id else first_chunk.id
    for r in import_rels:
        assert r.source_id == file_id_from_chunk

    contains_chunk_rels = [r for r in relationships if r.type == "CONTAINS_CHUNK"]
    assert len(contains_chunk_rels) == len(chunks)
    for r_cc, chunk in zip(contains_chunk_rels, chunks):
        assert r_cc.source_id == file_id_from_chunk
        assert r_cc.target_id == chunk.id

    contains_entity_rels = [r for r in relationships if r.type == "CONTAINS_ENTITY"]
    assert len(contains_entity_rels) == len(funcs)
    for r_ce in contains_entity_rels:
        assert any(chunk.id == r_ce.source_id for chunk in chunks)
        assert any(func.id == r_ce.target_id for func in funcs)

async def test_parse_class_with_imports_file(parser: PythonParser, tmp_path: Path, run_parser_and_save_output):
    test_file = TEST_DATA_DIR / "class_with_imports.py"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    code_entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    relationships = [dp for dp in results if isinstance(dp, Relationship)]

    classes = [ce for ce in code_entities if ce.type == "ClassDefinition"]
    assert len(classes) == 1
    cls_data_processor = None
    for c in classes:
        if ":ClassDefinition:DataProcessor:" in c.id:
            cls_data_processor = c
            break
    assert cls_data_processor is not None
    assert cls_data_processor.type == "ClassDefinition"
    assert '"""Processes data asynchronously."""' in cls_data_processor.snippet_content

    funcs = [ce for ce in code_entities if ce.type == "FunctionDefinition"]
    assert len(funcs) == 4

    func_names_from_ids = set()
    for f in funcs:
        parts = f.id.split(":")
        if len(parts) >= 3 and parts[-3] == "FunctionDefinition":
            func_names_from_ids.add(parts[-2])

    assert "__init__" in func_names_from_ids
    assert "load_data" in func_names_from_ids
    assert "process" in func_names_from_ids
    assert "main" in func_names_from_ids

    import_rels = [r for r in relationships if r.type == "IMPORTS"]
    assert len(import_rels) >= 3
    import_targets = {r.target_id for r in import_rels}
    assert "asyncio" in import_targets
    assert any(imp_target.startswith("typing") for imp_target in import_targets)
    assert ".utils" in import_targets

async def test_parse_file_with_only_comments(parser: PythonParser, tmp_path: Path, run_parser_and_save_output):
    content = """
# This is a comment line.
# Another comment.

# More comments after whitespace.
"""
    test_file = tmp_path / "comments_only.py"
    test_file.write_text(content, encoding="utf-8")
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    if content.strip():
        assert len(results) >= 1
        chunks = [dp for dp in results if isinstance(dp, TextChunk)]
        relationships = [dp for dp in results if isinstance(dp, Relationship)]
        code_entities = [dp for dp in results if isinstance(dp, CodeEntity)]

        assert len(chunks) >= 1
        assert len(code_entities) == 0
        assert len(relationships) == len(chunks)
        assert all(r.type == "CONTAINS_CHUNK" for r in relationships)

        full_chunked_text = "".join(c.chunk_content for c in chunks)
        assert "# This is a comment line." in full_chunked_text
    else:
        assert len(results) == 0
