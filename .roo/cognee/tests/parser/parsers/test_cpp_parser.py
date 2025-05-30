# .roo/cognee/tests/parser/parsers/test_cpp_parser.py

import pytest
import asyncio
from pathlib import Path
from typing import List, AsyncGenerator # Added AsyncGenerator for the fixture type hint

from pydantic import BaseModel

from src.parser.parsers.cpp_parser import CppParser
from src.parser.entities import CodeEntity, Relationship, ParserOutput, TextChunk # Added ParserOutput
from src.parser.parsers.treesitter_setup import get_language
from src.parser.parsers.base_parser import BaseParser # For type hinting run_parser_and_save_output

# --- Define TEST_DATA_DIR directly ---
TEST_DATA_DIR = Path(__file__).resolve().parent.parent / "test_data" / "cpp"
if not TEST_DATA_DIR.is_dir():
    # This will only print if the script is run directly in a way that this path is wrong.
    # Pytest should handle paths correctly if run from the project root.
    print(f"Warning: Test data directory not found at {TEST_DATA_DIR}. Check path relative to test file.")

# --- Fixture Definitions ---
@pytest.fixture(scope="function")
def parser() -> CppParser:
    """Provides a CppParser instance for tests."""
    if get_language("cpp") is None:
        pytest.skip("C++ tree-sitter language not available for tests.", allow_module_level=True)
    return CppParser()

@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.get_event_loop_policy()

# --- Import run_parser_and_save_output from conftest ---
# Assuming conftest.py is located at .roo/cognee/tests/conftest.py
try:
    from ...conftest import run_parser_and_save_output
except ImportError as e:
    print(f"Warning: Could not import 'run_parser_and_save_output' from '...conftest'. Error: {e}")
    print("Ensure conftest.py is in the '.roo/cognee/tests/' directory and provides this fixture.")

    # Define a dummy fixture if import fails, so tests can be collected but will skip.
    # This helps identify if the problem is the fixture import itself.
    @pytest.fixture
    async def run_parser_and_save_output():
        # Type hint for the inner function to match expected signature
        async def _dummy_fixture(parser: BaseParser, test_file_path: Path, output_dir: Path) -> List[BaseModel]:
            pytest.skip("Fixture 'run_parser_and_save_output' is not available. Check conftest.py setup.")
            return []
        return _dummy_fixture

# --- Test Functions ---

@pytest.mark.asyncio
async def test_parse_empty_cpp_file(parser: CppParser, tmp_path: Path, run_parser_and_save_output):
    empty_cpp = tmp_path / "empty.cpp"
    empty_cpp.write_text("")
    results = await run_parser_and_save_output(parser=parser, test_file_path=empty_cpp, output_dir=tmp_path)
    assert len(results) == 0

@pytest.mark.asyncio
async def test_parse_empty_hpp_file(parser: CppParser, tmp_path: Path, run_parser_and_save_output):
    empty_hpp = tmp_path / "empty.hpp"
    empty_hpp.write_text("")
    results = await run_parser_and_save_output(parser=parser, test_file_path=empty_hpp, output_dir=tmp_path)
    assert len(results) == 0

@pytest.mark.asyncio
async def test_parse_simple_class_file(parser: CppParser, tmp_path: Path, run_parser_and_save_output):
    test_file = TEST_DATA_DIR / "simple_class.cpp"
    results = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0
    entities = [dp for dp in results if isinstance(dp, CodeEntity)]

    namespaces = [e for e in entities if e.type == "NamespaceDefinition"]
    assert any(":NamespaceDefinition:Processing:" in ns.id for ns in namespaces), "Namespace 'Processing' not found."

    classes = [e for e in entities if e.type == "ClassDefinition"]
    assert len(classes) == 1
    assert any(":ClassDefinition:SimpleClass:" in c.id for c in classes), f"Class 'SimpleClass' not found. Found: {[c.id for c in classes]}"

    func_defs = [e for e in entities if e.type == "FunctionDefinition"]
    assert len(func_defs) == 3, f"Expected 3 func_defs, found {len(func_defs)}. IDs: {[f.id for f in func_defs]}"

    assert any(":FunctionDefinition:main:" in f.id for f in func_defs)
    assert any("helperFunction" in f.id and f.type == "FunctionDefinition" for f in func_defs)
    assert any("processVector" in f.id and f.type == "FunctionDefinition" for f in func_defs)

    relationships = [dp for dp in results if isinstance(dp, Relationship)]
    assert any(r.type == "CONTAINS_ENTITY" for r in relationships)
    assert any(r.type == "CONTAINS_CHUNK" for r in relationships)
    imports = {r.target_id for r in relationships if r.type == "IMPORTS"}
    assert "my_class.hpp" in imports
    assert "iostream" in imports
    assert "std" in imports

@pytest.mark.asyncio
async def test_parse_header_file(parser: CppParser, tmp_path: Path, run_parser_and_save_output):
    test_file = TEST_DATA_DIR / "my_class.hpp"
    results: List[BaseModel] = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)

    assert len(results) > 0

    entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    relationships = [dp for dp in results if isinstance(dp, Relationship)]

    namespaces = [e for e in entities if e.type == "NamespaceDefinition"]
    assert len(namespaces) == 1, f"Expected 1 namespace, found {len(namespaces)}"
    assert ":NamespaceDefinition:Processing:" in namespaces[0].id, f"Namespace 'Processing' not found correctly: {namespaces[0].id if namespaces else 'None'}"

    classes = [e for e in entities if e.type == "ClassDefinition"]
    assert len(classes) == 1, f"Expected 1 class, found {len(classes)}"
    cls_my_data_proc = next((c for c in classes if ":ClassDefinition:MyDataProcessor:" in c.id), None)
    assert cls_my_data_proc is not None, "Class 'MyDataProcessor' not found"

    func_defs = [e for e in entities if e.type == "FunctionDefinition"]
    func_decls = [e for e in entities if e.type == "FunctionDeclaration"]

    expected_func_defs = 3
    expected_func_decls = 2

    assert len(func_defs) == expected_func_defs, \
        f"Expected {expected_func_defs} FunctionDefinitions. Found {len(func_defs)}: {[f.id for f in func_defs]}. Snippets: {[f.snippet_content[:70] + '...' for f in func_defs]}"

    assert any("MyDataProcessor" in f.id and "~" not in f.id for f in func_defs), "Constructor MyDataProcessor not found as definition"
    assert any("~MyDataProcessor" in f.id for f in func_defs), "Destructor ~MyDataProcessor not found as definition"
    assert any("identity" in f.id for f in func_defs), "Template function identity not found as definition"

    assert len(func_decls) == expected_func_decls, \
        f"Expected {expected_func_decls} FunctionDeclarations. Found {len(func_decls)}: {[d.id for d in func_decls]}. Snippets: {[d.snippet_content[:70] + '...' for d in func_decls]}"

    assert any("processVector" in d.id for d in func_decls), "Method processVector not found as declaration"
    assert any("helperFunction" in d.id for d in func_decls), "Function helperFunction not found as declaration"

    assert not any("processVector" in f.id for f in func_defs), "processVector should be a declaration, not a definition"
    assert not any("helperFunction" in f.id for f in func_defs), "helperFunction should be a declaration, not a definition"

    constructor_def = next((f for f in func_defs if "MyDataProcessor" in f.id and "~" not in f.id), None)
    assert constructor_def is not None
    assert any(r.source_id == cls_my_data_proc.id and r.target_id == constructor_def.id and r.type == "CONTAINS_ENTITY" for r in relationships), \
        f"MyDataProcessor class should contain constructor {constructor_def.id}"

    destructor_def = next((f for f in func_defs if "~MyDataProcessor" in f.id), None)
    assert destructor_def is not None
    assert any(r.source_id == cls_my_data_proc.id and r.target_id == destructor_def.id and r.type == "CONTAINS_ENTITY" for r in relationships), \
        f"MyDataProcessor class should contain destructor {destructor_def.id}"

    process_vector_decl = next((d for d in func_decls if "processVector" in d.id), None)
    assert process_vector_decl is not None
    assert any(r.source_id == cls_my_data_proc.id and r.target_id == process_vector_decl.id and r.type == "CONTAINS_ENTITY" for r in relationships), \
        f"MyDataProcessor class should contain processVector declaration {process_vector_decl.id}"

    template_identity_def = next((f for f in func_defs if "identity" in f.id), None)
    assert template_identity_def is not None
    assert any(r.source_id == cls_my_data_proc.id and r.target_id == template_identity_def.id and r.type == "CONTAINS_ENTITY" for r in relationships), \
        f"MyDataProcessor class should contain template identity definition {template_identity_def.id}"

    assert any(r.source_id == namespaces[0].id and r.target_id == cls_my_data_proc.id and r.type == "CONTAINS_ENTITY" for r in relationships)

    helper_func_decl = next((d for d in func_decls if "helperFunction" in d.id), None)
    assert helper_func_decl is not None
    assert any(r.source_id == namespaces[0].id and r.target_id == helper_func_decl.id and r.type == "CONTAINS_ENTITY" for r in relationships)

    imports = {r.target_id for r in relationships if r.type == "IMPORTS"}
    assert "string" in imports
    assert "vector" in imports

@pytest.mark.asyncio
async def test_complex_features_file(parser: CppParser, tmp_path: Path, run_parser_and_save_output):
    test_file = TEST_DATA_DIR / "complex_features.cpp"
    results = await run_parser_and_save_output(parser=parser, test_file_path=test_file, output_dir=tmp_path)
    entities = [dp for dp in results if isinstance(dp, CodeEntity)]

    assert len(entities) > 0, "No entities found in complex_features.cpp"

    func_defs = [e for e in entities if e.type == "FunctionDefinition"]
    func_decls = [e for e in entities if e.type == "FunctionDeclaration"]

    assert any("templatedFunction" in f.id for f in func_defs), "templatedFunction definition missing"
    assert any("normalFunctionWithDefault" in f.id for f in func_defs), "normalFunctionWithDefault definition missing"
    assert any("MyComplexClass" in f.id and "~" not in f.id and "staticMethod" not in f.id and "virtualMethod" not in f.id and "constMethod" not in f.id and "deletedMethod" not in f.id and "operator+" not in f.id for f in func_defs), "MyComplexClass constructor definition missing"
    assert any("~MyComplexClass" in f.id for f in func_defs), "MyComplexClass destructor definition missing"
    assert any("staticMethod" in f.id for f in func_defs), "staticMethod definition missing"
    assert any("virtualMethod" in f.id for f in func_defs), "virtualMethod definition missing"
    assert any("constMethod" in f.id for f in func_defs), "constMethod definition missing"
    assert any("deletedMethod" in f.id for f in func_defs), "deletedMethod definition missing"
    assert any("operator+" in f.id for f in func_defs), "operator+ definition missing"
    assert any("useLambda" in f.id for f in func_defs), "useLambda definition missing"
    assert any("main" in f.id for f in func_defs), "main definition missing"

    assert any("anotherTemplatedFunction" in d.id for d in func_decls), "anotherTemplatedFunction declaration missing"
    assert any("anExternFunction" in d.id for d in func_decls), "anExternFunction declaration missing"

    classes = {e.id.split(":")[3].replace('_', '::') for e in entities if e.type == "ClassDefinition"}
    assert "MyComplexClass" in classes
    assert "LambdaUser" in classes

    structs = {e.id.split(":")[3].replace('_', '::') for e in entities if e.type == "StructDefinition"}
    assert "SimpleStruct" in structs
    assert "DataContainer" in structs

    enums = {e.id.split(":")[3].replace('_', '::') for e in entities if e.type == "EnumDefinition"}
    assert "Color" in enums
    assert "ScopedEnum" in enums

    relationships = [item for item in results if isinstance(item, Relationship)]
    assert any(rel.type == "IMPORTS" and rel.target_id == "std" for rel in relationships), "'using namespace std' import missing"

    imports = {r.target_id for r in relationships if r.type == "IMPORTS"}
    expected_imports = {"iostream", "vector", "string", "array", "functional", "std"}
    missing_imports = expected_imports - imports
    assert not missing_imports, f"Missing expected imports: {missing_imports}"
