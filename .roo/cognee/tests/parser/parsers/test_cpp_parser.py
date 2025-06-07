# .roo/cognee/tests/parser/parsers/test_cpp_parser.py
import pytest
import asyncio
from pathlib import Path
from typing import List, Union, TYPE_CHECKING, Set, Tuple, AsyncGenerator, Type, Optional # Added Optional
import hashlib

from pydantic import BaseModel

pytestmark = pytest.mark.asyncio

try:
    # Updated imports to reflect parser yielding CodeEntity, Relationship, List[int]
    from src.parser.entities import CodeEntity, Relationship
    from src.parser.parsers.cpp_parser import CppParser
    from src.parser.parsers.treesitter_setup import get_language
    from src.parser.parsers.base_parser import BaseParser # For type hinting run_parser_fixture_func
    from src.parser.utils import logger, read_file_content
except ImportError as e:
    pytest.skip(f"Skipping C++ parser tests: Failed to import dependencies - {e}", allow_module_level=True)


TEST_DATA_DIR = Path(__file__).resolve().parent.parent / "test_data" / "cpp"
if not TEST_DATA_DIR.is_dir():
    pytest.skip(f"Test data directory not found: {TEST_DATA_DIR}", allow_module_level=True)

@pytest.fixture(scope="function")
def parser() -> CppParser:
    if get_language("cpp") is None:
        pytest.skip("C++ tree-sitter language not loaded or available.", allow_module_level=True)
    return CppParser()

# --- Test Helper: run_parser_and_collect_outputs ---
# This helper will simulate what the orchestrator does in terms of calling parse
# and collecting its distinct yield types.

class ParserYields(BaseModel):
    slice_lines: List[int] = []
    code_entities: List[CodeEntity] = []
    relationships: List[Relationship] = []

async def run_parser_and_collect_outputs(
    parser_instance: CppParser,
    test_file_path: Path,
    source_file_id: str # The ID orchestrator would generate (repo_id|relative_path)
) -> ParserYields:
    logger.info(f"Test Rig: Reading content for {test_file_path}")
    full_content_string = await read_file_content(str(test_file_path))
    if full_content_string is None:
        full_content_string = ""


    collected_yields = ParserYields()

    logger.info(f"Test Rig: Calling parser.parse for {source_file_id}")
    async for item in parser_instance.parse(source_file_id, full_content_string):
        if isinstance(item, list) and all(isinstance(i, int) for i in item):
            if collected_yields.slice_lines and item :
                 pytest.fail(f"Parser yielded slice_lines more than once. Previous: {collected_yields.slice_lines}, New: {item}")
            collected_yields.slice_lines = item
        elif isinstance(item, CodeEntity):
            collected_yields.code_entities.append(item)
        elif isinstance(item, Relationship):
            collected_yields.relationships.append(item)
        else:
            pytest.fail(f"Parser yielded unexpected type: {type(item)}")

    if not collected_yields.slice_lines and full_content_string.strip():
        logger.warning(f"Parser did not yield slice_lines for non-empty file {test_file_path}")
    elif collected_yields.slice_lines and full_content_string.strip() and 0 not in collected_yields.slice_lines:
        logger.warning(f"Parser yielded slice_lines {collected_yields.slice_lines} which does not include 0 for non-empty file {test_file_path}")


    return collected_yields

# --- Assertion Helper Functions ---
def find_code_entity_by_fqn_prefix(entities: List[CodeEntity], fqn_prefix: str) -> List[CodeEntity]:
    return [e for e in entities if e.id.split('@')[0] == fqn_prefix]

def find_code_entity_by_id(entities: List[CodeEntity], temp_id: str) -> CodeEntity | None:
    return next((e for e in entities if e.id == temp_id), None)

def find_relationships(relationships: List[Relationship], source_temp_id: Optional[str] = None, target_temp_id: Optional[str] = None, rel_type: Optional[str] = None) -> List[Relationship]:
    found = relationships
    if source_temp_id is not None:
        found = [r for r in found if r.source_id == source_temp_id]
    if target_temp_id is not None:
        found = [r for r in found if r.target_id == target_temp_id]
    if rel_type is not None:
        found = [r for r in found if r.type == rel_type]
    return found

# --- Test Cases ---

async def test_parse_empty_cpp_file(parser: CppParser, tmp_path: Path):
    empty_cpp_file = tmp_path / "empty.cpp"
    empty_cpp_file.write_text("")
    source_id = "test_repo|empty.cpp"

    yielded_data = await run_parser_and_collect_outputs(parser, empty_cpp_file, source_id)

    assert yielded_data.slice_lines == []
    assert len(yielded_data.code_entities) == 0
    assert len(yielded_data.relationships) == 0

async def test_parse_header_file_my_class_hpp(parser: CppParser):
    test_file = TEST_DATA_DIR / "my_class.hpp"
    source_id = "test_repo|my_class.hpp"

    data = await run_parser_and_collect_outputs(parser, test_file, source_id)

    assert data.slice_lines, "Should have slice_lines"
    assert 0 in data.slice_lines, "Slice lines should contain 0 for non-empty file"

    ces = data.code_entities
    found_ce_ids = [e.id for e in ces]
    logger.info(f"test_parse_header_file_my_class_hpp - Found CodeEntity IDs: {found_ce_ids}")

    assert len(ces) >= 5, f"Expected at least 5 CodeEntities, got {len(ces)}. Found: {found_ce_ids}"

    ns_processing_list = find_code_entity_by_fqn_prefix(ces, "Processing")
    assert len(ns_processing_list) == 1, f"Namespace 'Processing' not found or found multiple. Found IDs: {[e.id for e in ns_processing_list]}"
    ns_processing = ns_processing_list[0]
    assert ns_processing.type == "NamespaceDefinition"
    assert ns_processing.id.startswith("Processing@")

    cls_mdp_list = find_code_entity_by_fqn_prefix(ces, "Processing::MyDataProcessor")
    assert len(cls_mdp_list) == 1, f"Class 'Processing::MyDataProcessor' not found. Found IDs: {[e.id for e in cls_mdp_list]}"
    cls_mdp = cls_mdp_list[0]
    assert cls_mdp.type == "ClassDefinition"

    constructor_fqn_clever = "Processing::MyDataProcessor::MyDataProcessor(const std::string&)"
    constructor_list = find_code_entity_by_fqn_prefix(ces, constructor_fqn_clever)
    assert len(constructor_list) == 1, f"Constructor with FQN '{constructor_fqn_clever}' not found. Found matching MyDataProcessor constructors: {[e.id for e in ces if 'MyDataProcessor::MyDataProcessor' in e.id.split('@')[0]]}"
    constructor = constructor_list[0]
    assert constructor.type == "FunctionDefinition"

    destructor_fqn = "Processing::MyDataProcessor::~MyDataProcessor()"
    destructor_list = find_code_entity_by_fqn_prefix(ces, destructor_fqn)
    assert len(destructor_list) == 1, f"Destructor '{destructor_fqn}' not found. Found: {[e.id for e in ces if '~MyDataProcessor' in e.id.split('@')[0]]}"
    destructor = destructor_list[0]
    assert destructor.type == "FunctionDefinition"

    pv_fqn_clever = "Processing::MyDataProcessor::processVector(const std::vector<std::string>&)"
    process_vector_decl_list = find_code_entity_by_fqn_prefix(ces, pv_fqn_clever)
    assert len(process_vector_decl_list) == 1, f"Method declaration '{pv_fqn_clever}' not found. Found: {[e.id for e in ces if 'processVector' in e.id.split('@')[0]]}"
    process_vector_decl = process_vector_decl_list[0]
    assert process_vector_decl.type == "FunctionDeclaration"

    identity_fqn = "Processing::MyDataProcessor::identity(T)"
    identity_method_list = find_code_entity_by_fqn_prefix(ces, identity_fqn)
    assert len(identity_method_list) == 1, f"Template method '{identity_fqn}' not found. Found: {[e.id for e in ces if 'identity' in e.id.split('@')[0]]}"
    identity_method = identity_method_list[0]
    assert identity_method.type == "FunctionDefinition"

    hf_fqn = "Processing::helperFunction(int)"
    helper_func_decl_list = find_code_entity_by_fqn_prefix(ces, hf_fqn)
    assert len(helper_func_decl_list) == 1, f"Function declaration '{hf_fqn}' not found. Found: {[e.id for e in ces if 'helperFunction' in e.id.split('@')[0]]}"
    helper_func_decl = helper_func_decl_list[0]
    assert helper_func_decl.type == "FunctionDeclaration"

    string_include_list = find_code_entity_by_fqn_prefix(ces, "std::string")
    assert string_include_list and string_include_list[0].type == "ExternalReference", "<string> include not found as ExternalReference"
    string_include = string_include_list[0]

    vector_include_list = find_code_entity_by_fqn_prefix(ces, "std::vector")
    assert vector_include_list and vector_include_list[0].type == "ExternalReference", "<vector> include not found as ExternalReference"
    vector_include = vector_include_list[0]

    rels = data.relationships
    string_import_rel = find_relationships(rels, source_temp_id=source_id, target_temp_id=string_include.id, rel_type="IMPORTS")
    assert len(string_import_rel) == 1, f"IMPORTS relationship for std::string (target: {string_include.id}) not found"

    vector_import_rel = find_relationships(rels, source_temp_id=source_id, target_temp_id=vector_include.id, rel_type="IMPORTS")
    assert len(vector_import_rel) == 1, f"IMPORTS relationship for std::vector (target: {vector_include.id}) not found"


async def test_parse_simple_class_cpp(parser: CppParser):
    test_file = TEST_DATA_DIR / "simple_class.cpp"
    source_id = "test_repo|simple_class.cpp"
    data = await run_parser_and_collect_outputs(parser, test_file, source_id)

    ces = data.code_entities
    rels = data.relationships
    found_ce_ids = [e.id for e in ces]
    logger.info(f"test_parse_simple_class_cpp - Found CodeEntity IDs: {found_ce_ids}")

    iostream_ext_ref_list = find_code_entity_by_fqn_prefix(ces, "std::iostream")
    assert len(iostream_ext_ref_list) == 1 and iostream_ext_ref_list[0].type == "ExternalReference"
    iostream_ext_ref = iostream_ext_ref_list[0]
    assert find_relationships(rels, source_temp_id=source_id, target_temp_id=iostream_ext_ref.id, rel_type="IMPORTS")

    my_class_hpp_ext_ref_list = find_code_entity_by_fqn_prefix(ces, "my_class.hpp")
    assert len(my_class_hpp_ext_ref_list) == 1 and my_class_hpp_ext_ref_list[0].type == "ExternalReference"
    my_class_hpp_ext_ref = my_class_hpp_ext_ref_list[0]
    assert find_relationships(rels, source_temp_id=source_id, target_temp_id=my_class_hpp_ext_ref.id, rel_type="IMPORTS")

    using_std_directive_list = find_code_entity_by_fqn_prefix(ces, "directive_using_namespace::std")
    assert len(using_std_directive_list) == 1 and using_std_directive_list[0].type == "UsingDirective"
    using_std_directive = using_std_directive_list[0]
    assert find_relationships(rels, source_temp_id=source_id, target_temp_id=using_std_directive.id, rel_type="HAS_DIRECTIVE")
    assert find_relationships(rels, source_temp_id=using_std_directive.id, target_temp_id="std", rel_type="REFERENCES_NAMESPACE")

    ns_processing_list = find_code_entity_by_fqn_prefix(ces, "Processing")
    assert len(ns_processing_list) == 1 and ns_processing_list[0].type == "NamespaceDefinition"

    pv_impl_fqn_candidates = [
        "Processing::MyDataProcessor::processVector(const vector<string>&)",
        "Processing::MyDataProcessor::processVector(const std::vector<std::string>&)"
    ]
    process_vector_impl = None
    for fqn_candidate in pv_impl_fqn_candidates:
        found_list = find_code_entity_by_fqn_prefix(ces, fqn_candidate)
        if found_list:
            process_vector_impl = found_list[0]
            break
    assert process_vector_impl is not None, f"Method impl 'processVector' not found with expected FQNs. Check FQN parameter part. Found: {[e.id for e in ces if 'processVector' in e.id.split('@')[0]]}"
    assert process_vector_impl.type == "FunctionDefinition"

    helper_func_impl_fqn = "Processing::helperFunction(int)"
    helper_func_impl_list = find_code_entity_by_fqn_prefix(ces, helper_func_impl_fqn)
    assert len(helper_func_impl_list) == 1, f"Helper function impl '{helper_func_impl_fqn}' not found. Found: {[e.id for e in ces if 'helperFunction' in e.id.split('@')[0]]}"
    assert helper_func_impl_list[0].type == "FunctionDefinition"

    main_func_fqn = "main()"
    main_func_list = find_code_entity_by_fqn_prefix(ces, main_func_fqn)
    assert len(main_func_list) == 1, f"Main function '{main_func_fqn}' not found. Found: {[e.id for e in ces if 'main' in e.id.split('@')[0]]}"
    assert main_func_list[0].type == "FunctionDefinition"

async def test_complex_features_file(parser: CppParser):
    test_file = TEST_DATA_DIR / "complex_features.cpp"
    source_id = "test_repo|complex_features.cpp"
    data = await run_parser_and_collect_outputs(parser, test_file, source_id)

    ces = data.code_entities
    rels = data.relationships
    found_ce_ids = [e.id for e in ces]
    logger.info(f"test_complex_features_file - Found CodeEntity IDs: {len(found_ce_ids)} entities.")

    typedef_number_list = find_code_entity_by_fqn_prefix(ces, "Number")
    assert typedef_number_list and typedef_number_list[0].type == "TypeAlias", f"typedef 'Number' should be TypeAlias. Got: {typedef_number_list[0].type if typedef_number_list else 'Not Found'}" # CHANGED TypeDefinition to TypeAlias

    typedef_sv_list = find_code_entity_by_fqn_prefix(ces, "StringVector")
    assert typedef_sv_list and typedef_sv_list[0].type == "TypeAlias", f"TypeAlias StringVector not found. Found: {[e.id for e in typedef_sv_list if e.id.startswith('StringVector@')]}"

    ns_testns_list = find_code_entity_by_fqn_prefix(ces, "TestNS")
    assert ns_testns_list and ns_testns_list[0].type == "NamespaceDefinition"

    ns_innerns_list = find_code_entity_by_fqn_prefix(ces, "TestNS::InnerNS")
    assert ns_innerns_list and ns_innerns_list[0].type == "NamespaceDefinition"

    anon_func_list = find_code_entity_by_fqn_prefix(ces, "anonymous::anonNSFunction()")
    assert anon_func_list and anon_func_list[0].type == "FunctionDefinition"

    mcc_constructor_fqn = "MyComplexClass::MyComplexClass(std::string)"
    mcc_constructor_list = find_code_entity_by_fqn_prefix(ces, mcc_constructor_fqn)
    assert mcc_constructor_list and mcc_constructor_list[0].type == "FunctionDefinition", f"FQN {mcc_constructor_fqn} not found. Check param. Found: {[e.id for e in ces if 'MyComplexClass::MyComplexClass' in e.id.split('@')[0]]}"

    mcc_destructor_fqn = "MyComplexClass::~MyComplexClass()"
    mcc_destructor_list = find_code_entity_by_fqn_prefix(ces, mcc_destructor_fqn)
    assert mcc_destructor_list and mcc_destructor_list[0].type == "FunctionDefinition"

    mcc_virtual_fqn = "MyComplexClass::virtualMethod()"
    mcc_virtual_list = find_code_entity_by_fqn_prefix(ces, mcc_virtual_fqn)
    assert mcc_virtual_list and mcc_virtual_list[0].type == "FunctionDefinition"

    mcc_deleted_fqn = "MyComplexClass::deletedMethod()"
    mcc_deleted_list = find_code_entity_by_fqn_prefix(ces, mcc_deleted_fqn)
    assert mcc_deleted_list and mcc_deleted_list[0].type == "FunctionDefinition"

    mcc_op_plus_fqn = "MyComplexClass::operator+(const MyComplexClass&)"
    mcc_op_plus_list = find_code_entity_by_fqn_prefix(ces, mcc_op_plus_fqn)
    assert mcc_op_plus_list and mcc_op_plus_list[0].type == "FunctionDefinition", f"FQN {mcc_op_plus_fqn} not found. Found: {[e.id for e in ces if 'MyComplexClass::operator+' in e.id.split('@')[0]]}"

    dc_virtual_fqn = "TestNS::DerivedClass::virtualMethod()"
    dc_virtual_list = find_code_entity_by_fqn_prefix(ces, dc_virtual_fqn)
    assert dc_virtual_list and dc_virtual_list[0].type == "FunctionDefinition"

    derived_class_entity_list = find_code_entity_by_fqn_prefix(ces, "TestNS::DerivedClass")
    assert derived_class_entity_list and derived_class_entity_list[0].type == "ClassDefinition"
    derived_class_entity = derived_class_entity_list[0]

    extends_rels = find_relationships(rels, source_temp_id=derived_class_entity.id, rel_type="EXTENDS")
    assert len(extends_rels) == 1, "DerivedClass should have one EXTENDS relationship"
    assert extends_rels[0].target_id == "MyComplexClass", f"DerivedClass should extend MyComplexClass, got {extends_rels[0].target_id}"

    c_func_fqn = "c_style_function(int)"
    c_func_list = find_code_entity_by_fqn_prefix(ces, c_func_fqn)
    assert c_func_list and c_func_list[0].type == "FunctionDefinition"

    using_std_directive_list_complex = find_code_entity_by_fqn_prefix(ces, "directive_using_namespace::std")
    assert len(using_std_directive_list_complex) == 1 and using_std_directive_list_complex[0].type == "UsingDirective"

    main_complex_fqn = "main()"
    main_complex_list = find_code_entity_by_fqn_prefix(ces, main_complex_fqn)
    assert main_complex_list and main_complex_list[0].type == "FunctionDefinition"
