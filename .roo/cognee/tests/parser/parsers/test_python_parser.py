# .roo/cognee/tests/parser/parsers/test_python_parser.py
import pytest
import asyncio
import os
from pathlib import Path
from typing import List, TYPE_CHECKING

try:
    from src.parser.entities import TextChunk, CodeEntity, Relationship, ParserOutput
    from src.parser.parsers.python_parser import PythonParser
except ImportError as e:
    pytest.skip(f"Skipping Python parser tests: Failed to import dependencies - {e}", allow_module_level=True)

if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser
    from pydantic import BaseModel

pytestmark = pytest.mark.asyncio

TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "python"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

@pytest.fixture(scope="module")
def parser() -> PythonParser:
    """Provides a PythonParser instance, skipping if language not loaded."""
    try:
        from src.parser.parsers.treesitter_setup import get_language
        if get_language("python") is None:
            pytest.skip("Python tree-sitter language not loaded or available.", allow_module_level=True)
    except ImportError as e:
        pytest.skip(f"Tree-sitter setup or core library not available: {e}", allow_module_level=True)
    return PythonParser()

from ..conftest import run_parser_and_save_output

async def test_parse_empty_file(parser: PythonParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing an empty Python file."""
    empty_file = tmp_path / "empty.py"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0, "Empty file should yield no DataPoints"

async def test_parse_simple_function_file(parser: PythonParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing simple_function.py from test_data."""
    test_file = TEST_DATA_DIR / "simple_function.py"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0, "Expected DataPoints from non-empty file"

    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    funcs = [dp for dp in results if isinstance(dp, CodeEntity) and dp.type == "FunctionDefinition"]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(chunks) >= 1, "Expected at least one TextChunk"
    chunk0 = chunks[0]
    assert isinstance(chunk0.id, str) and chunk0.id.endswith(":0"), "Chunk ID format/index error"
    assert chunk0.chunk_content.strip().startswith("# A simple function example"), "First chunk content mismatch"
    assert chunk0.start_line is not None and chunk0.end_line is not None

    assert len(funcs) == 1, "Expected exactly one function definition"
    func = funcs[0]
    assert isinstance(func.id, str) and ":FunctionDefinition:process_data:0" in func.id, "Function ID format/name error"
    assert func.type == "FunctionDefinition"
    assert "def process_data(file_path: str) -> bool:" in func.snippet_content, "Function signature mismatch"
    assert '"""' in func.snippet_content, "Docstring seems missing from snippet"

    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) == 2, "Expected two IMPORTS relationships"
    import_rels.sort(key=lambda r: r.source_id + r.target_id)

    rel_os = next(r for r in import_rels if r.target_id == "os")
    rel_log = next(r for r in import_rels if r.target_id == "logging")

    assert rel_os.source_id.startswith("test_file_id_"), "Import source ID error"
    assert rel_os.target_id == "os"

    assert rel_log.source_id.startswith("test_file_id_"), "Import source ID error"
    assert rel_log.target_id == "logging"

    contains_chunk_rels = [r for r in rels if r.type == "CONTAINS_CHUNK"]
    assert len(contains_chunk_rels) == len(chunks), "Mismatch between chunks and CONTAINS_CHUNK relationships"
    assert all(r.target_id == c.id for r, c in zip(contains_chunk_rels, chunks)), "CONTAINS_CHUNK target mismatch"
    assert all(r.source_id == contains_chunk_rels[0].source_id for r in contains_chunk_rels), "CONTAINS_CHUNK source mismatch (should be file_id)"

    contains_entity_rels = [r for r in rels if r.type == "CONTAINS_ENTITY"]
    assert len(contains_entity_rels) == len(funcs), "Mismatch between funcs and CONTAINS_ENTITY relationships"
    assert contains_entity_rels[0].target_id == funcs[0].id, "CONTAINS_ENTITY target mismatch"
    assert contains_entity_rels[0].source_id == chunks[0].id, "CONTAINS_ENTITY source mismatch (should be chunk_id)"

async def test_parse_class_with_imports_file(parser: PythonParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing class_with_imports.py from test_data."""
    test_file = TEST_DATA_DIR / "class_with_imports.py"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    classes = [dp for dp in results if isinstance(dp, CodeEntity) and dp.type == "ClassDefinition"]
    funcs = [dp for dp in results if isinstance(dp, CodeEntity) and dp.type == "FunctionDefinition"]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(chunks) >= 1
    assert len(classes) == 1
    cls = classes[0]
    assert isinstance(cls.id, str) and ":ClassDefinition:DataProcessor:" in cls.id
    assert cls.type == "ClassDefinition"
    assert '"""Processes data asynchronously."""' in cls.snippet_content
    assert cls.start_line == 5
    assert cls.end_line == 28

    assert len(funcs) == 4
    func_map = {f.id.split(":")[-2]: f for f in funcs}

    assert "__init__" in func_map
    assert func_map["__init__"].start_line == 10
    assert func_map["__init__"].end_line == 12

    assert "load_data" in func_map
    assert func_map["load_data"].start_line == 14
    assert func_map["load_data"].end_line == 17

    assert "process" in func_map
    assert func_map["process"].start_line == 19
    assert func_map["process"].end_line == 28

    assert "main" in func_map
    assert func_map["main"].start_line == 31
    assert func_map["main"].end_line == 34

    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) >= 3, f"Expected at least 3 IMPORTS relationships, found {len(import_rels)}"
    import_targets = {r.target_id for r in import_rels}
    assert "asyncio" in import_targets
    assert "typing" in import_targets or "typing.List" in import_targets
    assert ".utils" in import_targets

async def test_parse_file_with_only_comments(parser: PythonParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing a file containing only comments and whitespace."""
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
        rels = [dp for dp in results if isinstance(dp, Relationship)]
        assert len(chunks) >= 1
        assert len(rels) == len(chunks)
        assert all(r.type == "CONTAINS_CHUNK" for r in rels)
        assert all(isinstance(dp, (TextChunk, Relationship)) for dp in results), "Only TextChunks and Relationships expected"
        full_text = "".join(c.chunk_content for c in chunks)
        assert "# This is a comment line." in full_text
        assert "# More comments after whitespace." in full_text
    else:
        assert len(results) == 0, "Should be empty if content was only whitespace"
