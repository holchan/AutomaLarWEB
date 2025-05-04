# .roo/cognee/tests/parser/parsers/test_rust_parser.py
import pytest
import asyncio
import os
from pathlib import Path
from typing import List, TYPE_CHECKING

pytestmark = pytest.mark.asyncio

try:
    from src.parser.entities import TextChunk, CodeEntity, Relationship, ParserOutput
    from src.parser.parsers.rust_parser import RustParser
except ImportError as e:
    pytest.skip(f"Skipping Rust parser tests: Failed to import dependencies - {e}", allow_module_level=True)

if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser
    from pydantic import BaseModel

TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "rust"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

@pytest.fixture(scope="module")
def parser() -> RustParser:
    """Provides a RustParser instance, skipping if language not loaded."""
    try:
        from src.parser.parsers.treesitter_setup import get_language
        if get_language("rust") is None:
            pytest.skip("Rust tree-sitter language not loaded or available.", allow_module_level=True)
    except ImportError as e:
        pytest.skip(f"Tree-sitter setup or core library not available: {e}", allow_module_level=True)
    return RustParser()

from ..conftest import run_parser_and_save_output

async def test_parse_empty_rs_file(parser: RustParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing an empty Rust file."""
    empty_file = tmp_path / "empty.rs"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0, "Empty .rs file should yield no DataPoints"

async def test_parse_utils_file(parser: RustParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing utils.rs which contains only a simple function."""
    test_file = TEST_DATA_DIR / "utils.rs"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(chunks) >= 1

    funcs = [e for e in entities if e.type == "FunctionDefinition"]
    assert len(funcs) == 1
    func = funcs[0]
    assert func.type == "FunctionDefinition"
    assert ":FunctionDefinition:helper:" in func.id
    assert func.start_line == 1
    assert func.end_line == 3
    assert "pub fn helper()" in func.snippet_content

    other_entities = [e for e in entities if e.type != "FunctionDefinition"]
    assert len(other_entities) == 0

    assert len(rels) == len(chunks) + len(entities)
    assert all(r.type in ["CONTAINS_CHUNK", "CONTAINS_ENTITY"] for r in rels)


async def test_parse_simple_mod_file(parser: RustParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing simple_mod.rs from test_data."""
    test_file = TEST_DATA_DIR / "simple_mod.rs"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    chunks = [dp for dp in results if isinstance(dp, TextChunk)]
    entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(chunks) >= 1

    entity_map = {}
    for e in entities:
        if e.type not in entity_map: entity_map[e.type] = []
        entity_map[e.type].append(e)

    assert len(entity_map.get("ModuleDefinition", [])) == 1
    assert ":ModuleDefinition:utils:" in entity_map["ModuleDefinition"][0].id

    assert len(entity_map.get("StructDefinition", [])) == 1
    assert ":StructDefinition:Point:" in entity_map["StructDefinition"][0].id

    assert len(entity_map.get("EnumDefinition", [])) == 1
    assert ":EnumDefinition:Status:" in entity_map["EnumDefinition"][0].id

    assert len(entity_map.get("TraitDefinition", [])) == 1
    assert ":TraitDefinition:Summary:" in entity_map["TraitDefinition"][0].id

    assert len(entity_map.get("Implementation", [])) == 2
    impl_names = sorted([impl.id.split(":")[-2] for impl in entity_map["Implementation"] if impl.id.count(":") >= 3])
    assert "Point"

    assert len(entity_map.get("FunctionDefinition", [])) == 5
    func_names = {f.id.split(":")[-2] for f in entity_map["FunctionDefinition"] if f.id.count(":") >= 3}
    assert func_names == {"new", "distance_from_origin", "summarize", "process_point", "main"}

    assert len(entity_map.get("MacroDefinition", [])) == 1
    assert ":MacroDefinition:create_map:" in entity_map["MacroDefinition"][0].id

    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) == 2
    targets = sorted([r.target_id for r in import_rels])
    assert targets == ["crate::utils::helper", "std::collections::HashMap"]

    implements_trait_rels = [r for r in rels if r.type == "IMPLEMENTS_TRAIT"]
    assert len(implements_trait_rels) == 1
    assert implements_trait_rels[0].source_id == entity_map["Implementation"][1].id
    assert implements_trait_rels[0].target_id == "Summary"
