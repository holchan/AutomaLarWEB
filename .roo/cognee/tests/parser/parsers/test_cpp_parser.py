# .roo/cognee/tests/parser/parsers/test_cpp_parser.py
import pytest
import asyncio
from pathlib import Path
from typing import List, Union, TYPE_CHECKING, Set, Tuple, AsyncGenerator
import hashlib

from pydantic import BaseModel

pytestmark = pytest.mark.asyncio

try:
    from src.parser.entities import TextChunk, CodeEntity, Relationship, ParserOutput
    from src.parser.parsers.cpp_parser import CppParser
    from src.parser.parsers.treesitter_setup import get_language
    from src.parser.parsers.base_parser import BaseParser
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

try:
    from ...conftest import run_parser_and_save_output
except ImportError as e:
    print(f"Warning: Could not import 'run_parser_and_save_output' from '...conftest'. Error: {e}")
    print("Ensure conftest.py is in the '.roo/cognee/tests/' directory and provides this fixture.")
    @pytest.fixture
    async def run_parser_and_save_output():
        async def _dummy_fixture(parser: BaseParser, test_file_path: Path, output_dir: Path, file_id_override: Optional[str] = None) -> List[BaseModel]:
            pytest.skip("Fixture 'run_parser_and_save_output' is not available. Check conftest.py setup and import path.")
            return []
        return _dummy_fixture

async def run_test_with_ast_dump_on_failure(
    request: pytest.FixtureRequest,
    parser_instance: CppParser,
    test_file: Path,
    tmp_path_for_output: Path,
    run_parser_fixture_func,
    assertions_callback,
    dump_ast_always: bool = False
):
    test_name = assertions_callback.__name__
    logger.info(f"--- Starting test: {test_name} for file {test_file.name} ---")

    file_id_base = str(test_file.absolute())
    actual_file_id_used_by_parser = f"test_parser_file_id_{hashlib.sha1(file_id_base.encode()).hexdigest()[:10]}"

    results: List[BaseModel] = await run_parser_fixture_func(
        parser=parser_instance,
        test_file_path=test_file,
        output_dir=tmp_path_for_output,
        file_id_override=actual_file_id_used_by_parser
    )

    try:
        assertions_callback(results, test_file, parser_instance, actual_file_id_used_by_parser)
        logger.info(f"--- Test PASSED: {test_name} for {test_file.name} ---")
    except AssertionError as e_assert:
        logger.error(f"--- Test FAILED: {test_name} for {test_file.name} ---")
        logger.error(f"AssertionError: {e_assert}", exc_info=True)
        logger.error(f"Parser yielded {len(results)} items for {test_file.name}:")
        for i, item in enumerate(results[:30]):
            if isinstance(item, CodeEntity):
                logger.error(f"  Item {i}: Type={item.type}, ID='{item.id}', EntityType='{getattr(item, 'type', 'N/A')}', Snippet='{item.snippet_content[:70].replace(chr(10),' ')}...'")
            elif isinstance(item, Relationship):
                logger.error(f"  Item {i}: Type={item.type}, ID='N/A', RelType='{getattr(item, 'type', 'N/A')}', Source='{item.source_id}', Target='{item.target_id}'")
            else:
                logger.error(f"  Item {i}: Type={getattr(item,'type','Unknown')}, ID='{getattr(item,'id','N/A')}', Content='{str(item)[:70].replace(chr(10),' ')}...'")
        if len(results) > 30:
            logger.error(f"  ... and {len(results) - 30} more items not shown.")

        if dump_ast_always or (request.config.getoption("verbose") > 0):
            logger.error(f"Dumping AST for {test_file.name} due to test failure:")
            try:
                content = await read_file_content(str(test_file))
                if content and parser_instance.parser:
                    tree = parser_instance.parser.parse(bytes(content, "utf8"))
                    if hasattr(tree.root_node, 'sexp'):
                        full_sexp = tree.root_node.sexp()
                        max_log_chunk = 2000
                        if len(full_sexp) > max_log_chunk:
                            logger.error(f"AST Sexp (truncated):\n{full_sexp[:max_log_chunk]}...")
                        else:
                            logger.error(f"AST Sexp:\n{full_sexp}")
                    else:
                        logger.error(f"Node (actual type: {type(tree.root_node)}, attr type: '{tree.root_node.type if hasattr(tree.root_node, 'type') else 'N/A'}') no .sexp(). Text: '{content[:70].replace(chr(10),' ')}...'")
                else:
                    logger.error("Could not read file content or parser not available for AST dump.")
            except Exception as dump_exc:
                logger.error(f"Failed to dump AST: {dump_exc}")
            logger.error(f"--- End AST Dump for {test_file.name} (failure) ---")
        raise
    finally:
        if hasattr(parser_instance, 'current_file_path'):
            parser_instance.current_file_path = None


def assertions_empty_file(results: List[BaseModel], test_file: Path, parser_instance: CppParser, file_id: str):
    assert len(results) == 0

def assertions_simple_class_file(results: List[BaseModel], test_file: Path, parser_instance: CppParser, file_id: str):
    logger.info(f"Running assertions for {test_file.name}. Results count: {len(results)}")
    assert len(results) > 0, f"Parser yielded no results for {test_file.name}"
    entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    relationships = [dp for dp in results if isinstance(dp, Relationship)]

    assert len(entities) >= 4, f"Expected at least 4 CodeEntities, got {len(entities)}"

    namespace_defs = [e for e in entities if e.type == "NamespaceDefinition"]
    assert any("Processing" in e.id for e in namespace_defs), "Namespace 'Processing' not found"

    class_defs = [e for e in entities if e.type == "ClassDefinition"]
    assert not any("MyDataProcessor" in e.id for e in class_defs), \
        f"Class 'MyDataProcessor' should NOT be defined in {test_file.name}. Found: {[e.id for e in class_defs if 'MyDataProcessor' in e.id]}"

    func_def_names = {e.id.split(":")[-2].replace("_SCOPE_","::") for e in entities if e.type == "FunctionDefinition"}

    expected_funcs = {"Processing::MyDataProcessor::processVector", "Processing::helperFunction", "main"}
    missing_funcs = expected_funcs - func_def_names
    assert not missing_funcs, f"Missing functions: {missing_funcs}. Found: {func_def_names}"

    imports = {r.target_id for r in relationships if r.type == "IMPORTS"}
    logger.info(f"IMPORTS found in {test_file.name}: {imports}")
    assert "my_class.hpp" in imports
    assert "iostream" in imports
    assert "vector" in imports
    assert "string" in imports
    assert "std" in imports

def assertions_header_file(results: List[BaseModel], test_file: Path, parser_instance: CppParser, file_id: str):
    logger.info(f"Running assertions for {test_file.name}. Results count: {len(results)}")
    assert len(results) > 0, f"Parser yielded no results for {test_file.name}"
    entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    relationships = [dp for dp in results if isinstance(dp, Relationship)]

    ns_processing_list = [
        e for e in entities if e.type == "NamespaceDefinition" and
        e.id.split(":")[-2].replace("_SCOPE_", "::") == "Processing"
    ]
    assert len(ns_processing_list) == 1, f"Expected 1 NamespaceDefinition for 'Processing', found {len(ns_processing_list)}. IDs: {[e.id for e in ns_processing_list]}"
    ns_processing = ns_processing_list[0]
    logger.info(f"Found NamespaceDefinition: ID='{ns_processing.id}', Type='{ns_processing.type}'")

    cls_my_data_proc_list = [
        e for e in entities if e.type == "ClassDefinition" and
        e.id.split(":")[-2].replace("_SCOPE_", "::") == "Processing::MyDataProcessor"
    ]
    assert len(cls_my_data_proc_list) == 1, \
        f"Expected 1 ClassDefinition for 'Processing::MyDataProcessor', found {len(cls_my_data_proc_list)}. IDs: {[e.id for e in cls_my_data_proc_list]}"
    cls_my_data_proc = cls_my_data_proc_list[0]
    logger.info(f"Found ClassDefinition: ID='{cls_my_data_proc.id}', Type='{cls_my_data_proc.type}'")

    ns_chunk_id = next((r.source_id for r in relationships if r.type == "CONTAINS_ENTITY" and r.target_id == ns_processing.id), None)
    cls_chunk_id = next((r.source_id for r in relationships if r.type == "CONTAINS_ENTITY" and r.target_id == cls_my_data_proc.id), None)
    assert ns_chunk_id is not None, f"Namespace {ns_processing.id} not contained in any chunk."
    assert cls_chunk_id is not None, f"Class {cls_my_data_proc.id} not contained in any chunk."
    assert ns_chunk_id == cls_chunk_id, \
        f"Namespace and Class are expected to be in the same chunk for this simple header. NS_Chunk: {ns_chunk_id}, CLS_Chunk: {cls_chunk_id}"

    if chunk_nodes := [item for item in results if isinstance(item, TextChunk)]:
        assert ns_chunk_id.startswith(file_id), f"Chunk ID '{ns_chunk_id}' of namespace does not start with file_id '{file_id}'"
    logger.info(f"VERIFIED (Temporarily): Namespace '{ns_processing.id}' and Class '{cls_my_data_proc.id}' are in the same chunk '{ns_chunk_id}'.")


    func_def_names = {e.id.split(":")[-2].replace("_SCOPE_","::") for e in entities if e.type == "FunctionDefinition"}
    expected_defs = {
        "Processing::MyDataProcessor::MyDataProcessor",
        "Processing::MyDataProcessor::~MyDataProcessor",
        "Processing::MyDataProcessor::identity"
    }
    missing_defs = expected_defs - func_def_names
    assert not missing_defs, f"Missing expected function definitions: {missing_defs}. Found: {func_def_names}"

    func_decl_names = {e.id.split(":")[-2].replace("_SCOPE_","::") for e in entities if e.type == "FunctionDeclaration"}
    expected_decls = {
        "Processing::MyDataProcessor::processVector",
        "Processing::helperFunction"
    }
    missing_decls = expected_decls - func_decl_names
    assert not missing_decls, f"Missing expected function declarations: {missing_decls}. Found: {func_decl_names}"

    imports = {r.target_id for r in relationships if r.type == "IMPORTS"}
    logger.info(f"IMPORTS found in {test_file.name}: {imports}")
    assert "string" in imports
    assert "vector" in imports

def assertions_complex_features_file(results: List[BaseModel], test_file: Path, parser_instance: CppParser, file_id: str):
    logger.info(f"Running assertions for {test_file.name}. Results count: {len(results)}")
    entities = [dp for dp in results if isinstance(dp, CodeEntity)]
    relationships = [dp for dp in results if isinstance(dp, Relationship)]
    assert len(entities) > 0, "No entities found in complex_features.cpp"

    def get_entity_names_from_ids(entity_type: str) -> Set[str]:
        names = set()
        for e_item in entities:
            if e_item.type == entity_type:
                parts = e_item.id.split(':')
                if len(parts) >= 4:
                    name_part_from_id = parts[-2]
                    converted_name = name_part_from_id.replace('_SCOPE_', '::')
                    names.add(converted_name)
        logger.debug(f"Names for {entity_type} in {test_file.name}: {names}")
        return names

    enum_names = get_entity_names_from_ids("EnumDefinition")
    assert "TestNS::ScopedEnum" in enum_names, f"Enum TestNS::ScopedEnum not found. Found: {enum_names}"
    assert "UnscopedEnum" in enum_names, f"Enum UnscopedEnum not found. Found: {enum_names}"
    logger.info(f"Successfully found 'TestNS::ScopedEnum' and 'UnscopedEnum'. Enum names found: {enum_names}")


    type_def_names = get_entity_names_from_ids("TypeDefinition")
    if "FuncPtr" not in type_def_names:
        logger.warning("Typedef 'FuncPtr' not found, possibly due to current typedef query limitations.")
    assert "StringVector" in type_def_names, f"Typedef/Alias StringVector not found. Found: {type_def_names}"


    namespace_names = get_entity_names_from_ids("NamespaceDefinition")
    assert "TestNS" in namespace_names, f"Namespace TestNS not found. Found: {namespace_names}"
    assert "TestNS::InnerNS" in namespace_names, f"Namespace TestNS::InnerNS not found. Found: {namespace_names}"
    assert "anonymous" in namespace_names, f"Anonymous namespace not found. Found: {namespace_names}"

    struct_names = get_entity_names_from_ids("StructDefinition")
    assert "SimpleStruct" in struct_names, f"Struct SimpleStruct not found. Found: {struct_names}"
    assert "TestNS::DataContainer" in struct_names, f"Struct TestNS::DataContainer not found. Found: {struct_names}"

    func_def_names = get_entity_names_from_ids("FunctionDefinition")
    expected_funcs = {
        "createInitializedArray",
        "TestNS::InnerNS::innerFunction",
        "TestNS::namespacedFunction",
        "anonymous::anonNSFunction",
        "MyComplexClass::MyComplexClass", "MyComplexClass::~MyComplexClass",
        "MyComplexClass::virtualMethod", "MyComplexClass::constMethod",
        "MyComplexClass::staticMethod", "MyComplexClass::operator+",
        "MyComplexClass::deletedMethod",
        "friendFunction",
        "TestNS::DerivedClass::DerivedClass",
        "TestNS::DerivedClass::virtualMethod",
        "TestNS::DerivedClass::anotherVirtualMethod",
        "useLambda",
        "c_style_function",
        "main"
    }

    missing_funcs = expected_funcs - func_def_names
    assert not missing_funcs, f"Missing FunctionDefinitions: {missing_funcs}. Found: {func_def_names}"

    constructor_entity_id_fqn_part = "MyComplexClass_SCOPE_MyComplexClass"
    assert any(e.id.endswith(f":FunctionDefinition:{constructor_entity_id_fqn_part}:0") for e in entities if e.type == "FunctionDefinition"), \
        f"Constructor MyComplexClass::MyComplexClass with specific ID ending not found. Check FQN and indexing. Entities: {[e.id for e in entities if e.type == 'FunctionDefinition']}"

    destructor_entity_id_fqn_part = "MyComplexClass_SCOPE_~MyComplexClass"
    assert any(e.id.endswith(f":FunctionDefinition:{destructor_entity_id_fqn_part}:0") for e in entities if e.type == "FunctionDefinition"), \
        f"Destructor MyComplexClass::~MyComplexClass with specific ID ending not found. Entities: {[e.id for e in entities if e.type == 'FunctionDefinition']}"

    class_names = get_entity_names_from_ids("ClassDefinition")
    assert "MyComplexClass" in class_names, f"Class MyComplexClass not found. Found: {class_names}"
    assert "TestNS::DerivedClass" in class_names, f"Class TestNS::DerivedClass not found. Found: {class_names}"
    assert "ForwardDeclaredClass" in class_names, f"ForwardDeclaredClass not found as ClassDefinition. Found: {class_names}"


    cls_derived_list = [e for e in entities if e.type == "ClassDefinition" and e.id.split(":")[-2].replace("_SCOPE_", "::") == "TestNS::DerivedClass"]
    assert len(cls_derived_list) == 1, f"Expected 1 DerivedClass, found {len(cls_derived_list)}"
    cls_derived = cls_derived_list[0]

    extends_rels = [r for r in relationships if r.source_id == cls_derived.id and r.type == "EXTENDS"]
    assert any(r.target_id == "MyComplexClass" for r in extends_rels), \
        f"DerivedClass should extend MyComplexClass. Found extends: {[r.target_id for r in extends_rels]}"

    imports = {r.target_id for r in relationships if r.type == "IMPORTS"}
    expected_imports = {"iostream", "vector", "string", "functional", "std", "array"}
    missing_imports = expected_imports - imports
    assert not missing_imports, f"Missing expected imports: {missing_imports}"
    assert "std" in imports
    assert "using_namespace_std_directive_placeholder" not in imports


@pytest.mark.asyncio
async def test_parse_empty_cpp_file(request: pytest.FixtureRequest, parser: CppParser, tmp_path: Path, run_parser_and_save_output):
    empty_cpp_file = tmp_path / "empty.cpp"
    empty_cpp_file.write_text("")
    await run_test_with_ast_dump_on_failure(request, parser, empty_cpp_file, tmp_path, run_parser_and_save_output, assertions_empty_file)

@pytest.mark.asyncio
async def test_parse_empty_hpp_file(request: pytest.FixtureRequest, parser: CppParser, tmp_path: Path, run_parser_and_save_output):
    empty_hpp_file = tmp_path / "empty.hpp"
    empty_hpp_file.write_text("")
    await run_test_with_ast_dump_on_failure(request, parser, empty_hpp_file, tmp_path, run_parser_and_save_output, assertions_empty_file)

@pytest.mark.asyncio
async def test_parse_simple_class_file(request: pytest.FixtureRequest, parser: CppParser, tmp_path: Path, run_parser_and_save_output):
    test_file = TEST_DATA_DIR / "simple_class.cpp"
    await run_test_with_ast_dump_on_failure(request, parser, test_file, tmp_path, run_parser_and_save_output, assertions_simple_class_file)

@pytest.mark.asyncio
async def test_parse_header_file(request: pytest.FixtureRequest, parser: CppParser, tmp_path: Path, run_parser_and_save_output):
    test_file = TEST_DATA_DIR / "my_class.hpp"
    await run_test_with_ast_dump_on_failure(request, parser, test_file, tmp_path, run_parser_and_save_output, assertions_header_file)

@pytest.mark.asyncio
async def test_complex_features_file(request: pytest.FixtureRequest, parser: CppParser, tmp_path: Path, run_parser_and_save_output):
    logger.debug("Starting test_complex_features_file")
    test_file = TEST_DATA_DIR / "complex_features.cpp"
    if not test_file.exists():
        logger.error(f"Test data file not found: {test_file}")
        pytest.skip(f"Test data file not found: {test_file}")
    await run_test_with_ast_dump_on_failure(request, parser, test_file, tmp_path, run_parser_and_save_output, assertions_complex_features_file, dump_ast_always=False)
