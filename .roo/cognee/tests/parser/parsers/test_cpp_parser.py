# .roo/cognee/tests/parser/parsers/test_cpp_parser.py
import pytest
import asyncio
from pathlib import Path
from typing import List, Union, Set, Tuple, AsyncGenerator, Type, Optional, Dict, Any
import os

from pydantic import BaseModel

pytestmark = pytest.mark.asyncio

try:
    from src.parser.entities import CodeEntity, Relationship, CallSiteReference, ParserOutput
    from src.parser.parsers.cpp_parser import CppParser
    from src.parser.parsers.treesitter_setup import get_language
    from src.parser.utils import logger, read_file_content
except ImportError as e:
    print(f"DEBUG: test_cpp_parser.py import error: {e}")
    pytest.skip(f"Skipping C++ parser tests: Failed to import dependencies - {e}", allow_module_level=True)


TEST_DATA_BASE_DIR = Path(__file__).resolve().parent.parent / "test_data" / "cpp"
SLICING_DATA_DIR = TEST_DATA_BASE_DIR / "slicing"

if not TEST_DATA_BASE_DIR.is_dir():
    pytest.skip(f"Test data base directory not found: {TEST_DATA_BASE_DIR}", allow_module_level=True)


class ParserTestOutput(BaseModel):
    slice_lines: List[int] = []
    code_entities: List[CodeEntity] = []
    relationships: List[Relationship] = []
    call_site_references: List[CallSiteReference] = []

async def _actual_run_parser_logic(
    parser_instance: CppParser,
    source_file_id: str,
    file_content: str
) -> ParserTestOutput:
    collected_slice_lines: List[int] = []
    slice_lines_yielded_count = 0
    collected_code_entities: List[CodeEntity] = []
    collected_relationships: List[Relationship] = []
    collected_call_sites: List[CallSiteReference] = []

    parser_instance.current_source_file_id_for_debug = None

    async for item in parser_instance.parse(source_file_id, file_content):
        if isinstance(item, list) and all(isinstance(i, int) for i in item):
            slice_lines_yielded_count += 1
            if slice_lines_yielded_count > 1:
                pytest.fail(f"Parser yielded slice_lines more than once for {source_file_id}. First: {collected_slice_lines}, New: {item}")
            collected_slice_lines = item
        elif isinstance(item, CodeEntity):
            collected_code_entities.append(item)
        elif isinstance(item, Relationship):
            collected_relationships.append(item)
        elif isinstance(item, CallSiteReference):
            collected_call_sites.append(item)
        else:
            pytest.fail(f"Parser yielded unexpected type: {type(item)} for {source_file_id}. Item: {item}")

    if not file_content.strip():
        if slice_lines_yielded_count == 0 and not collected_slice_lines :
             pass
        elif collected_slice_lines != []:
             pytest.fail(f"Parser yielded non-empty slice_lines for empty/blank file: {source_file_id}, got: {collected_slice_lines}")
    else:
        if slice_lines_yielded_count == 0 and not collected_slice_lines:
             pytest.fail(f"Parser did not yield slice_lines for non-empty file: {source_file_id}")
        elif not collected_slice_lines or (0 not in collected_slice_lines and collected_slice_lines != []):
             pytest.fail(f"Parser slice_lines for non-empty file {source_file_id} must exist and start with 0 if not empty. Got: {collected_slice_lines}")


    return ParserTestOutput(
        slice_lines=collected_slice_lines,
        code_entities=collected_code_entities,
        relationships=collected_relationships,
        call_site_references=collected_call_sites
    )

@pytest.fixture(scope="function")
def run_parser_helper_fixture():
    return _actual_run_parser_logic

@pytest.fixture(scope="function")
def parser() -> CppParser:
    if get_language("cpp") is None:
        pytest.skip("C++ tree-sitter language not loaded or available.", allow_module_level=True)
    return CppParser()

async def load_test_file_content(file_path: Path) -> str:
    if not file_path.is_file():
        logger.error(f"Test data file not found during load_test_file_content: {file_path}")
        return ""
    content = await read_file_content(str(file_path))
    if content:
        lines = content.splitlines()
        if lines and lines[0].startswith("// .roo/cognee/tests/parser/test_data/cpp/"):
            if len(lines) > 1:
                new_content = "\n".join(lines[1:])
                return new_content
            return ""
    return content if content is not None else ""


def find_code_entity_by_id_prefix(entities: List[CodeEntity], id_prefix: str) -> List[CodeEntity]:
    return [e for e in entities if e.id.split('@')[0].startswith(id_prefix)]

def find_code_entity_by_exact_temp_id(entities: List[CodeEntity], temp_id: str) -> Optional[CodeEntity]:
    found = [e for e in entities if e.id == temp_id]
    if not found: return None
    if len(found) > 1:
        logger.warning(f"Found multiple CEs for temp_id '{temp_id}': {[e.id for e in found]}")
    return found[0]

def find_relationships(
    relationships: List[Relationship],
    source_id: Optional[str] = None,
    target_id: Optional[str] = None,
    rel_type: Optional[str] = None
) -> List[Relationship]:
    found = relationships
    if source_id is not None: found = [r for r in found if r.source_id == source_id]
    if target_id is not None: found = [r for r in found if r.target_id == target_id]
    if rel_type is not None: found = [r for r in found if r.type == rel_type]
    return found

def find_call_sites(
    call_sites: List[CallSiteReference],
    calling_entity_fqn_prefix: Optional[str] = None,
    calling_entity_temp_id: Optional[str] = None,
    called_name_expr: Optional[str] = None,
    at_line_0: Optional[int] = None,
    arg_count: Optional[int] = None,
) -> List[CallSiteReference]:
    found = call_sites
    if calling_entity_fqn_prefix is not None:
        found = [cs for cs in found if cs.calling_entity_temp_id.split('@')[0].startswith(calling_entity_fqn_prefix)]
    if calling_entity_temp_id is not None:
        found = [cs for cs in found if cs.calling_entity_temp_id == calling_entity_temp_id]
    if called_name_expr is not None:
        found = [cs for cs in found if cs.called_name_expr == called_name_expr]
    if at_line_0 is not None:
        found = [cs for cs in found if cs.line_of_call_0_indexed == at_line_0]
    if arg_count is not None:
        found = [cs for cs in found if cs.argument_count == arg_count]
    return found

# --- SLICING EDGE CASES ---
@pytest.mark.parametrize("sub_dir, filename, expected_slice_lines, expect_entities, expect_rels, expect_calls", [
    ("slicing", "empty_file.cpp", [0], False, False, False),
    ("slicing", "blank_file.cpp", [], False, False, False),
    ("slicing", "comments_only_file.cpp", [0], False, False, False),
])
async def test_parse_empty_and_comment_files(parser: CppParser, run_parser_helper_fixture: Any, sub_dir: str, filename: str, expected_slice_lines: List[int], expect_entities: bool, expect_rels: bool, expect_calls: bool):
    test_file_path = TEST_DATA_BASE_DIR / sub_dir / filename
    file_content = await load_test_file_content(test_file_path)
    s_id_path_part = os.path.join(sub_dir, filename).replace(os.path.sep, '|')
    source_id = f"test_repo|{s_id_path_part}"

    data = await run_parser_helper_fixture(parser, source_id, file_content)

    assert data.slice_lines == expected_slice_lines, f"Slice lines mismatch for {filename}"
    assert bool(data.code_entities) == expect_entities, f"Code entities expectation mismatch for {filename}"
    assert bool(data.relationships) == expect_rels, f"Relationships expectation mismatch for {filename}"
    assert bool(data.call_site_references) == expect_calls, f"Call sites expectation mismatch for {filename}"


async def test_parse_comments_with_include(parser: CppParser, run_parser_helper_fixture: Any):
    filename = "comments_with_include.cpp"
    test_file_path = SLICING_DATA_DIR / filename
    file_content = await load_test_file_content(test_file_path)
    source_id = f"test_repo|slicing|{filename}"
    data = await run_parser_helper_fixture(parser, source_id, file_content)

    # If header stripped, content starts:
    # // This is a top-level comment. Line 0.  (line 0 for parser)
    #                                         (line 1 for parser)
    # #include <iostream>                     (line 2 for parser)
    # Parser log shows include is at line 2 for this file content.
    assert data.slice_lines == [0, 2], f"Actual slice_lines: {data.slice_lines}"

    assert len(data.code_entities) == 1, f"Found CEs: {[e.id for e in data.code_entities]}"
    ext_ref = find_code_entity_by_exact_temp_id(data.code_entities, "std::iostream@2")
    assert ext_ref, "std::iostream@2 ExternalReference not found"
    assert ext_ref.type == "ExternalReference"
    assert ext_ref.snippet_content == "std::iostream"

    assert len(data.relationships) == 1
    imp_rel = find_relationships(data.relationships, source_id=source_id, target_id="std::iostream@2", rel_type="IMPORTS")
    assert len(imp_rel) == 1
    assert not data.call_site_references

async def test_parse_closely_packed_definitions(parser: CppParser, run_parser_helper_fixture: Any):
    filename = "closely_packed_definitions.cpp"
    test_file_path = SLICING_DATA_DIR / filename
    file_content = await load_test_file_content(test_file_path)
    source_id = f"test_repo|slicing|{filename}"
    data = await run_parser_helper_fixture(parser, source_id, file_content)

    # 0-indexed after .roo header strip:
    # struct Point2D @0; namespace TinyNS @1 (Helper@1, assist@1); enum class Color @2;
    # void standaloneFunction @3; typedef Vec2D @4;
    expected_slices = sorted(list(set([0, 1, 2, 3, 4])))
    assert data.slice_lines == expected_slices, f"Actual slice_lines: {data.slice_lines}"

    ces = data.code_entities
    assert len(ces) == 7, f"Expected 7 CodeEntities, got {len(ces)}. Found: {[e.id for e in ces]}"

    assert find_code_entity_by_exact_temp_id(ces, "Point2D@0")
    assert find_code_entity_by_exact_temp_id(ces, "TinyNS@1")
    helper_class = find_code_entity_by_exact_temp_id(ces, "TinyNS::Helper@1")
    assert helper_class and helper_class.type == "ClassDefinition"
    assist_decl = find_code_entity_by_exact_temp_id(ces, "TinyNS::Helper::assist()@1")
    assert assist_decl and assist_decl.type == "FunctionDeclaration"
    assert find_code_entity_by_exact_temp_id(ces, "Color@2")
    assert find_code_entity_by_exact_temp_id(ces, "standaloneFunction(int)@3")
    vec2d_alias = find_code_entity_by_exact_temp_id(ces, "Vec2D@4")
    assert vec2d_alias and vec2d_alias.type == "TypeAlias"


async def test_parse_forward_declarations(parser: CppParser, run_parser_helper_fixture: Any):
    filename = "forward_declarations.hpp"
    test_file_path = SLICING_DATA_DIR / filename
    file_content = await load_test_file_content(test_file_path)
    source_id = f"test_repo|slicing|{filename}"
    data = await run_parser_helper_fixture(parser, source_id, file_content)

    # After .roo header strip, 0-indexed: #pragma once @0, MyForwardClass @2, MyForwardStruct @3,
    # namespace FwdNS @5, enum MyFwdEnum @6, class AnotherFwdClass @7, void fwd_declared_func @10
    expected_slices = sorted(list(set([0, 2, 3, 5, 6, 7, 10])))
    assert data.slice_lines == expected_slices, f"Actual slice_lines: {data.slice_lines}"

    ces = data.code_entities
    assert len(ces) == 6, f"Expected 6 CEs, got {len(ces)}, IDs: {[e.id for e in ces]}"

    mfc = find_code_entity_by_exact_temp_id(ces, "MyForwardClass@2")
    assert mfc and mfc.type == "ClassDefinition"

    mfs = find_code_entity_by_exact_temp_id(ces, "MyForwardStruct@3")
    assert mfs and mfs.type == "StructDefinition"

    ns_fwdns = find_code_entity_by_exact_temp_id(ces, "FwdNS@5")
    assert ns_fwdns and ns_fwdns.type == "NamespaceDefinition"

    mfe = find_code_entity_by_exact_temp_id(ces, "FwdNS::MyFwdEnum@6")
    assert mfe and mfe.type == "EnumDefinition"

    afc = find_code_entity_by_exact_temp_id(ces, "FwdNS::AnotherFwdClass@7")
    assert afc and afc.type == "ClassDefinition"

    fwd_func = find_code_entity_by_exact_temp_id(ces, "fwd_declared_func(int)@10")
    assert fwd_func and fwd_func.type == "FunctionDeclaration"


async def test_parse_my_class_hpp(parser: CppParser, run_parser_helper_fixture: Any):
    filename = "my_class.hpp"
    test_file_path = TEST_DATA_BASE_DIR / filename
    if not test_file_path.exists(): pytest.skip(f"Test file {test_file_path} not found.")
    file_content = await load_test_file_content(test_file_path)
    source_id = f"test_repo|{filename}"
    data = await run_parser_helper_fixture(parser, source_id, file_content)

    # After .roo header strip, 0-idx: #ifndef @0, #include <string> @2, #include <vector> @3, ns Processing @5, class MyDataProcessor @8,
    # ctor @14, dtor @17, processVector decl @20,
    # template<T> @23 (for template_declaration of identity)
    # T identity def @24 (inner function_definition of template)
    # helperFunction decl @28
    expected_slices = sorted(list(set([0, 2, 3, 5, 8, 14, 17, 20, 23, 24, 28])))
    assert data.slice_lines == expected_slices, f"Actual slice_lines: {data.slice_lines}"

    ces, rels = data.code_entities, data.relationships

    ext_ref_string = find_code_entity_by_exact_temp_id(ces, "std::string@2")
    assert ext_ref_string and ext_ref_string.type == "ExternalReference"
    assert find_relationships(rels, source_id=source_id, target_id="std::string@2", rel_type="IMPORTS")

    ext_ref_vector = find_code_entity_by_exact_temp_id(ces, "std::vector@3")
    assert ext_ref_vector and ext_ref_vector.type == "ExternalReference"
    assert find_relationships(rels, source_id=source_id, target_id="std::vector@3", rel_type="IMPORTS")

    assert find_code_entity_by_exact_temp_id(ces, "Processing@5")
    assert find_code_entity_by_exact_temp_id(ces, "Processing::MyDataProcessor@8")
    assert find_code_entity_by_exact_temp_id(ces, "Processing::MyDataProcessor::MyDataProcessor(const std::string&)@14")
    assert find_code_entity_by_exact_temp_id(ces, "Processing::MyDataProcessor::~MyDataProcessor()@17")

    pv_decl = find_code_entity_by_exact_temp_id(ces, "Processing::MyDataProcessor::processVector(const std::vector<std::string>&)@20")
    assert pv_decl and pv_decl.type == "FunctionDeclaration"

    identity_method_from_template_query = find_code_entity_by_exact_temp_id(ces, "Processing::MyDataProcessor::identity(T)@23")
    assert identity_method_from_template_query and identity_method_from_template_query.type == "FunctionDefinition"

    correct_fqn_identity_inner = find_code_entity_by_exact_temp_id(ces, "Processing::MyDataProcessor::identity(T)@24")
    assert correct_fqn_identity_inner and correct_fqn_identity_inner.type == "FunctionDefinition", \
        f"Inner func def of template not found with correct FQN@24. Found: {[e.id for e in ces if e.id.endswith('@24')]}"

    helper_decl = find_code_entity_by_exact_temp_id(ces, "Processing::helperFunction(int)@28")
    assert helper_decl and helper_decl.type == "FunctionDeclaration"

    assert not data.call_site_references


async def test_parse_simple_class_cpp(parser: CppParser, run_parser_helper_fixture: Any):
    filename = "simple_class.cpp"
    test_file_path = TEST_DATA_BASE_DIR / filename
    if not test_file_path.exists(): pytest.skip(f"Test file {test_file_path} not found.")
    file_content = await load_test_file_content(test_file_path)
    source_id = f"test_repo|{filename}"
    data = await run_parser_helper_fixture(parser, source_id, file_content)

    ces, rels, calls = data.code_entities, data.relationships, data.call_site_references

    # After .roo header strip: #include <iostream> @0, #include <vector> @1, #include <string> @2, #include "my_class.hpp" @3
    # using namespace std; @5 (after comment)
    # namespace Processing @7
    # void MyDataProcessor::processVector @10
    # int helperFunction @18
    # int main @25
    expected_slices = sorted(list(set([0, 1, 2, 3, 5, 7, 10, 18, 25])))
    assert data.slice_lines == expected_slices, f"Actual slice_lines: {data.slice_lines}"

    assert find_code_entity_by_exact_temp_id(ces, "std::iostream@0")
    assert find_code_entity_by_exact_temp_id(ces, "std::vector@1")
    assert find_code_entity_by_exact_temp_id(ces, "std::string@2")
    my_class_hpp_ref = find_code_entity_by_exact_temp_id(ces, "my_class.hpp@3")
    assert my_class_hpp_ref and my_class_hpp_ref.snippet_content == "my_class.hpp"

    directive_ce = find_code_entity_by_exact_temp_id(ces, "using_namespace_directive_referencing::std@5")
    assert directive_ce and directive_ce.type == "UsingDirective"
    assert directive_ce.snippet_content == "using namespace std;"
    assert find_relationships(rels, source_id=source_id, target_id=directive_ce.id, rel_type="HAS_DIRECTIVE")
    assert find_relationships(rels, source_id=directive_ce.id, target_id="std", rel_type="REFERENCES_NAMESPACE")

    pv_impl_fqn_options = [
        "Processing::MyDataProcessor::processVector(const std::vector<std::string>&)@10",
        "Processing::MyDataProcessor::processVector(const vector<string>&)@10"
    ]
    pv_impl = next((find_code_entity_by_exact_temp_id(ces, fqn) for fqn in pv_impl_fqn_options if find_code_entity_by_exact_temp_id(ces, fqn)), None)
    assert pv_impl and pv_impl.type == "FunctionDefinition", f"processVector impl not found. Checked: {pv_impl_fqn_options}. Found: {[e.id for e in ces if 'processVector' in e.id]}"

    hf_impl = find_code_entity_by_exact_temp_id(ces, "Processing::helperFunction(int)@18")
    assert hf_impl and hf_impl.type == "FunctionDefinition"

    main_func_list = find_code_entity_by_id_prefix(ces, "main()")
    assert len(main_func_list) == 1, f"Found main funcs: {[e.id for e in main_func_list]}"
    main_func_temp_id = main_func_list[0].id
    assert main_func_temp_id == "main()@25"

    # processor.processVector(items); is on line 28 (0-indexed after header strip)
    call_pv = find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="processor.processVector", at_line_0=28)
    assert len(call_pv) == 1, f"Call to processor.processVector not found. Got {len(call_pv)} calls. All calls from main: {[c.model_dump(exclude_none=True) for c in find_call_sites(calls, calling_entity_temp_id=main_func_temp_id)]}"
    if call_pv: assert call_pv[0].raw_arg_text=="items"

    # cout << "Helper result: " << Processing::helperFunction(5) << endl; is on line 30
    cout_calls_in_main = find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="operator<<", at_line_0=30)
    assert len(cout_calls_in_main) >= 1

    call_helper_in_main = find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="Processing::helperFunction", at_line_0=30)
    assert len(call_helper_in_main) == 1, f"Call to Processing::helperFunction not found. Got {len(call_helper_in_main)} calls."
    if call_helper_in_main : assert call_helper_in_main[0].argument_count == 1 and call_helper_in_main[0].raw_arg_text == "5"

    if pv_impl:
        pv_impl_temp_id = pv_impl.id
        # cout << "Processing C++ vector data..." << endl; on line 11 (0-indexed of actual content)
        cout_calls_in_pv_line11 = find_call_sites(calls, calling_entity_temp_id=pv_impl_temp_id, called_name_expr="operator<<", at_line_0=11)
        assert len(cout_calls_in_pv_line11) >= 1
        # cout << " - Item: " << item << endl; on line 13
        cout_calls_in_pv_line13 = find_call_sites(calls, calling_entity_temp_id=pv_impl_temp_id, called_name_expr="operator<<", at_line_0=13)
        assert len(cout_calls_in_pv_line13) >= 1


async def test_parse_complex_features(parser: CppParser, run_parser_helper_fixture: Any):
    filename = "complex_features.cpp"
    test_file_path = TEST_DATA_BASE_DIR / filename
    if not test_file_path.exists(): pytest.skip(f"Test file {test_file_path} not found.")
    file_content = await load_test_file_content(test_file_path)
    source_id = f"test_repo|{filename}"
    data = await run_parser_helper_fixture(parser, source_id, file_content)
    ces, rels, calls = data.code_entities, data.relationships, data.call_site_references
    logger.info(f"Complex Features: Found {len(ces)} CEs, {len(rels)} Rels, {len(calls)} CallSites.")

    actual_slices = data.slice_lines
    # 0-indexed from start of actual file content (after .roo header is stripped by load_test_file_content)
    # Use the actual slice log from the previous run to set the expectation.
    expected_key_slices_from_log = {0, 1, 2, 3, 4, 5, 8, 10, 11, 12, 13, 17, 18, 19, 23, 28, 35, 37, 43, 49, 50, 51, 56, 57, 64, 70, 75, 80, 85, 90, 95, 98, 104, 109, 115, 116, 118, 123, 128, 136, 147, 153, 155}
    assert set(actual_slices) == expected_key_slices_from_log, f"Slice lines mismatch for complex_features. Actual: {actual_slices}"

    assert find_code_entity_by_exact_temp_id(ces, "Number@10").type == "TypeAlias"
    derived_cls = find_code_entity_by_exact_temp_id(ces, "TestNS::DerivedClass@101")
    assert derived_cls, "TestNS::DerivedClass@101 not found"
    assert find_relationships(rels, source_id=derived_cls.id, target_id="MyComplexClass", rel_type="EXTENDS")

    main_func = find_code_entity_by_exact_temp_id(ces, "main()@138")
    assert main_func, "main()@138 not found"
    main_func_temp_id = main_func.id

    call_static = find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="MyComplexClass::staticMethod", at_line_0=144)
    assert len(call_static) == 1

    op_plus_calls = find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="operator+", at_line_0=147)
    assert len(op_plus_calls) == 1
    if op_plus_calls: assert op_plus_calls[0].argument_count == 2

    constructor_call_in_expr = find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="MyComplexClass", arg_count=1, at_line_0=147)
    if constructor_call_in_expr:
        assert constructor_call_in_expr[0].raw_arg_text == "\"Obj2_Added\""
    logger.info(f"DEBUG complex_features: constructor_call_in_expr for MyComplexClass(\"Obj2_Added\") found: {[c.model_dump(exclude_none=True) for c in constructor_call_in_expr]}")

    call_anon_func = find_call_sites(calls, calling_entity_temp_id=main_func_temp_id, called_name_expr="anonNSFunction", at_line_0=152)
    assert len(call_anon_func) == 1


async def test_parse_calls_specific(parser: CppParser, run_parser_helper_fixture: Any):
    filename = "calls_specific.cpp"
    test_file_path = TEST_DATA_BASE_DIR / filename
    if not test_file_path.exists(): pytest.skip(f"Test file {test_file_path} not found.")
    file_content = await load_test_file_content(test_file_path)
    source_id = f"test_repo|{filename}"
    data = await run_parser_helper_fixture(parser, source_id, file_content)

    ces, calls = data.code_entities, data.call_site_references
    logger.info(f"Calls Specific: Found {len(ces)} CEs, {len(data.relationships)} Rels, {len(calls)} CallSites.")

    # 0-indexed lines from calls_specific.cpp (after potential .roo header strip)
    main_demo_func = find_code_entity_by_exact_temp_id(ces, "main_calls_demo(int,char**)@59")
    assert main_demo_func, "main_calls_demo@59 function not found"
    main_demo_func_id = main_demo_func.id

    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="global_function_no_args", arg_count=0, at_line_0=61)
    csr1 = find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="global_function_with_args", arg_count=2, at_line_0=62)
    assert len(csr1) == 1 and csr1[0].raw_arg_text == "10, \"hello from main\""
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="CallTestNS::a_namespaced_function", arg_count=1, at_line_0=64)
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="func_ptr", arg_count=1, at_line_0=67)

    csr_raw_ptr = find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, at_line_0=70, arg_count=1)
    assert len(csr_raw_ptr) == 1 and (csr_raw_ptr[0].called_name_expr == "raw_func_ptr" or csr_raw_ptr[0].called_name_expr == "(*raw_func_ptr)")

    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="callable_struct_instance", arg_count=1, at_line_0=73)
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="tester_obj.simple_member_method", arg_count=1, at_line_0=76)

    csr_new_tester = find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="MemberCallTester", arg_count=1, at_line_0=79)
    assert len(csr_new_tester) == 1, f"Expected 'new MemberCallTester(...)' call. Found: {[c.model_dump_json() for c in csr_new_tester]}"
    if csr_new_tester: assert csr_new_tester[0].raw_arg_text == "\"PtrObj\""

    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="tester_ptr->another_member_method", arg_count=2, at_line_0=80)
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="MemberCallTester::static_method_target", arg_count=1, at_line_0=83)
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="MemberCallTester::static_method_caller", arg_count=0, at_line_0=84)

    csr_template_expl = find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, arg_count=1, at_line_0=87)
    assert len(csr_template_expl) == 1 and csr_template_expl[0].called_name_expr.startswith("CallTestNS::generic_processor")

    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="CallTestNS::generic_processor", arg_count=1, at_line_0=88)
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="tester_obj.get_vector", arg_count=0, at_line_0=90)
    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="my_vec.push_back", arg_count=1, at_line_0=91)

    constructor_call_decl = find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="Processing::MyDataProcessor", at_line_0=94)
    assert len(constructor_call_decl) == 0


    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="processor_ext.processVector", arg_count=1, at_line_0=96)

    assert find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="operator+", arg_count=2, at_line_0=99)

    cout_calls_main = find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="operator<<", at_line_0=100)
    assert len(cout_calls_main) >= 1

    delete_call = find_call_sites(calls, calling_entity_temp_id=main_demo_func_id, called_name_expr="operator delete", arg_count=1, at_line_0=103)
    assert len(delete_call) == 1

    simple_method = find_code_entity_by_exact_temp_id(ces, "MemberCallTester::simple_member_method(int)@42")
    assert simple_method, "simple_member_method@42 not found"
    simple_method_temp_id = simple_method.id

    call_internal_member = find_call_sites(calls, calling_entity_temp_id=simple_method_temp_id, called_name_expr="this->another_member_method", at_line_0=44)
    assert len(call_internal_member) == 1, f"Call to this->another_member_method not found. Caller ID: {simple_method_temp_id}"
    if call_internal_member: assert call_internal_member[0].argument_count == 2

    call_internal_global = find_call_sites(calls, calling_entity_temp_id=simple_method_temp_id, called_name_expr="global_function_no_args", at_line_0=45)
    assert len(call_internal_global) == 1, f"Call to global_function_no_args not found. Caller ID: {simple_method_temp_id}"
    if call_internal_global: assert call_internal_global[0].argument_count == 0


async def test_parse_inheritance_variations(parser: CppParser, run_parser_helper_fixture: Any):
    filename = "inheritance_variations.hpp"
    test_file_path = TEST_DATA_BASE_DIR / filename
    if not test_file_path.exists(): pytest.skip(f"Test file {test_file_path} not found.")
    file_content = await load_test_file_content(test_file_path)
    source_id = f"test_repo|{filename}"
    data = await run_parser_helper_fixture(parser, source_id, file_content)
    ces, rels, calls = data.code_entities, data.relationships, data.call_site_references

    # 0-indexed lines from file (after .roo header strip)
    # #pragma once @0
    # #include <string> @1
    # namespace InheritanceTest @4
    expected_slices = sorted(list(set([0, 1, 4, 6, 8, 9, 10, 14, 17, 20, 21, 24, 28, 30, 31, 35, 37, 38, 45, 47, 53, 57, 58])))
    assert data.slice_lines == expected_slices, f"Actual slice_lines: {data.slice_lines}"


    base1 = find_code_entity_by_exact_temp_id(ces, "InheritanceTest::Base1@6")
    assert base1, "Base1@6 not found"

    derived_single = find_code_entity_by_exact_temp_id(ces, "InheritanceTest::DerivedSingle@28")
    assert derived_single, "DerivedSingle@28 not found"

    derived_multiple = find_code_entity_by_exact_temp_id(ces, "InheritanceTest::DerivedMultiple@35")
    assert derived_multiple, "DerivedMultiple@35 not found"

    derived_from_template = find_code_entity_by_exact_temp_id(ces, "InheritanceTest::DerivedFromTemplate@45")
    assert derived_from_template, "DerivedFromTemplate@45 not found"

    assert find_relationships(rels, source_id=derived_single.id, target_id="Base1", rel_type="EXTENDS")
    dm_extends = find_relationships(rels, source_id=derived_multiple.id, rel_type="EXTENDS")
    assert len(dm_extends) == 2 and {"Base1", "Base2"} == {r.target_id for r in dm_extends}
    dft_extends = find_relationships(rels, source_id=derived_from_template.id, rel_type="EXTENDS")
    assert len(dft_extends) == 1 and dft_extends[0].target_id == "TemplatedBase<int>"

    dm_method = find_code_entity_by_exact_temp_id(ces, "InheritanceTest::DerivedMultiple::derivedMultipleMethod()@38")
    assert dm_method, "InheritanceTest::DerivedMultiple::derivedMultipleMethod()@38 not found"
    dm_method_id = dm_method.id

    # base2Method(); is on line 40
    call_base2_method = find_call_sites(calls, calling_entity_temp_id=dm_method_id, called_name_expr="base2Method", at_line_0=40)
    assert len(call_base2_method) == 1, f"Call to base2Method not found. Caller ID: {dm_method_id}"

    dft_method = find_code_entity_by_exact_temp_id(ces, "InheritanceTest::DerivedFromTemplate::useTemplatedFeature()@47")
    assert dft_method, "InheritanceTest::DerivedFromTemplate::useTemplatedFeature()@47 not found"
    dft_method_id = dft_method.id
    # templatedBaseMethod(200); is on line 49
    call_templated_base_method = find_call_sites(calls, calling_entity_temp_id=dft_method_id, called_name_expr="templatedBaseMethod", at_line_0=49)
    assert len(call_templated_base_method) == 1, f"Call to templatedBaseMethod not found. Caller ID: {dft_method_id}"
