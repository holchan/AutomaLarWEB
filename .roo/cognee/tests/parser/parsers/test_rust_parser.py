import pytest
import asyncio
import os
import json
import hashlib
from pathlib import Path
from typing import List, TYPE_CHECKING

# Use pytest-asyncio for async tests
pytestmark = pytest.mark.asyncio

# Import the parser and entity types
try:
    from src.parser.parsers.rust_parser import RustParser
    # Assuming Rust entities map to these generic types
    from src.parser.entities import DataPoint, TextChunk, CodeEntity, Dependency
except ImportError as e:
    # pytest.skip(f"Skipping Rust parser tests: Failed to import dependencies - {e}", allow_module_level=True)
    pass # Allow test collection even if imports fail, fixture will skip
# Avoid runtime import errors if BaseParser isn't directly used
if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser

# --- Test Configuration ---
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "rust"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

# Helper fixture `run_parser_and_save_output` is defined in tests/parser/conftest.py
# and injected by pytest into test functions that request it.
# --- Parser Fixture ---
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

# --- Test Cases ---

async def test_parse_empty_rs_file(parser: RustParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing an empty Rust file."""
    empty_file = tmp_path / "empty.rs"
    empty_file.touch()
    results = await run_parser_and_save_output(parser=parser, test_file_path=empty_file, output_dir=tmp_path)
    assert len(results) == 0, "Empty .rs file should yield no DataPoints"

async def test_parse_utils_file(parser: RustParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing utils.rs which contains only a simple function."""
    test_file = TEST_DATA_DIR / "utils.rs"
    results = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0, "Expected DataPoints from utils.rs"
    payloads = [dp.model_dump(mode='json') for dp in results]

    # Check for TextChunks
    chunks = [p for p in payloads if p.get("type") == "TextChunk"]
    assert len(chunks) >= 1, "Expected at least one TextChunk"

    # Check for CodeEntity (FunctionDefinition)
    funcs = [p for p in payloads if p.get("type") == "FunctionDefinition"]
    assert len(funcs) == 1, "Expected one function definition"
    func_meta = funcs[0].get("metadata", {})
    assert func_meta.get("name") == "helper"
    assert func_meta.get("start_line") == 1
    assert func_meta.get("end_line") == 3
    assert "pub fn helper()" in funcs[0].get("text_content","") # Check main content

    # Check no other code entities or dependencies
    other_entities = [p for p in payloads if p.get("type") not in ["TextChunk", "FunctionDefinition"]]
    assert len(other_entities) == 0, f"Found unexpected entities: {[e.get('type') for e in other_entities]}"

async def test_parse_simple_mod_file(parser: RustParser, tmp_path: Path, run_parser_and_save_output):
    """Test parsing simple_mod.rs from test_data."""
    test_file = TEST_DATA_DIR / "simple_mod.rs"
    results = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0, "Expected DataPoints from simple_mod.rs"
    payloads = [dp.model_dump(mode='json') for dp in results]
    payload_map = {p.get("type", "Unknown"): [] for p in payloads}
    for p in payloads:
        payload_map[p.get("type", "Unknown")].append(p)

    # Check counts of each entity type
    assert len(payload_map.get("TextChunk", [])) >= 1
    assert len(payload_map.get("ModuleDefinition", [])) == 1
    assert len(payload_map.get("StructDefinition", [])) == 1
    assert len(payload_map.get("EnumDefinition", [])) == 1
    assert len(payload_map.get("TraitDefinition", [])) == 1
    assert len(payload_map.get("Implementation", [])) == 2
    assert len(payload_map.get("FunctionDefinition", [])) == 5
    assert len(payload_map.get("MacroDefinition", [])) == 1
    assert len(payload_map.get("Dependency", [])) == 2

    # Verify ModuleDefinition
    mod = payload_map["ModuleDefinition"][0]
    mod_meta = mod.get("metadata", {})
    assert mod_meta.get("name") == "utils"
    assert mod_meta.get("start_line") == 4
    assert mod.get("text_content") == "mod utils; // Declare submodule" # Check main content

    # Verify StructDefinition
    struct = payload_map["StructDefinition"][0]
    struct_meta = struct.get("metadata", {})
    assert struct_meta.get("name") == "Point"
    assert struct_meta.get("start_line") == 6
    assert struct_meta.get("end_line") == 9

    # Verify EnumDefinition
    enum = payload_map["EnumDefinition"][0]
    enum_meta = enum.get("metadata", {})
    assert enum_meta.get("name") == "Status"
    assert enum_meta.get("start_line") == 19
    assert enum_meta.get("end_line") == 22

    # Verify TraitDefinition
    trait = payload_map["TraitDefinition"][0]
    trait_meta = trait.get("metadata", {})
    assert trait_meta.get("name") == "Summary"
    assert trait_meta.get("start_line") == 24
    assert trait_meta.get("end_line") == 26

    # Verify Implementations
    impls = payload_map["Implementation"]
    impls.sort(key=lambda i: i.get("metadata", {}).get("start_line", 0)) # Sort by line in metadata
    impl_point = impls[0] # impl Point { ... }
    impl_summary = impls[1] # impl Summary for Point { ... }
    impl_point_meta = impl_point.get("metadata", {})
    impl_summary_meta = impl_summary.get("metadata", {})
    assert impl_point_meta.get("name") == "Point" # Name is the type being implemented
    assert impl_point_meta.get("start_line") == 11
    assert impl_point_meta.get("end_line") == 17
    assert "impl Point {" in impl_point.get("text_content", "") # Check main content
    assert impl_summary_meta.get("name") == "Point"
    assert impl_summary_meta.get("start_line") == 28
    assert impl_summary_meta.get("end_line") == 32
    assert "impl Summary for Point {" in impl_summary.get("text_content", "") # Check main content

    # Verify FunctionDefinitions
    funcs = payload_map["FunctionDefinition"]
    func_map = {f.get("metadata", {}).get("name"): f for f in funcs}
    assert set(func_map.keys()) == {"new", "distance_from_origin", "summarize", "process_point", "main"}
    assert func_map["new"].get("metadata", {}).get("start_line") == 12
    assert func_map["distance_from_origin"].get("metadata", {}).get("start_line") == 15
    assert func_map["summarize"].get("metadata", {}).get("start_line") == 29 # Method inside trait impl
    assert func_map["process_point"].get("metadata", {}).get("start_line") == 35
    assert func_map["main"].get("metadata", {}).get("start_line") == 57

    # Verify MacroDefinition
    macro = payload_map["MacroDefinition"][0]
    macro_meta = macro.get("metadata", {})
    assert macro_meta.get("name") == "create_map"
    assert macro_meta.get("start_line") == 46
    assert macro_meta.get("end_line") == 55

    # Verify Dependencies (use statements)
    deps = payload_map["Dependency"]
    deps.sort(key=lambda d: d.get("metadata", {}).get("start_line", 0)) # Sort by line in metadata
    dep0_meta = deps[0].get("metadata", {})
    dep1_meta = deps[1].get("metadata", {})
    assert dep0_meta.get("target_module") == "std::collections::HashMap"
    assert dep0_meta.get("start_line") == 2
    assert deps[0].get("text_content") == "use std::collections::HashMap; // Standard library import" # Check main content
    assert dep1_meta.get("target_module") == "crate::utils::helper"
    assert dep1_meta.get("start_line") == 3
    assert deps[1].get("text_content") == "use crate::utils::helper; // Crate relative import" # Check main content
