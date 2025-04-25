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
    from src.parser.parsers.cpp_parser import CppParser
    # Assuming C++ entities map to these generic types
    from src.parser.entities import DataPoint, TextChunk, CodeEntity, Dependency
except ImportError as e:
    pytest.skip(f"Skipping C++ parser tests: Failed to import dependencies - {e}", allow_module_level=True)


# Avoid runtime import errors if BaseParser isn't directly used
if TYPE_CHECKING:
    from src.parser.parsers.base_parser import BaseParser

# --- Test Configuration ---
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data" / "cpp"
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
def parser() -> CppParser:
    """Provides a CppParser instance, skipping if language not loaded."""
    try:
        from src.parser.parsers.treesitter_setup import get_language
        if get_language("cpp") is None:
            pytest.skip("C++ tree-sitter language not loaded or available.", allow_module_level=True)
    except ImportError as e:
        pytest.skip(f"Tree-sitter setup or core library not available: {e}", allow_module_level=True)

    return CppParser()

# --- Test Cases ---

async def test_parse_empty_cpp_file(parser: CppParser, tmp_path: Path):
    """Test parsing an empty C++ file."""
    empty_file = tmp_path / "empty.cpp"
    empty_file.touch()
    results = await run_parser_and_save_output(parser, empty_file, tmp_path)
    assert len(results) == 0, "Empty .cpp file should yield no DataPoints"

async def test_parse_empty_hpp_file(parser: CppParser, tmp_path: Path):
    """Test parsing an empty C++ header file."""
    empty_file = tmp_path / "empty.hpp"
    empty_file.touch()
    results = await run_parser_and_save_output(parser, empty_file, tmp_path)
    assert len(results) == 0, "Empty .hpp file should yield no DataPoints"

async def test_parse_simple_class_file(parser: CppParser, tmp_path: Path):
    """Test parsing simple_class.cpp from test_data."""
    test_file = TEST_DATA_DIR / "simple_class.cpp"
    results = await run_parser_and_save_output(parser, test_file, tmp_path)

    assert len(results) > 0, "Expected DataPoints from non-empty file"
    payloads = [dp.payload for dp in results]

    # Check for TextChunks
    chunks = [p for p in payloads if p.get("type") == "TextChunk"]
    assert len(chunks) >= 1, "Expected at least one TextChunk"

    # Check for CodeEntity (NamespaceDefinition)
    namespaces = [p for p in payloads if p.get("type") == "NamespaceDefinition"]
    assert len(namespaces) == 1, "Expected one namespace definition"
    ns = namespaces[0]
    assert ns.get("name") == "Processing"
    assert ns.get("start_line") == 10, "Incorrect start line for namespace"
    assert ns.get("end_line") == 24, "Incorrect end line for namespace"

    # Check for CodeEntity (FunctionDefinition)
    funcs = [p for p in payloads if p.get("type") == "FunctionDefinition"]
    # Expect: MyDataProcessor::processVector, helperFunction, main
    assert len(funcs) == 3, "Expected 3 function definitions"
    func_map = {f.get("name"): f for f in funcs if f.get("name")} # Name is simplified

    assert "processVector" in func_map
    assert func_map["processVector"]["start_line"] == 13
    assert func_map["processVector"]["end_line"] == 18
    assert "void MyDataProcessor::processVector" in func_map["processVector"]["source_code_snippet"]

    assert "helperFunction" in func_map
    assert func_map["helperFunction"]["start_line"] == 21
    assert func_map["helperFunction"]["end_line"] == 23
    assert "int helperFunction(int value)" in func_map["helperFunction"]["source_code_snippet"]

    assert "main" in func_map
    assert func_map["main"]["start_line"] == 28
    assert func_map["main"]["end_line"] == 35
    assert "int main()" in func_map["main"]["source_code_snippet"]

    # Check for Dependencies (Includes and Using)
    deps = [p for p in payloads if p.get("type") == "Dependency"]
    assert len(deps) == 5, "Expected 4 includes + 1 using directive"
    deps.sort(key=lambda d: d.get("start_line", 0))

    # Check includes
    assert deps[0].get("target_module") == "iostream" and deps[0].get("start_line") == 1
    assert deps[1].get("target_module") == "vector" and deps[1].get("start_line") == 2
    assert deps[2].get("target_module") == "string" and deps[2].get("start_line") == 3
    assert deps[3].get("target_module") == "my_class.hpp" and deps[3].get("start_line") == 4

    # Check using directive
    assert deps[4].get("target_module") == "std", "Using namespace target mismatch"
    assert deps[4].get("start_line") == 7
    assert deps[4].get("source_code_snippet") == "using namespace std;"

async def test_parse_header_file(parser: CppParser, tmp_path: Path):
    """Test parsing my_class.hpp from test_data."""
    test_file = TEST_DATA_DIR / "my_class.hpp"
    results = await run_parser_and_save_output(parser, test_file, tmp_path)

    assert len(results) > 0, "Expected DataPoints from non-empty header"
    payloads = [dp.payload for dp in results]

    # Check for TextChunks
    chunks = [p for p in payloads if p.get("type") == "TextChunk"]
    assert len(chunks) >= 1, "Expected at least one TextChunk"

    # Check for NamespaceDefinition
    namespaces = [p for p in payloads if p.get("type") == "NamespaceDefinition"]
    assert len(namespaces) == 1, "Expected one namespace"
    assert namespaces[0].get("name") == "Processing"

    # Check for ClassDefinition
    classes = [p for p in payloads if p.get("type") == "ClassDefinition"]
    assert len(classes) == 1, "Expected one class definition"
    cls = classes[0]
    assert cls.get("name") == "MyDataProcessor"
    assert cls.get("start_line") == 9
    assert cls.get("end_line") == 22

    # Check for FunctionDefinition (includes constructor, destructor, methods, templates)
    funcs = [p for p in payloads if p.get("type") == "FunctionDefinition"]
    # Expect: Constructor, Destructor, processVector (declaration), identity (template), helperFunction (declaration)
    assert len(funcs) >= 5, "Expected at least 5 function-like definitions"
    func_map = {f.get("name"): f for f in funcs if f.get("name")}

    # Constructor/Destructor names captured by query
    assert "MyDataProcessor" in func_map, "Constructor not found"
    assert func_map["MyDataProcessor"]["start_line"] == 14 # Line of constructor def

    assert "~MyDataProcessor" in func_map, "Destructor not found"
    assert func_map["~MyDataProcessor"]["start_line"] == 17 # Line of destructor def

    assert "processVector" in func_map, "processVector declaration not found"
    assert func_map["processVector"]["start_line"] == 20 # Line of method declaration

    assert "identity" in func_map, "identity template declaration not found"
    assert func_map["identity"]["start_line"] == 22 # Line of template method (adjust if query captures differently)
    assert "template<typename T>" in func_map["identity"]["source_code_snippet"]

    assert "helperFunction" in func_map, "helperFunction declaration not found"
    assert func_map["helperFunction"]["start_line"] == 25 # Line of function declaration

    # Check for Dependencies (Includes)
    deps = [p for p in payloads if p.get("type") == "Dependency"]
    assert len(deps) == 2, "Expected two include dependencies"
    deps.sort(key=lambda d: d.get("start_line", 0))
    assert deps[0].get("target_module") == "string" and deps[0].get("start_line") == 3
    assert deps[1].get("target_module") == "vector" and deps[1].get("start_line") == 4


async def test_parse_file_with_enums_structs(parser: CppParser, tmp_path: Path):
    """Test parsing C++ file with enums and structs within a namespace."""
    content = """
#include <string> // Include dep

namespace DataTypes { // Namespace def

    struct Point { // Struct def
        int x, y;
    };

    enum Status { // Enum def
        Active,
        Inactive
    };

    enum class ErrorCode { // Enum class def
        None = 0,
        IOError,
        NetworkError
    };
} // End namespace

struct GlobalStruct { float val; }; // Global struct def
"""
    test_file = tmp_path / "types.cpp"
    test_file.write_text(content, encoding="utf-8")
    results = await run_parser_and_save_output(parser, test_file, tmp_path)

    payloads = [dp.payload for dp in results]

    # Check for TextChunks
    chunks = [p for p in payloads if p.get("type") == "TextChunk"]
    assert len(chunks) >= 1

    # Check Namespace
    namespaces = [p for p in payloads if p.get("type") == "NamespaceDefinition"]
    assert len(namespaces) == 1
    assert namespaces[0].get("name") == "DataTypes"

    # Check Structs (namespaced and global)
    structs = [p for p in payloads if p.get("type") == "StructDefinition"]
    assert len(structs) == 2, "Expected two struct definitions"
    struct_map = {s.get("name"): s for s in structs}
    assert "Point" in struct_map
    assert struct_map["Point"]["start_line"] == 4 # Line 'struct Point {'
    assert struct_map["Point"]["end_line"] == 6 # Line '};'
    assert "GlobalStruct" in struct_map
    assert struct_map["GlobalStruct"]["start_line"] == 19 # Line 'struct GlobalStruct ...'

    # Check Enums (namespaced standard and class)
    enums = [p for p in payloads if p.get("type") == "EnumDefinition"]
    assert len(enums) == 2, "Expected two enum definitions"
    enum_map = {e.get("name"): e for e in enums}
    assert "Status" in enum_map
    assert enum_map["Status"]["start_line"] == 8 # Line 'enum Status {'
    assert "ErrorCode" in enum_map
    assert enum_map["ErrorCode"]["start_line"] == 13 # Line 'enum class ErrorCode {'

    # Check Dependency (Include)
    deps = [p for p in payloads if p.get("type") == "Dependency"]
    assert len(deps) == 1, "Expected one include dependency"
    assert deps[0].get("target_module") == "string"
    assert deps[0].get("start_line") == 1
