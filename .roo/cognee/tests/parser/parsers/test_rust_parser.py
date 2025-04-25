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
    pytest.skip(f"Skipping Rust parser tests: Failed to import dependencies - {e}", allow_module_level=True)

# Avoid runtime import errors if BaseParser isn't directly used
if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser

# --- Test Configuration ---
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "rust"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

# --- Helper Function (Copied from previous step) ---
async def run_parser_and_save_output(
    parser: 'BaseParser',
    test_file_path: Path,
    output_dir: Path
) -> List['DataPoint']:
    """
    Runs the parser on a given file path, saves the payload results to a JSON
    file in output_dir, and returns the list of original DataPoint objects.
    """
    if not test_file_path.is_file():
        pytest.fail(f"Test input file not found: {test_file_path}")

    file_id_base = str(test_file_path.absolute())
    file_id = f"test_file_id_{hashlib.sha1(file_id_base.encode()).hexdigest()[:10]}"

    results_objects: List[DataPoint] = []
    results_payloads: List[dict] = []

    try:
        async for dp in parser.parse(file_path=str(test_file_path), file_id=file_id):
            results_objects.append(dp)
            if hasattr(dp, 'model_dump'):
                payload = dp.model_dump()
            elif hasattr(dp, 'payload'):
                payload = dp.payload
            else:
                payload = {"id": getattr(dp, 'id', 'unknown'), "type": "UnknownPayloadStructure"}
            results_payloads.append(payload)
    except Exception as e:
        print(f"\nERROR during parser execution for {test_file_path.name}: {e}")
        pytest.fail(f"Parser execution failed for {test_file_path.name}: {e}", pytrace=True)

    output_filename = output_dir / f"parsed_{test_file_path.stem}_output.json"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(results_payloads, f, indent=2, ensure_ascii=False, sort_keys=True)
        print(f"\n[Test Output] Saved parser results for '{test_file_path.name}' to: {output_filename}")
    except Exception as e:
        print(f"\n[Test Output] WARNING: Failed to save test output for {test_file_path.name}: {e}")

    return results_objects


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

async def test_parse_empty_rs_file(parser: RustParser, tmp_path: Path):
    """Test parsing an empty Rust file."""
    empty_file = tmp_path / "empty.rs"
    empty_file.touch()
    results = await run_parser_and_save_output(parser, empty_file, tmp_path)
    assert len(results) == 0, "Empty .rs file should yield no DataPoints"

async def test_parse_utils_file(parser: RustParser, tmp_path: Path):
    """Test parsing utils.rs which contains only a simple function."""
    test_file = TEST_DATA_DIR / "utils.rs"
    results = await run_parser_and_save_output(parser, test_file, tmp_path)

    assert len(results) > 0, "Expected DataPoints from utils.rs"
    payloads = [dp.payload for dp in results]

    # Check for TextChunks
    chunks = [p for p in payloads if p.get("type") == "TextChunk"]
    assert len(chunks) >= 1, "Expected at least one TextChunk"

    # Check for CodeEntity (FunctionDefinition)
    funcs = [p for p in payloads if p.get("type") == "FunctionDefinition"]
    assert len(funcs) == 1, "Expected one function definition"
    assert funcs[0].get("name") == "helper"
    assert funcs[0].get("start_line") == 1
    assert funcs[0].get("end_line") == 3
    assert "pub fn helper()" in funcs[0].get("source_code_snippet","")

    # Check no other code entities or dependencies
    other_entities = [p for p in payloads if p.get("type") not in ["TextChunk", "FunctionDefinition"]]
    assert len(other_entities) == 0, f"Found unexpected entities: {[e.get('type') for e in other_entities]}"

async def test_parse_simple_mod_file(parser: RustParser, tmp_path: Path):
    """Test parsing simple_mod.rs from test_data."""
    test_file = TEST_DATA_DIR / "simple_mod.rs"
    results = await run_parser_and_save_output(parser, test_file, tmp_path)

    assert len(results) > 0, "Expected DataPoints from simple_mod.rs"
    payloads = [dp.payload for dp in results]
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
    assert mod.get("name") == "utils"
    assert mod.get("start_line") == 4
    assert mod.get("source_code_snippet") == "mod utils; // Declare submodule"

    # Verify StructDefinition
    struct = payload_map["StructDefinition"][0]
    assert struct.get("name") == "Point"
    assert struct.get("start_line") == 6
    assert struct.get("end_line") == 9

    # Verify EnumDefinition
    enum = payload_map["EnumDefinition"][0]
    assert enum.get("name") == "Status"
    assert enum.get("start_line") == 19
    assert enum.get("end_line") == 22

    # Verify TraitDefinition
    trait = payload_map["TraitDefinition"][0]
    assert trait.get("name") == "Summary"
    assert trait.get("start_line") == 24
    assert trait.get("end_line") == 26

    # Verify Implementations
    impls = payload_map["Implementation"]
    impls.sort(key=lambda i: i.get("start_line", 0)) # Sort by line
    impl_point = impls[0] # impl Point { ... }
    impl_summary = impls[1] # impl Summary for Point { ... }
    assert impl_point.get("name") == "Point" # Name is the type being implemented
    assert impl_point.get("start_line") == 11
    assert impl_point.get("end_line") == 17
    assert "impl Point {" in impl_point.get("source_code_snippet", "")
    assert impl_summary.get("name") == "Point"
    assert impl_summary.get("start_line") == 28
    assert impl_summary.get("end_line") == 32
    assert "impl Summary for Point {" in impl_summary.get("source_code_snippet", "")

    # Verify FunctionDefinitions
    funcs = payload_map["FunctionDefinition"]
    func_map = {f.get("name"): f for f in funcs}
    assert set(func_map.keys()) == {"new", "distance_from_origin", "summarize", "process_point", "main"}
    assert func_map["new"]["start_line"] == 12
    assert func_map["distance_from_origin"]["start_line"] == 15
    assert func_map["summarize"]["start_line"] == 29 # Method inside trait impl
    assert func_map["process_point"]["start_line"] == 35
    assert func_map["main"]["start_line"] == 57

    # Verify MacroDefinition
    macro = payload_map["MacroDefinition"][0]
    assert macro.get("name") == "create_map"
    assert macro.get("start_line") == 46
    assert macro.get("end_line") == 55

    # Verify Dependencies (use statements)
    deps = payload_map["Dependency"]
    deps.sort(key=lambda d: d.get("start_line", 0)) # Sort by line
    assert deps[0].get("target_module") == "std::collections::HashMap"
    assert deps[0].get("start_line") == 2
    assert deps[0].get("source_code_snippet") == "use std::collections::HashMap; // Standard library import"
    assert deps[1].get("target_module") == "crate::utils::helper"
    assert deps[1].get("start_line") == 3
    assert deps[1].get("source_code_snippet") == "use crate::utils::helper; // Crate relative import"
