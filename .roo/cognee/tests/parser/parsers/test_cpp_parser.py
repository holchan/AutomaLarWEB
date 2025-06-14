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
from src.parser.utils import logger

# --- Imports from other test utility modules ---
# Use absolute imports from the 'tests' directory, which is on pythonpath
from tests.conftest import ParserTestOutput
from tests.shared_test_utils import (
    load_test_file_content,
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

# --- Test Cases (Only showing the start, the rest of the test functions remain the same) ---
@pytest.mark.parametrize("filename, expected_slice_lines, expect_entities, expect_rels, expect_calls", [
    ("empty_file.cpp", [], False, False, False),
    ("blank_file.cpp", [], False, False, False),
    ("comments_only_file.cpp", [0], False, False, False),
])
async def test_parse_empty_and_comment_files(
    cpp_parser: CppParser,
    parse_file_and_collect_output: Any, # Fixture from tests.conftest, injected by pytest
    filename: str,
    expected_slice_lines: List[int],
    expect_entities: bool,
    expect_rels: bool,
    expect_calls: bool
):
    test_file_path = TEST_FILES_DIR / filename
    file_content = await load_test_file_content(test_file_path) # From tests.shared_test_utils
    # Construct source_id; ensuring it's platform-independent for path separators if needed
    # For consistency, let's always use '/' for the path part in source_id
    path_part_in_id = filename # Since test_data/cpp is now flat
    source_id = f"test_repo|{path_part_in_id.replace(os.path.sep, '/')}"


    data: ParserTestOutput = await parse_file_and_collect_output( # Using the fixture
        cpp_parser,
        source_id,
        file_content,
        test_file_path
    )

    assert data.slice_lines == expected_slice_lines, f"Slice lines mismatch for {filename}"
    assert bool(data.code_entities) == expect_entities, f"Code entities expectation mismatch for {filename}"
    assert bool(data.relationships) == expect_rels, f"Relationships expectation mismatch for {filename}"
    assert bool(data.call_site_references) == expect_calls, f"Call sites expectation mismatch for {filename}"


async def test_parse_comments_with_include(cpp_parser: CppParser, parse_file_and_collect_output: Any):
    filename = "comments_with_include.cpp"
    test_file_path = TEST_FILES_DIR / filename
    file_content = await load_test_file_content(test_file_path)
    source_id = f"test_repo|{filename.replace(os.path.sep, '|')}"
    data: ParserTestOutput = await parse_file_and_collect_output(cpp_parser, source_id, file_content, test_file_path)

    assert data.slice_lines == [0, 2], f"Actual slice_lines: {data.slice_lines}"
    assert len(data.code_entities) == 1
    ext_ref = find_code_entity_by_exact_temp_id(data.code_entities, "std::iostream@2")
    assert ext_ref and ext_ref.type == "ExternalReference" and ext_ref.snippet_content == "std::iostream"
    assert len(data.relationships) == 1
    assert find_relationships(data.relationships, source_id=source_id, target_id="std::iostream@2", rel_type="IMPORTS")
    assert not data.call_site_references

async def test_parse_closely_packed_definitions(cpp_parser: CppParser, parse_file_and_collect_output: Any):
    filename = "closely_packed_definitions.cpp"
    test_file_path = TEST_FILES_DIR / filename
    file_content = await load_test_file_content(test_file_path)
    source_id = f"test_repo|{filename.replace(os.path.sep, '|')}"
    data: ParserTestOutput = await parse_file_and_collect_output(cpp_parser, source_id, file_content, test_file_path)

    expected_slices = sorted(list(set([0, 1, 2, 3, 4])))
    assert data.slice_lines == expected_slices, f"Actual slice_lines: {data.slice_lines}"
    ces = data.code_entities
    assert len(ces) == 7
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
    file_content = await load_test_file_content(test_file_path)
    source_id = f"test_repo|{filename.replace(os.path.sep, '|')}"
    data: ParserTestOutput = await parse_file_and_collect_output(cpp_parser, source_id, file_content, test_file_path)

    expected_slices = sorted(list(set([0, 2, 3, 5, 6, 7, 10])))
    assert data.slice_lines == expected_slices, f"Actual slice_lines: {data.slice_lines}"
    ces = data.code_entities
    assert len(ces) == 6
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
    file_content = await load_test_file_content(test_file_path)
    source_id = f"test_repo|{filename.replace(os.path.sep, '|')}"
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
    assert find_code_entity_by_exact_temp_id(ces, "Processing::MyDataProcessor::identity(T)@24").type == "FunctionDefinition"
    assert find_code_entity_by_exact_temp_id(ces, "Processing::MyDataProcessor::identity(T)@25").type == "FunctionDefinition"
    assert find_code_entity_by_exact_temp_id(ces, "Processing::helperFunction(int)@29").type == "FunctionDeclaration"
    assert not data.call_site_references

async def test_parse_simple_class_cpp(cpp_parser: CppParser, parse_file_and_collect_output: Any):
    filename = "simple_class.cpp"
    test_file_path = TEST_FILES_DIR / filename
    if not test_file_path.exists(): pytest.skip(f"Test file {test_file_path} not found.")
    file_content = await load_test_file_content(test_file_path)
    source_id = f"test_repo|{filename.replace(os.path.sep, '|')}"
    data: ParserTestOutput = await parse_file_and_collect_output(cpp_parser, source_id, file_content, test_file_path)

    ces, rels, calls = data.code_entities, data.relationships, data.call_site_references
    expected_slices = sorted(list(set([0, 1, 2, 3, 6, 8, 11, 19, 26]))) # Corrected based on file structure
    assert data.slice_lines == expected_slices, f"Actual slice_lines: {data.slice_lines}"

    assert find_code_entity_by_exact_temp_id(ces, "std::iostream@0")
    assert find_code_entity_by_exact_temp_id(ces, "std::vector@1") # Added
    assert find_code_entity_by_exact_temp_id(ces, "std::string@2") # Added
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
    file_content = await load_test_file_content(test_file_path)
    source_id = f"test_repo|{filename.replace(os.path.sep, '|')}"

    data: ParserTestOutput = await parse_file_and_collect_output(cpp_parser, source_id, file_content, test_file_path)
    ces, rels, calls = data.code_entities, data.relationships, data.call_site_references
    logger.info(f"Complex Features Test: Found {len(ces)} CEs, {len(rels)} Rels, {len(calls)} CallSites.")

    # Log all TypeAlias entities found for this file
    logger.info(f"--- TypeAlias CodeEntities found in {filename} ---")
    found_any_funcptr_like = False
    for ce in ces:
        if ce.type == "TypeAlias":
            logger.info(f"TypeAlias Candidate: ID='{ce.id}', Snippet='{ce.snippet_content.strip()}'")
            if "FuncPtr" in ce.id or "FuncPtr" in ce.snippet_content:
                found_any_funcptr_like = True
    if not found_any_funcptr_like:
        logger.warning(f"NO TypeAlias entity containing 'FuncPtr' was found in the parser output for {filename}.")
    logger.info(f"----------------------------------------------------")


    # Slice Lines Assertion - Use the exact list from the parser's successful output
    expected_slices = sorted(list(set([
        0, 1, 2, 3, 4, 6, 8, 10, 13, 14, 15, 20, 25, 31, 33, 38, 43, 44, 45, 49, 50, 56,
        61, 65, 69, 73, 77, 81, 83, 89, 93, 98, 99, 101, 105, 110, 117, 127, 132, 134
    ])))
    assert data.slice_lines == expected_slices, f"Slice lines mismatch. Actual: {data.slice_lines}"

    assert find_code_entity_by_exact_temp_id(ces, "ForwardDeclaredClass@6")
    assert find_code_entity_by_exact_temp_id(ces, "Number@8").type == "TypeAlias"

    # THE FAILING ASSERTION:
    func_ptr_entity = find_code_entity_by_exact_temp_id(ces, "FuncPtr(int)@9")
    assert func_ptr_entity is not None, "CodeEntity for 'FuncPtr(int)@9' not found."
    assert func_ptr_entity.type == "TypeAlias"


    assert find_code_entity_by_exact_temp_id(ces, "StringVector@10").type == "TypeAlias"
    # ... (rest of your assertions, they are likely fine if the line numbers are correct) ...
    # ... (ensure all line numbers in subsequent assertions are correct 0-indexed from raw file) ...

    assert find_code_entity_by_exact_temp_id(ces, "TestNS@12")
    assert find_code_entity_by_exact_temp_id(ces, "TestNS::InnerNS@13")
    assert find_code_entity_by_exact_temp_id(ces, "TestNS::InnerNS::innerFunction()@14")
    assert find_code_entity_by_exact_temp_id(ces, "TestNS::DataContainer@19")
    assert find_code_entity_by_exact_temp_id(ces, "TestNS::namespacedFunction(const TestNS::DataContainer&)@24") or \
           find_code_entity_by_exact_temp_id(ces, "TestNS::namespacedFunction(const DataContainer&)@24")
    assert find_code_entity_by_exact_temp_id(ces, "anonymous@30")
    assert find_code_entity_by_exact_temp_id(ces, "anonymous::anonNSFunction()@32")
    assert find_code_entity_by_exact_temp_id(ces, "SimpleStruct@37")
    assert find_code_entity_by_exact_temp_id(ces, "UnscopedEnum@42")
    scoped_enum = find_code_entity_by_exact_temp_id(ces, "TestNS::ScopedEnum@44")
    assert scoped_enum and scoped_enum.type == "EnumDefinition"
    assert find_code_entity_by_exact_temp_id(ces, "createInitializedArray(T)@48")
    assert find_code_entity_by_exact_temp_id(ces, "createInitializedArray(T)@49")
    assert find_code_entity_by_exact_temp_id(ces, "MyComplexClass@55")
    assert find_code_entity_by_exact_temp_id(ces, "MyComplexClass::MyComplexClass(std::string)@60")
    assert find_code_entity_by_exact_temp_id(ces, "MyComplexClass::~MyComplexClass()@64")
    assert find_code_entity_by_exact_temp_id(ces, "MyComplexClass::virtualMethod()@68")
    assert find_code_entity_by_exact_temp_id(ces, "MyComplexClass::constMethod()@72")
    assert find_code_entity_by_exact_temp_id(ces, "MyComplexClass::staticMethod()@76")
    assert find_code_entity_by_exact_temp_id(ces, "MyComplexClass::deletedMethod()@80")
    assert find_code_entity_by_exact_temp_id(ces, "MyComplexClass::operator+(const MyComplexClass&)@82")
    friend_decl = find_code_entity_by_exact_temp_id(ces, "MyComplexClass::friendFunction(MyComplexClass&)@88")
    assert friend_decl and friend_decl.type == "FunctionDeclaration"
    assert find_code_entity_by_exact_temp_id(ces, "friendFunction(MyComplexClass&)@92")
    derived_cls = find_code_entity_by_exact_temp_id(ces, "TestNS::DerivedClass@98")
    assert derived_cls and derived_cls.type == "ClassDefinition"
    assert find_relationships(rels, source_id=derived_cls.id, target_id="MyComplexClass", rel_type="EXTENDS")
    assert find_code_entity_by_exact_temp_id(ces, "TestNS::DerivedClass::DerivedClass(std::string)@100")
    assert find_code_entity_by_exact_temp_id(ces, "TestNS::DerivedClass::virtualMethod()@104")
    assert find_code_entity_by_exact_temp_id(ces, "TestNS::DerivedClass::anotherVirtualMethod()@109")
    assert find_code_entity_by_exact_temp_id(ces, "useLambda()@116")
    assert find_code_entity_by_exact_temp_id(ces, "c_style_function(int)@127")
    using_directive = find_code_entity_by_exact_temp_id(ces, "using_namespace_directive_referencing::std@131")
    assert using_directive and using_directive.type == "UsingDirective"
    main_func = find_code_entity_by_exact_temp_id(ces, "main()@133")
    assert main_func and main_func.type == "FunctionDefinition"
    main_func_temp_id = main_func.id

    assert len(find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="MyComplexClass::staticMethod", at_line_0=139)) == 1
    op_plus_obj_call = find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="operator+", at_line_0=141)
    assert len(op_plus_obj_call) == 1 and op_plus_obj_call[0].argument_count == 2
    constructor_call_in_expr = find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="MyComplexClass", arg_count=1, at_line_0=141)
    assert len(constructor_call_in_expr) == 1 and constructor_call_in_expr[0].raw_arg_text == "\"Obj2_Added\""
    assert len(find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="anonNSFunction", at_line_0=146)) == 1
    call_namespaced = find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="TestNS::namespacedFunction", at_line_0=150)
    assert len(call_namespaced) == 1 and call_namespaced[0].raw_arg_text == "dc"
    assert len(find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="derived_obj.virtualMethod", at_line_0=154)) == 1
    assert len(find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="useLambda", at_line_0=161)) == 1
    inner_func = find_code_entity_by_exact_temp_id(ces, "TestNS::InnerNS::innerFunction()@14")
    assert inner_func
    assert len(find_call_sites(calls, calling_entity_temp_id=inner_func.id, called_name_expr="operator<<", at_line_0=15)) >= 1

async def test_parse_calls_specific(cpp_parser: CppParser, parse_file_and_collect_output: Any):
    filename = "calls_specific.cpp"
    test_file_path = TEST_FILES_DIR / filename
    if not test_file_path.exists(): pytest.skip(f"Test file {test_file_path} not found.")
    file_content = await load_test_file_content(test_file_path)
    source_id = f"test_repo|{filename.replace(os.path.sep, '|')}"
    data: ParserTestOutput = await parse_file_and_collect_output(cpp_parser, source_id, file_content, test_file_path)
    ces, calls = data.code_entities, data.call_site_references

    # Raw 0-indexed lines from calls_specific.cpp
    main_demo_func = find_code_entity_by_exact_temp_id(ces, "main_calls_demo(int,char*[])@70")
    assert main_demo_func
    main_demo_func_id = main_demo_func.id

    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="global_function_no_args", at_line_0=71)
    csr1 = find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="global_function_with_args", at_line_0=72)
    assert len(csr1) == 1 and csr1[0].raw_arg_text == "10, \"hello from main\""
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="CallTestNS::a_namespaced_function", at_line_0=74)
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="func_ptr", at_line_0=77)
    csr_raw_ptr = find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, at_line_0=80)
    assert len(csr_raw_ptr) == 1 and (csr_raw_ptr[0].called_name_expr == "raw_func_ptr" or csr_raw_ptr[0].called_name_expr == "(*raw_func_ptr)")
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="callable_struct_instance", at_line_0=83)
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="tester_obj.simple_member_method", at_line_0=86)
    csr_new_tester = find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="MemberCallTester", at_line_0=88)
    assert len(csr_new_tester) == 1 and csr_new_tester[0].raw_arg_text == "\"PtrObj\""
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="tester_ptr->another_member_method", at_line_0=89)
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="MemberCallTester::static_method_target", at_line_0=91)
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="MemberCallTester::static_method_caller", at_line_0=92)
    csr_template_expl = find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, at_line_0=95)
    assert len(csr_template_expl) == 1 and csr_template_expl[0].called_name_expr.startswith("CallTestNS::generic_processor")
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="CallTestNS::generic_processor", at_line_0=96)
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="tester_obj.get_vector", at_line_0=98)
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="my_vec.push_back", at_line_0=99)
    assert len(find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="Processing::MyDataProcessor", at_line_0=101)) == 0
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="processor_ext.processVector", at_line_0=103)
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="operator+", at_line_0=106)
    assert len(find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="operator<<", at_line_0=107)) >= 1
    assert len(find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="operator delete", at_line_0=109)) == 1
    simple_method = find_code_entity_by_exact_temp_id(ces, "MemberCallTester::simple_member_method(int)@49")
    assert simple_method
    assert len(find_call_sites(calls, calling_entity_temp_id=simple_method.id, called_name_expr="this->another_member_method", at_line_0=51)) == 1
    assert len(find_call_sites(calls, calling_entity_temp_id=simple_method.id, called_name_expr="global_function_no_args", at_line_0=52)) == 1

async def test_parse_inheritance_variations(cpp_parser: CppParser, parse_file_and_collect_output: Any):
    filename = "inheritance_variations.hpp"
    test_file_path = TEST_FILES_DIR / filename
    if not test_file_path.exists(): pytest.skip(f"Test file {test_file_path} not found.")
    file_content = await load_test_file_content(test_file_path)
    source_id = f"test_repo|{filename.replace(os.path.sep, '|')}"
    data: ParserTestOutput = await parse_file_and_collect_output(cpp_parser, source_id, file_content, test_file_path)
    ces, rels, calls = data.code_entities, data.relationships, data.call_site_references

    expected_slices = sorted(list(set([
        0, 1, 3, 5, 7, 8, 9, 12, 15, 18, 19, 22, 26, 28, 29, 33, 35, 36, 43, 45, 51, 55, 56
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
