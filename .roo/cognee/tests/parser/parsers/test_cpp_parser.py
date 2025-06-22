# .roo/cognee/tests/parser/parsers/test_cpp_parser.py
import pytest
import asyncio
from pathlib import Path
from typing import List, Optional, Any
import os

# --- Cognee src imports ---
from src.parser.entities import CodeEntity, Relationship, CallSiteReference
from src.parser.parsers.cpp_parser import CppParser
from src.parser.parsers.treesitter_setup import get_language
from src.parser.utils import logger, read_file_content # read_file_content for direct use

# --- Imports from other test utility modules ---
from tests.conftest import ParserTestOutput # From conftest
# Import helpers from shared_test_utils
from tests.shared_test_utils import (
    # load_test_file_content, # We are using read_file_content directly now
    find_code_entity_by_id_prefix,
    find_code_entity_by_exact_temp_id,
    find_relationships,
    find_call_sites
)

pytestmark = pytest.mark.asyncio

# --- Test file specific constants ---
TEST_FILES_DIR = Path(__file__).resolve().parent.parent / "test_data" / "cpp"

if not TEST_FILES_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_FILES_DIR}", allow_module_level=True)

# --- Parser-specific Fixture ---
@pytest.fixture(scope="function")
def cpp_parser() -> CppParser:
    if get_language("cpp") is None:
        pytest.skip("C++ tree-sitter language not loaded or available.", allow_module_level=True)
    return CppParser()

# --- Test Cases ---
@pytest.mark.parametrize("filename, expected_slice_lines, expect_entities, expect_rels, expect_calls", [
    ("empty_file.cpp", [], False, False, False), # empty_file.cpp is 0 bytes
    ("blank_file.cpp", [], False, False, False), # blank_file.cpp contains only whitespace
    ("comments_only_file.cpp", [0], False, False, False),
])
async def test_parse_empty_and_comment_files(
    cpp_parser: CppParser,
    parse_file_and_collect_output: Any, # Fixture from conftest
    filename: str,
    expected_slice_lines: List[int],
    expect_entities: bool,
    expect_rels: bool,
    expect_calls: bool
):
    test_file_path = TEST_FILES_DIR / filename
    file_content_raw = await read_file_content(str(test_file_path))
    file_content = file_content_raw if file_content_raw is not None else ""

    path_part_in_id = filename # Using direct filename as path part for these simple cases
    source_id = f"test_repo|{path_part_in_id.replace(os.path.sep, '/')}"

    data: ParserTestOutput = await parse_file_and_collect_output(
        cpp_parser,
        source_id,
        file_content,
        test_file_path
    )

    assert data.slice_lines == expected_slice_lines, f"Slice lines mismatch for {filename}"
    assert bool(data.code_entities) == expect_entities, f"Code entities expectation mismatch for {filename}: Got {len(data.code_entities)}"
    assert bool(data.relationships) == expect_rels, f"Relationships expectation mismatch for {filename}: Got {len(data.relationships)}"
    assert bool(data.call_site_references) == expect_calls, f"Call sites expectation mismatch for {filename}: Got {len(data.call_site_references)}"


async def test_parse_comments_with_include(cpp_parser: CppParser, parse_file_and_collect_output: Any):
    filename = "comments_with_include.cpp"
    test_file_path = TEST_FILES_DIR / filename
    file_content_raw = await read_file_content(str(test_file_path))
    file_content = file_content_raw if file_content_raw is not None else ""
    source_id = f"test_repo|{filename.replace(os.path.sep, '/')}"
    data: ParserTestOutput = await parse_file_and_collect_output(cpp_parser, source_id, file_content, test_file_path)

    assert data.slice_lines == [0, 2], f"Actual slice_lines: {data.slice_lines}"
    assert len(data.code_entities) == 1, f"Expected 1 CE, got {len(data.code_entities)}, CEs: {[e.id for e in data.code_entities]}"
    ext_ref = find_code_entity_by_exact_temp_id(data.code_entities, "std::iostream@2")
    assert ext_ref and ext_ref.type == "ExternalReference" and ext_ref.snippet_content == "std::iostream"
    assert len(data.relationships) == 1
    assert find_relationships(data.relationships, source_id=source_id, target_id="std::iostream@2", rel_type="IMPORTS")
    assert not data.call_site_references

async def test_parse_closely_packed_definitions(cpp_parser: CppParser, parse_file_and_collect_output: Any):
    filename = "closely_packed_definitions.cpp"
    test_file_path = TEST_FILES_DIR / filename
    file_content_raw = await read_file_content(str(test_file_path))
    file_content = file_content_raw if file_content_raw is not None else ""
    source_id = f"test_repo|{filename.replace(os.path.sep, '/')}"
    data: ParserTestOutput = await parse_file_and_collect_output(cpp_parser, source_id, file_content, test_file_path)

    expected_slices = sorted(list(set([0, 1, 2, 3, 4])))
    assert data.slice_lines == expected_slices, f"Actual slice_lines: {data.slice_lines}"
    ces = data.code_entities
    assert len(ces) == 7, f"Expected 7 CEs, got {len(ces)}. IDs: {[e.id for e in ces]}"
    assert find_code_entity_by_exact_temp_id(ces, "Point2D@0")
    assert find_code_entity_by_exact_temp_id(ces, "TinyNS@1")
    assert find_code_entity_by_exact_temp_id(ces, "TinyNS::Helper@1").type == "ClassDefinition"
    assert find_code_entity_by_exact_temp_id(ces, "TinyNS::Helper::assist()@1").type == "FunctionDeclaration"
    assert find_code_entity_by_exact_temp_id(ces, "Color@2")
    assert find_code_entity_by_exact_temp_id(ces, "standaloneFunction(int)@3")
    assert find_code_entity_by_exact_temp_id(ces, "Vec2D@4").type == "TypeAlias"

async def test_parse_forward_declarations(cpp_parser: CppParser, parse_file_and_collect_output: Any):
    filename = "forward_declarations.hpp"
    test_file_path = TEST_FILES_DIR / filename
    file_content_raw = await read_file_content(str(test_file_path))
    file_content = file_content_raw if file_content_raw is not None else ""
    source_id = f"test_repo|{filename.replace(os.path.sep, '/')}"
    data: ParserTestOutput = await parse_file_and_collect_output(cpp_parser, source_id, file_content, test_file_path)

    expected_slices = sorted(list(set([0, 2, 3, 5, 6, 7, 10])))
    assert data.slice_lines == expected_slices, f"Actual slice_lines: {data.slice_lines}"
    ces = data.code_entities
    assert len(ces) == 6, f"Expected 6 CEs, got {len(ces)}. IDs: {[e.id for e in ces]}"
    assert find_code_entity_by_exact_temp_id(ces, "MyForwardClass@2").type == "ClassDefinition"
    assert find_code_entity_by_exact_temp_id(ces, "MyForwardStruct@3").type == "StructDefinition"
    assert find_code_entity_by_exact_temp_id(ces, "FwdNS@5").type == "NamespaceDefinition"
    assert find_code_entity_by_exact_temp_id(ces, "FwdNS::MyFwdEnum@6").type == "EnumDefinition"
    assert find_code_entity_by_exact_temp_id(ces, "FwdNS::AnotherFwdClass@7").type == "ClassDefinition"
    assert find_code_entity_by_exact_temp_id(ces, "fwd_declared_func(int)@10").type == "FunctionDeclaration"

async def test_parse_my_class_hpp(cpp_parser: CppParser, parse_file_and_collect_output: Any):
    filename = "my_class.hpp"
    test_file_path = TEST_FILES_DIR / filename
    if not test_file_path.exists(): pytest.skip(f"Test file {test_file_path} not found.")
    file_content_raw = await read_file_content(str(test_file_path))
    file_content = file_content_raw if file_content_raw is not None else ""
    source_id = f"test_repo|{filename.replace(os.path.sep, '/')}"
    data: ParserTestOutput = await parse_file_and_collect_output(cpp_parser, source_id, file_content, test_file_path)

    expected_slices = sorted(list(set([0, 3, 4, 6, 9, 15, 18, 21, 24, 25, 29])))
    assert data.slice_lines == expected_slices, f"Actual slice_lines for my_class.hpp: {data.slice_lines}"
    ces, rels = data.code_entities, data.relationships
    assert find_code_entity_by_exact_temp_id(ces, "std::string@3").type == "ExternalReference"
    assert find_relationships(rels, source_id=source_id, target_id="std::string@3", rel_type="IMPORTS")
    assert find_code_entity_by_exact_temp_id(ces, "std::vector@4").type == "ExternalReference"
    assert find_relationships(rels, source_id=source_id, target_id="std::vector@4", rel_type="IMPORTS")
    assert find_code_entity_by_exact_temp_id(ces, "Processing@6")
    assert find_code_entity_by_exact_temp_id(ces, "Processing::MyDataProcessor@9")
    assert find_code_entity_by_exact_temp_id(ces, "Processing::MyDataProcessor::MyDataProcessor(const std::string&)@15")
    assert find_code_entity_by_exact_temp_id(ces, "Processing::MyDataProcessor::~MyDataProcessor()@18")
    assert find_code_entity_by_exact_temp_id(ces, "Processing::MyDataProcessor::processVector(const std::vector<std::string>&)@21").type == "FunctionDeclaration"
    assert find_code_entity_by_exact_temp_id(ces, "Processing::MyDataProcessor::identity(T)@24").type == "FunctionDefinition" # Template itself
    assert find_code_entity_by_exact_temp_id(ces, "Processing::MyDataProcessor::identity(T)@25").type == "FunctionDefinition" # Inner function of template
    assert find_code_entity_by_exact_temp_id(ces, "Processing::helperFunction(int)@29").type == "FunctionDeclaration"
    assert not data.call_site_references

async def test_parse_simple_class_cpp(cpp_parser: CppParser, parse_file_and_collect_output: Any):
    filename = "simple_class.cpp"
    test_file_path = TEST_FILES_DIR / filename
    if not test_file_path.exists(): pytest.skip(f"Test file {test_file_path} not found.")
    file_content_raw = await read_file_content(str(test_file_path))
    file_content = file_content_raw if file_content_raw is not None else ""
    source_id = f"test_repo|{filename.replace(os.path.sep, '/')}"
    data: ParserTestOutput = await parse_file_and_collect_output(cpp_parser, source_id, file_content, test_file_path)

    ces, rels, calls = data.code_entities, data.relationships, data.call_site_references
    expected_slices = sorted(list(set([0, 1, 2, 3, 6, 8, 11, 19, 26])))
    assert data.slice_lines == expected_slices, f"Actual slice_lines: {data.slice_lines}"

    assert find_code_entity_by_exact_temp_id(ces, "std::iostream@0")
    assert find_code_entity_by_exact_temp_id(ces, "std::vector@1")
    assert find_code_entity_by_exact_temp_id(ces, "std::string@2")
    assert find_code_entity_by_exact_temp_id(ces, "my_class.hpp@3").snippet_content == "my_class.hpp"
    directive_ce = find_code_entity_by_exact_temp_id(ces, "using_namespace_directive_referencing::std@6")
    assert directive_ce and directive_ce.type == "UsingDirective"
    pv_impl = find_code_entity_by_exact_temp_id(ces, "Processing::MyDataProcessor::processVector(const vector<string>&)@11") or \
              find_code_entity_by_exact_temp_id(ces, "Processing::MyDataProcessor::processVector(const std::vector<std::string>&)@11")
    assert pv_impl and pv_impl.type == "FunctionDefinition"
    hf_impl = find_code_entity_by_exact_temp_id(ces, "Processing::helperFunction(int)@19")
    assert hf_impl and hf_impl.type == "FunctionDefinition"
    main_func = find_code_entity_by_exact_temp_id(ces, "main()@26")
    assert main_func and main_func.type == "FunctionDefinition"
    main_func_temp_id = main_func.id
    assert len(find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="processor.processVector", at_line_0=29)) == 1
    assert len(find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="operator<<", at_line_0=31)) >= 1
    assert len(find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="Processing::helperFunction", at_line_0=31)) == 1
    if pv_impl:
        assert len(find_call_sites(calls, calling_entity_temp_id=pv_impl.id, called_name_expr="operator<<", at_line_0=12)) >= 1
        assert len(find_call_sites(calls, calling_entity_temp_id=pv_impl.id, called_name_expr="operator<<", at_line_0=14)) >= 1

async def test_parse_complex_features(cpp_parser: CppParser, parse_file_and_collect_output: Any):
    filename = "complex_features.cpp"
    test_file_path = TEST_FILES_DIR / filename
    if not test_file_path.exists(): pytest.skip(f"Test file {test_file_path} not found.")
    file_content_raw = await read_file_content(str(test_file_path))
    file_content = file_content_raw if file_content_raw is not None else ""
    source_id = f"test_repo|{filename.replace(os.path.sep, '|')}"

    data: ParserTestOutput = await parse_file_and_collect_output(cpp_parser, source_id, file_content, test_file_path)
    ces, rels, calls = data.code_entities, data.relationships, data.call_site_references
    logger.info(f"Complex Features Test: Found {len(ces)} CEs, {len(rels)} Rels, {len(calls)} CallSites.")

    # Expected slices, including line 9 for the FuncPtr typedef
    expected_slices = sorted(list(set([
        0, 1, 2, 3, 4, 6, 8, 9, 10, # Line 9 added
        13, 14, 15, 20, 25, 31, 33, 38, 43, 44, 45, 49, 50, 56,
        61, 65, 69, 73, 77, 81, 83, 89, 93, 98, 99, 101, 105, 110, 117, 127, 132, 134
    ])))
    assert data.slice_lines == expected_slices, \
        f"Slice lines mismatch. Actual: {data.slice_lines}"

    logger.info(f"--- TypeAlias CodeEntities found in {filename} ---")
    found_func_ptr_specific_log = False
    for ce in ces:
        if ce.type == "TypeAlias":
            logger.info(f"TypeAlias Candidate: ID='{ce.id}', Snippet='{ce.snippet_content.strip()}'")
            if "FuncPtr(int)@9" in ce.id : # Check if the specific ID is present
                found_func_ptr_specific_log = True
    if not found_func_ptr_specific_log:
         logger.warning(f"TypeAlias with specific ID 'FuncPtr(int)@9' was not found in parser output for {filename}.")
    logger.info(f"----------------------------------------------------")

    assert find_code_entity_by_exact_temp_id(ces, "ForwardDeclaredClass@6")
    assert find_code_entity_by_exact_temp_id(ces, "Number@8").type == "TypeAlias"

    # Updated assertion for FuncPtr
    func_ptr_entity = find_code_entity_by_exact_temp_id(ces, "FuncPtr(int)@9")
    assert func_ptr_entity is not None, \
        (f"TypeAlias for 'FuncPtr(int)@9' was NOT found. Check DEBUG_TYPEDEF_MATCH logs in CppParser. "
         f"Relevant CEs by name part 'FuncPtr': {[ce.id for ce in ces if 'FuncPtr' in ce.id]}. "
         f"Relevant CEs by line '@9': {[ce.id for ce in ces if '@9' in ce.id]}.")
    if func_ptr_entity:
        assert func_ptr_entity.type == "TypeAlias"
        assert func_ptr_entity.snippet_content == "typedef void (*FuncPtr)(int);"


    assert find_code_entity_by_exact_temp_id(ces, "StringVector@10").type == "TypeAlias"
    # ... (rest of the assertions for complex_features remain the same as your Attempt 59) ...
    assert find_code_entity_by_exact_temp_id(ces, "TestNS@13")
    assert find_code_entity_by_exact_temp_id(ces, "TestNS::InnerNS@14")
    assert find_code_entity_by_exact_temp_id(ces, "TestNS::InnerNS::innerFunction()@15")
    assert find_code_entity_by_exact_temp_id(ces, "TestNS::DataContainer@20")
    assert find_code_entity_by_exact_temp_id(ces, "TestNS::namespacedFunction(const TestNS::DataContainer&)@25") or \
           find_code_entity_by_exact_temp_id(ces, "TestNS::namespacedFunction(const DataContainer&)@25")

    assert find_code_entity_by_exact_temp_id(ces, "anonymous@31")
    assert find_code_entity_by_exact_temp_id(ces, "anonymous::anonNSFunction()@33")

    assert find_code_entity_by_exact_temp_id(ces, "SimpleStruct@38")
    assert find_code_entity_by_exact_temp_id(ces, "UnscopedEnum@43")
    scoped_enum = find_code_entity_by_exact_temp_id(ces, "TestNS::ScopedEnum@45")
    assert scoped_enum and scoped_enum.type == "EnumDefinition"

    assert find_code_entity_by_exact_temp_id(ces, "createInitializedArray(T)@49") # Template definition itself

    assert find_code_entity_by_exact_temp_id(ces, "MyComplexClass@56")
    assert find_code_entity_by_exact_temp_id(ces, "MyComplexClass::MyComplexClass(std::string)@61")
    assert find_code_entity_by_exact_temp_id(ces, "MyComplexClass::~MyComplexClass()@65")
    assert find_code_entity_by_exact_temp_id(ces, "MyComplexClass::virtualMethod()@69")
    assert find_code_entity_by_exact_temp_id(ces, "MyComplexClass::constMethod()@73")
    assert find_code_entity_by_exact_temp_id(ces, "MyComplexClass::staticMethod()@77")
    assert find_code_entity_by_exact_temp_id(ces, "MyComplexClass::deletedMethod()@81")
    assert find_code_entity_by_exact_temp_id(ces, "MyComplexClass::operator+(const MyComplexClass&)@83")
    friend_decl = find_code_entity_by_exact_temp_id(ces, "MyComplexClass::friendFunction(MyComplexClass&)@89")
    assert friend_decl and friend_decl.type == "FunctionDeclaration"
    assert find_code_entity_by_exact_temp_id(ces, "friendFunction(MyComplexClass&)@93")
    derived_cls = find_code_entity_by_exact_temp_id(ces, "TestNS::DerivedClass@99")
    assert derived_cls and derived_cls.type == "ClassDefinition"
    assert find_relationships(rels, source_id=derived_cls.id, target_id="MyComplexClass", rel_type="EXTENDS")
    assert find_code_entity_by_exact_temp_id(ces, "TestNS::DerivedClass::DerivedClass(std::string)@101")
    assert find_code_entity_by_exact_temp_id(ces, "TestNS::DerivedClass::virtualMethod()@105")
    assert find_code_entity_by_exact_temp_id(ces, "TestNS::DerivedClass::anotherVirtualMethod()@110")
    assert find_code_entity_by_exact_temp_id(ces, "useLambda()@117")
    assert find_code_entity_by_exact_temp_id(ces, "c_style_function(int)@127")
    using_directive = find_code_entity_by_exact_temp_id(ces, "using_namespace_directive_referencing::std@132")
    assert using_directive and using_directive.type == "UsingDirective"
    main_func = find_code_entity_by_exact_temp_id(ces, "main()@134")
    assert main_func and main_func.type == "FunctionDefinition"
    main_func_temp_id = main_func.id

    assert len(find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="MyComplexClass::staticMethod", at_line_0=140)) == 1
    op_plus_obj_call = find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="operator+", at_line_0=142)
    assert len(op_plus_obj_call) == 1 and op_plus_obj_call[0].argument_count == 2
    constructor_call_in_expr = find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="MyComplexClass", arg_count=1, at_line_0=142)
    assert len(constructor_call_in_expr) == 1 and constructor_call_in_expr[0].raw_arg_text == "\"Obj2_Added\""
    assert len(find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="anonNSFunction", at_line_0=149)) == 1 # Line 149 for anonNSFunction call
    call_namespaced = find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="TestNS::namespacedFunction", at_line_0=148) # Line 148 for TestNS::namespacedFunction
    assert len(call_namespaced) == 1 and call_namespaced[0].raw_arg_text == "dc"
    assert len(find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="derived_obj.virtualMethod", at_line_0=152)) == 1
    assert len(find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="useLambda", at_line_0=158)) == 1

    inner_func = find_code_entity_by_exact_temp_id(ces, "TestNS::InnerNS::innerFunction()@15")
    assert inner_func
    assert len(find_call_sites(calls, calling_entity_temp_id=inner_func.id, called_name_expr="operator<<", at_line_0=16)) >= 1


async def test_parse_calls_specific(cpp_parser: CppParser, parse_file_and_collect_output: Any):
    filename = "calls_specific.cpp"
    test_file_path = TEST_FILES_DIR / filename
    if not test_file_path.exists(): pytest.skip(f"Test file {test_file_path} not found.")
    file_content_raw = await read_file_content(str(test_file_path))
    file_content = file_content_raw if file_content_raw is not None else ""
    source_id = f"test_repo|{filename.replace(os.path.sep, '|')}"
    data: ParserTestOutput = await parse_file_and_collect_output(cpp_parser, source_id, file_content, test_file_path)
    ces, calls = data.code_entities, data.call_site_references

    main_demo_func = find_code_entity_by_exact_temp_id(ces, "main_calls_demo(int,char*[])@71") # Line 71 for main_calls_demo
    assert main_demo_func
    main_demo_func_id = main_demo_func.id

    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="global_function_no_args", arg_count=0, at_line_0=72) # Line 72
    csr1 = find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="global_function_with_args", arg_count=2, at_line_0=73) # Line 73
    assert len(csr1) == 1 and csr1[0].raw_arg_text == "10, \"hello from main\""
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="CallTestNS::a_namespaced_function", arg_count=1, at_line_0=75) # Line 75
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="func_ptr", arg_count=1, at_line_0=78) # Line 78
    csr_raw_ptr = find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, at_line_0=81) # Line 81
    assert len(csr_raw_ptr) == 1 and (csr_raw_ptr[0].called_name_expr == "raw_func_ptr" or csr_raw_ptr[0].called_name_expr == "(*raw_func_ptr)")
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="callable_struct_instance", arg_count=1, at_line_0=84) # Line 84
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="tester_obj.simple_member_method", arg_count=1, at_line_0=87) # Line 87
    csr_new_tester = find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="MemberCallTester", arg_count=1, at_line_0=89)
    assert len(csr_new_tester) == 1 and csr_new_tester[0].raw_arg_text == "\"PtrObj\""
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="tester_ptr->another_member_method", arg_count=2, at_line_0=90) # Line 90
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="MemberCallTester::static_method_target", arg_count=1, at_line_0=92) # Line 92
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="MemberCallTester::static_method_caller", arg_count=0, at_line_0=93) # Line 93

    csr_template_expl = find_call_sites(calls,
                                        calling_entity_temp_id=main_demo_func_id,
                                        called_name_expr="CallTestNS::generic_processor<int>", # Expecting full name
                                        at_line_0=96, # Line 96
                                        arg_count=1)
    assert len(csr_template_expl) == 1, \
        (f"Call to 'CallTestNS::generic_processor<int>' at line 96 not found or found multiple. "
         f"Found with same caller and line: {[cs.model_dump_json(exclude_none=True) for cs in find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, at_line_0=96)]}")
    if csr_template_expl:
        assert csr_template_expl[0].raw_arg_text == "template_arg"

    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="CallTestNS::generic_processor", at_line_0=97) # Line 97
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="tester_obj.get_vector", arg_count=0, at_line_0=99) # Line 99
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="my_vec.push_back", arg_count=1, at_line_0=100) # Line 100

    stack_constructor_call = find_call_sites(calls,
                                             calling_entity_temp_id=main_demo_func_id,
                                             called_name_expr="Processing::MyDataProcessor", # Constructor call via type name
                                             at_line_0=102, # Line 102
                                             arg_count=1)
    assert len(stack_constructor_call) == 1, \
        (f"Stack-based constructor call to 'Processing::MyDataProcessor' at line 102 not found or found multiple. "
         f"Found: {[cs.model_dump_json(exclude_none=True) for cs in find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, at_line_0=102)]}")
    if stack_constructor_call:
        assert stack_constructor_call[0].raw_arg_text == "\"ExternalClass\""


    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="processor_ext.processVector", arg_count=1, at_line_0=104) # Line 104
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="operator+", arg_count=2, at_line_0=107) # Line 107
    assert len(find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="operator<<", at_line_0=108)) >= 1 # Line 108
    assert len(find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="operator delete", at_line_0=110)) == 1 # Line 110

    simple_method = find_code_entity_by_exact_temp_id(ces, "MemberCallTester::simple_member_method(int)@50") # Line 50
    assert simple_method
    assert len(find_call_sites(calls, calling_entity_temp_id=simple_method.id, called_name_expr="this->another_member_method", at_line_0=52)) == 1 # Line 52
    assert len(find_call_sites(calls, calling_entity_temp_id=simple_method.id, called_name_expr="global_function_no_args", at_line_0=53)) == 1 # Line 53

async def test_parse_inheritance_variations(cpp_parser: CppParser, parse_file_and_collect_output: Any):
    filename = "inheritance_variations.hpp"
    test_file_path = TEST_FILES_DIR / filename
    if not test_file_path.exists(): pytest.skip(f"Test file {test_file_path} not found.")
    file_content_raw = await read_file_content(str(test_file_path))
    file_content = file_content_raw if file_content_raw is not None else ""
    source_id = f"test_repo|{filename.replace(os.path.sep, '|')}"
    data: ParserTestOutput = await parse_file_and_collect_output(cpp_parser, source_id, file_content, test_file_path)
    ces, rels, calls = data.code_entities, data.relationships, data.call_site_references

    expected_slices = sorted(list(set([
        0, 1, 3, 5, 7, 8, 9, 12, 15, 19, 22, 26, 28, 29, 33, 35, 36, 43, 45, 52, 57, 58
    ])))
    assert data.slice_lines == expected_slices, f"Actual slice_lines: {data.slice_lines}"

    base1 = find_code_entity_by_exact_temp_id(ces, "InheritanceTest::Base1@5")
    assert base1
    derived_single = find_code_entity_by_exact_temp_id(ces, "InheritanceTest::DerivedSingle@26")
    assert derived_single
    derived_multiple = find_code_entity_by_exact_temp_id(ces, "InheritanceTest::DerivedMultiple@33")
    assert derived_multiple
    templated_base_class = find_code_entity_by_exact_temp_id(ces, "InheritanceTest::TemplatedBase@19")
    assert templated_base_class and templated_base_class.type == "ClassDefinition"
    derived_from_template = find_code_entity_by_exact_temp_id(ces, "InheritanceTest::DerivedFromTemplate@43")
    assert derived_from_template
    assert find_relationships(rels, source_id=derived_single.id, target_id="Base1", rel_type="EXTENDS")
    dm_extends = find_relationships(rels, source_id=derived_multiple.id, rel_type="EXTENDS")
    assert len(dm_extends) == 2 and {"Base1", "Base2"} == {r.target_id for r in dm_extends}
    dft_extends = find_relationships(rels, source_id=derived_from_template.id, rel_type="EXTENDS")
    assert len(dft_extends) == 1 and dft_extends[0].target_id == "TemplatedBase<int>"
    dm_method = find_code_entity_by_exact_temp_id(ces, "InheritanceTest::DerivedMultiple::derivedMultipleMethod()@36")
    assert dm_method
    assert len(find_call_sites(calls, calling_entity_temp_id=dm_method.id, called_name_expr="base2Method", at_line_0=38)) == 1
    dft_method = find_code_entity_by_exact_temp_id(ces, "InheritanceTest::DerivedFromTemplate::useTemplatedFeature()@45")
    assert dft_method
    assert len(find_call_sites(calls, calling_entity_temp_id=dft_method.id, called_name_expr="templatedBaseMethod", at_line_0=47)) == 1
