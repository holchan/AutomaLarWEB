# .roo/cognee/tests/parser/parsers/test_cpp_parser.py
import pytest
import asyncio
from pathlib import Path
from typing import List, Optional, Any
import os

# --- Cognee src imports ---
# IMPORTANT: We import the new data contracts
from src.parser.entities import CodeEntity, RawSymbolReference, ReferenceContext, ImportType
from src.parser.parsers.cpp_parser import CppParser
from src.parser.parsers.treesitter_setup import get_language
from src.parser.utils import logger, read_file_content

# --- Imports from other test utility modules ---
from tests.conftest import ParserTestOutput
# IMPORTANT: We import the new helper and remove the old ones
from tests.shared_test_utils import (
    find_code_entity_by_exact_temp_id,
    find_raw_symbol_references, # <-- NEW
)

pytestmark = pytest.mark.asyncio

# --- Test file specific constants ---
TEST_FILES_DIR = Path(__file__).resolve().parent.parent / "test_data" / "cpp"

if not TEST_FILES_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_FILES_DIR}", allow_module_level=True)

# --- Parser-specific Fixture ---
@pytest.fixture(scope="function")
def cpp_parser() -> CppParser:
    # This setup is correct
    if get_language("cpp") is None:
        pytest.skip("C++ tree-sitter language not loaded or available.", allow_module_level=True)
    return CppParser()

# --- NEW: A helper to run the parser and collect output ---
# This helper is essential for clean tests
async def run_parser(parser: CppParser, filename: str) -> ParserTestOutput:
    test_file_path = TEST_FILES_DIR / filename
    if not test_file_path.exists():
        pytest.skip(f"Test file not found: {test_file_path}")

    file_content = await read_file_content(str(test_file_path)) or ""
    # The source_id is just for context in the parser logs
    source_id = f"test_repo|{filename.replace(os.path.sep, '/')}"

    # We use the conftest fixture to collect the parser's output
    # This simulates how the orchestrator would consume the generator
    output = ParserTestOutput(slice_lines=[], code_entities=[], raw_symbol_references=[])
    async for item in parser.parse(source_id, file_content):
        if isinstance(item, list):
            output.slice_lines.extend(item)
        elif isinstance(item, CodeEntity):
            output.code_entities.append(item)
        elif isinstance(item, RawSymbolReference):
            output.raw_symbol_references.append(item)
    return output

# --- Refactored Test Cases ---

@pytest.mark.parametrize("filename, expect_entities, expect_refs", [
    ("empty_file.cpp", False, False),
    ("blank_file.cpp", False, False),
    ("comments_only_file.cpp", False, False),
])
async def test_parse_empty_and_comment_files(
    cpp_parser: CppParser,
    filename: str,
    expect_entities: bool,
    expect_refs: bool
):
    data = await run_parser(cpp_parser, filename)
    assert bool(data.code_entities) == expect_entities
    assert bool(data.raw_symbol_references) == expect_refs

async def test_parse_comments_with_include(cpp_parser: CppParser):
    data = await run_parser(cpp_parser, "comments_with_include.cpp")
    source_id = "test_repo|comments_with_include.cpp"

    assert data.slice_lines == [2], f"Actual slice_lines: {data.slice_lines}"

    # The parser should NOT create a CodeEntity for an include. It's a reference.
    assert len(data.code_entities) == 0, "Includes should not create CodeEntities."

    # It SHOULD create a RawSymbolReference.
    assert len(data.raw_symbol_references) == 1
    include_ref = data.raw_symbol_references[0]

    assert include_ref.source_entity_id == source_id
    assert include_ref.target_expression == "iostream"
    assert include_ref.reference_type == "INCLUDE"
    assert include_ref.context.import_type == ImportType.ABSOLUTE # from <...>
    assert include_ref.context.path_parts == ["iostream"]

async def test_parse_my_class_hpp(cpp_parser: CppParser):
    data = await run_parser(cpp_parser, "my_class.hpp")
    ces, refs = data.code_entities, data.raw_symbol_references

    # Test definitions
    assert find_code_entity_by_exact_temp_id(ces, "Processing::MyDataProcessor@9")
    assert find_code_entity_by_exact_temp_id(ces, "Processing::MyDataProcessor::MyDataProcessor(const std::string&)@15")
    assert find_code_entity_by_exact_temp_id(ces, "Processing::helperFunction(int)@29")

    # Test references (includes)
    string_include = find_raw_symbol_references(refs, target_expression="string", reference_type="INCLUDE")
    assert len(string_include) == 1
    assert string_include[0].context.import_type == ImportType.ABSOLUTE

    vector_include = find_raw_symbol_references(refs, target_expression="vector", reference_type="INCLUDE")
    assert len(vector_include) == 1
    assert vector_include[0].context.import_type == ImportType.ABSOLUTE

async def test_parse_inheritance_variations(cpp_parser: CppParser):
    data = await run_parser(cpp_parser, "inheritance_variations.hpp")
    ces, refs = data.code_entities, data.raw_symbol_references

    # Find the child classes first
    derived_single = find_code_entity_by_exact_temp_id(ces, "InheritanceTest::DerivedSingle@26")
    derived_multiple = find_code_entity_by_exact_temp_id(ces, "InheritanceTest::DerivedMultiple@33")
    derived_from_template = find_code_entity_by_exact_temp_id(ces, "InheritanceTest::DerivedFromTemplate@43")
    assert derived_single and derived_multiple and derived_from_template

    # Now, test that the correct RawSymbolReferences for inheritance were created
    single_inheritance_ref = find_raw_symbol_references(refs, source_entity_id_prefix="InheritanceTest::DerivedSingle", reference_type="INHERITANCE")
    assert len(single_inheritance_ref) == 1
    assert single_inheritance_ref[0].target_expression == "Base1"

    multiple_inheritance_refs = find_raw_symbol_references(refs, source_entity_id_prefix="InheritanceTest::DerivedMultiple", reference_type="INHERITANCE")
    assert len(multiple_inheritance_refs) == 2
    assert {"Base1", "Base2"} == {ref.target_expression for ref in multiple_inheritance_refs}

    template_inheritance_ref = find_raw_symbol_references(refs, source_entity_id_prefix="InheritanceTest::DerivedFromTemplate", reference_type="INHERITANCE")
    assert len(template_inheritance_ref) == 1
    assert template_inheritance_ref[0].target_expression == "TemplatedBase<int>"

async def test_parse_calls_specific(cpp_parser: CppParser):
    data = await run_parser(cpp_parser, "calls_specific.cpp")
    ces, refs = data.code_entities, data.raw_symbol_references

    # Find the calling function
    main_demo_func = find_code_entity_by_exact_temp_id(ces, "main_calls_demo(int,char*[])@71")
    assert main_demo_func

    # Test for specific calls originating from this function
    global_call = find_raw_symbol_references(refs, source_entity_id_prefix="main_calls_demo", target_expression="global_function_no_args", reference_type="FUNCTION_CALL")
    assert len(global_call) == 1

    namespaced_call = find_raw_symbol_references(refs, source_entity_id_prefix="main_calls_demo", target_expression="CallTestNS::a_namespaced_function", reference_type="FUNCTION_CALL")
    assert len(namespaced_call) == 1
    # Check the context provided by the parser
    assert namespaced_call[0].context.import_type == ImportType.ABSOLUTE
    assert namespaced_call[0].context.path_parts == ["CallTestNS", "a_namespaced_function"]

    member_call = find_raw_symbol_references(refs, source_entity_id_prefix="main_calls_demo", target_expression="tester_obj.simple_member_method", reference_type="FUNCTION_CALL")
    assert len(member_call) == 1

    static_call = find_raw_symbol_references(refs, source_entity_id_prefix="main_calls_demo", target_expression="MemberCallTester::static_method_target", reference_type="FUNCTION_CALL")
    assert len(static_call) == 1
