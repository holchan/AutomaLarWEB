import pytest
import asyncio
from pathlib import Path
from typing import List, Union, TYPE_CHECKING

from pydantic import BaseModel

pytestmark = pytest.mark.asyncio

try:
    from src.parser.entities import TextChunk, CodeEntity, Relationship
    ParserOutput = Union[TextChunk, CodeEntity, Relationship]
    from src.parser.parsers.rust_parser import RustParser
except ImportError as e:
    pytest.skip(f"Skipping Rust parser tests: Failed to import dependencies - {e}", allow_module_level=True)

if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser

TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "rust"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

@pytest.fixture(scope="module")
def parser() -> RustParser:
    try:
        from src.parser.parsers.treesitter_setup import get_language
        if get_language("rust") is None:
            pytest.skip("Rust tree-sitter language not loaded or available.", allow_module_level=True)
    except ImportError as e:
        pytest.skip(f"Tree-sitter setup or core library not available: {e}", allow_module_level=True)
    return RustParser()

from ..conftest import run_parser_and_save_output

async def test_parse_empty_rs_file(parser: RustParser, tmp_path: Path, run_parser_and_save_output):
    empty_file = tmp_path / "empty.rs"
    empty_file.touch()
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0

async def test_parse_utils_file(parser: RustParser, tmp_path: Path, run_parser_and_save_output):
    test_file = TEST_DATA_DIR / "utils.rs"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    code_entities = [dp for dp in results if isinstance(dp, CodeEntity)]

    funcs = [e for e in code_entities if e.type == "FunctionDefinition"]
    assert len(funcs) == 1
    func_helper = next((f for f in funcs if ":FunctionDefinition:helper:" in f.id), None)
    assert func_helper is not None
    assert func_helper.type == "FunctionDefinition"
    assert "pub fn helper()" in func_helper.snippet_content

    other_entities = [e for e in code_entities if e.type != "FunctionDefinition"]
    assert len(other_entities) == 0

async def test_parse_simple_mod_file(parser: RustParser, tmp_path: Path, run_parser_and_save_output):
    test_file = TEST_DATA_DIR / "simple_mod.rs"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    code_entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    rels = [dp for dp in results if isinstance(dp, Relationship)]

    entity_types_found = {e.type for e in code_entities}
    assert "ModuleDefinition" in entity_types_found
    assert "StructDefinition" in entity_types_found
    assert "EnumDefinition" in entity_types_found
    assert "TraitDefinition" in entity_types_found
    assert "Implementation" in entity_types_found
    assert "FunctionDefinition" in entity_types_found
    assert "MacroDefinition" in entity_types_found

    mod_utils = next((e for e in code_entities if e.type == "ModuleDefinition" and ":utils:" in e.id), None)
    assert mod_utils is not None

    struct_point = next((e for e in code_entities if e.type == "StructDefinition" and ":Point:" in e.id), None)
    assert struct_point is not None

    enum_status = next((e for e in code_entities if e.type == "EnumDefinition" and ":Status:" in e.id), None)
    assert enum_status is not None

    trait_summary = next((e for e in code_entities if e.type == "TraitDefinition" and ":Summary:" in e.id), None)
    assert trait_summary is not None

    impls = [e for e in code_entities if e.type == "Implementation"]
    assert len(impls) == 2
    impl_point_for_summary = next((impl for impl in impls if ":Implementation:Point:" in impl.id and "Summary" in impl.snippet_content), None)
    assert impl_point_for_summary is not None


    funcs = [e for e in code_entities if e.type == "FunctionDefinition"]
    assert len(funcs) == 5
    func_names_from_ids = set()
    for f in funcs:
        parts = f.id.split(":")
        if len(parts) >=3 and parts[-3] == "FunctionDefinition": func_names_from_ids.add(parts[-2])
    assert func_names_from_ids == {"new", "distance_from_origin", "summarize", "process_point", "main"}

    macro_create_map = next((e for e in code_entities if e.type == "MacroDefinition" and ":create_map:" in e.id), None)
    assert macro_create_map is not None

    import_rels = [r for r in rels if r.type == "IMPORTS"]
    assert len(import_rels) == 2
    targets = sorted([r.target_id for r in import_rels])
    assert targets == ["crate::utils::helper", "std::collections::HashMap"]

    implements_trait_rels = [r for r in rels if r.type == "IMPLEMENTS_TRAIT"]
    assert len(implements_trait_rels) == 1
    impl_node_id_for_summary_trait = None
    for impl_entity in impls:
        if ":Implementation:Point:" in impl_entity.id and "impl Summary for Point" in impl_entity.snippet_content:
            impl_node_id_for_summary_trait = impl_entity.id
            break
    assert impl_node_id_for_summary_trait is not None
    assert implements_trait_rels[0].source_id == impl_node_id_for_summary_trait
    assert implements_trait_rels[0].target_id == "Summary"
