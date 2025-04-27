from typing import AsyncGenerator
from uuid import uuid5, NAMESPACE_OID
import pytest
import asyncio
import os
from pathlib import Path
# Use unittest.mock for its robust patching capabilities, especially with async
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import List, Dict, Any, Optional, Tuple

# Ensure pytest-asyncio is installed and usable
pytestmark = pytest.mark.asyncio

# Import the function to test and entity types for verification
try:
    from src.parser.orchestrator import process_repository
    # Import specific entity types for instantiation in mocks
    from src.parser.entities import Repository, SourceFile, DataPoint, TextChunk, CodeEntity, Dependency
except ImportError as e:
     pytest.skip(f"Skipping orchestrator tests: Failed to import dependencies - {e}", allow_module_level=True)


# --- Mock Data Setup ---

# Helper to create mock payloads (dictionaries representing entity data)
# ADD text_content parameter
def create_mock_payload(id_val: str, type_val: str, parent_id: str = None, text_content: str = "", **kwargs) -> dict:
    """Creates a dictionary representing DataPoint data for mocking."""
    payload = {
        "id": id_val,
        "type": type_val,
        "text_content": text_content, # Added text_content
        # Add keys based on type for more realistic mocks if needed by assertions
        "chunk_of": parent_id if type_val == "TextChunk" else None,
        "defined_in_file": parent_id if type_val in ["FunctionDefinition", "ClassDefinition"] else None,
        "used_in_file": parent_id if type_val == "Dependency" else None,
        **kwargs
    }
    return {k: v for k, v in payload.items() if v is not None} # Clean None values

# Define mock discovery results (paths will be based on tmp_path later)
# Structure: List[Tuple[absolute_path_str, relative_path_str, file_type_str]]
def get_mock_discovery_data(base_path: Path) -> List[tuple]:
    """Generates mock discovery data relative to a base path."""
    repo_root = base_path / "mock_repo"
    return [
        (str(repo_root / "main.py"), "main.py", "python"),
        (str(repo_root / "README.md"), "README.md", "markdown"),
        (str(repo_root / "src" / "app.js"), os.path.join("src", "app.js"), "javascript"),
        (str(repo_root / "config.xml"), "config.xml", "xml"), # Unsupported type
    ]

# Define expected IDs and mock parser outputs based on mock discovery
# This helps ensure consistency between mocks and assertions
def setup_expected_outcomes(base_path: Path) -> dict:
    """Calculates expected IDs and defines mock parser outputs."""
    mock_discovery = get_mock_discovery_data(base_path)
    repo_root = base_path / "mock_repo"
    abs_repo_path = str(repo_root.absolute())

    outcomes = {
        "repo_id": str(uuid5(NAMESPACE_OID, abs_repo_path)),
        "file_ids": {}, # Map rel_path -> file_id
        "parser_outputs": {} # Map file_id (string) -> list of mock payloads
    }

    for abs_p, rel_p, f_type in mock_discovery:
        file_id = str(uuid5(NAMESPACE_OID, os.path.abspath(abs_p)))
        outcomes["file_ids"][rel_p] = file_id

        # Define mock outputs *only* for supported types with parsers
        if f_type == "python":
            outcomes["parser_outputs"][str(file_id)] = [ # Use string ID as key
                # Pass text_content
                create_mock_payload(f"{str(file_id)}:chunk:0", "TextChunk", parent_id=str(file_id), chunk_index=0, text_content="mock python text chunk 1"),
                create_mock_payload(f"{str(file_id)}:FunctionDefinition:main:10", "FunctionDefinition", parent_id=str(file_id), name="main", start_line=10, end_line=15, text_content="def main():\n  pass"),
                create_mock_payload(f"{str(file_id)}:dep:os:1", "Dependency", parent_id=str(file_id), target_module="os", start_line=1, end_line=1, text_content="import os"),
            ]
        elif f_type == "markdown":
             outcomes["parser_outputs"][str(file_id)] = [ # Use string ID as key
                # Pass text_content
                create_mock_payload(f"{str(file_id)}:chunk:0", "TextChunk", parent_id=str(file_id), chunk_index=0, text_content="mock markdown text chunk 1"),
                create_mock_payload(f"{str(file_id)}:chunk:1", "TextChunk", parent_id=str(file_id), chunk_index=1, text_content="mock markdown text chunk 2"),
             ]
        elif f_type == "javascript":
             outcomes["parser_outputs"][str(file_id)] = [ # Use string ID as key
                # Pass text_content
                create_mock_payload(f"{str(file_id)}:ClassDefinition:App:5", "ClassDefinition", parent_id=str(file_id), name="App", start_line=5, end_line=20, text_content="class App {}"),
                create_mock_payload(f"{str(file_id)}:dep:react:1", "Dependency", parent_id=str(file_id), target_module="react", start_line=1, end_line=1, text_content="import React from 'react'"),
             ]
        # No output defined for 'xml'

    return outcomes

# Updated helper to yield actual DataPoint instances based on mock payload dicts
async def async_payload_gen_wrapper(payload_list: Optional[List[Dict]]):
    """Wraps a list of payload dicts in an async generator yielding DataPoint instances."""
    if payload_list is None:
        payload_list = []
    for payload in payload_list:
        entity_type = payload.get("type")
        # Ensure parent_id is always string
        str_parent_id = str(payload.get("chunk_of") or payload.get("defined_in_file") or payload.get("used_in_file"))

        # Instantiate the correct DataPoint subclass based on type
        type_val = payload.get("type")
        if type_val == "TextChunk":
            dp = TextChunk(
                chunk_id_str=payload.get("id"),
                parent_id=str_parent_id,
                text=payload.get("text_content", ""), # Use text_content
                chunk_index=payload.get("chunk_index"),
                start_line=payload.get("start_line"),
                end_line=payload.get("end_line")
            )
        elif type_val in ["FunctionDefinition", "ClassDefinition", "StructDefinition", "EnumDefinition", "TraitDefinition", "Implementation", "MacroDefinition", "ModuleDefinition"]:
             dp = CodeEntity( # Add CodeEntity instantiation
                 entity_id_str=payload.get("id"),
                 entity_type=type_val, # Use the specific type
                 name=payload.get("name"),
                 source_file_id=str_parent_id,
                 source_code=payload.get("text_content", ""), # Use text_content
                 start_line=payload.get("start_line"),
                 end_line=payload.get("end_line")
             )
        elif type_val == "Dependency":
             dp = Dependency( # Add Dependency instantiation
                 dep_id_str=payload.get("id"),
                 source_file_id=str_parent_id,
                 target=payload.get("target_module"), # Use target_module
                 source_code_snippet=payload.get("text_content", ""), # Use text_content
                 start_line=payload.get("start_line"),
                 end_line=payload.get("end_line")
             )
        else:
            # Fallback or raise error for unknown types
            logger.warning(f"Mock payload creator encountered unknown type: {type_val}")
            # Create a generic DataPoint or skip? For testing, maybe skip.
            return None # Skip unknown types
        yield dp # Yield the created instance


# Async generator helper for discover_files mock
async def async_gen_wrapper(item_list: List[tuple]):
    """Wraps a list of items in a simple async generator."""
    for item in item_list:
        yield item
        await asyncio.sleep(0) # Yield control


# --- Test Cases ---

# Use patch to replace dependencies within the orchestrator module
@patch('src.parser.orchestrator.discover_files')
@patch('src.parser.orchestrator.PARSER_MAP', new_callable=dict) # Patch the actual dict used
async def test_process_repository_basic_flow(mock_parser_map_dict, mock_discover, tmp_path: Path):
    """
    Tests the main success path: discovery, repo/file yielding, parser dispatch, result yielding.
    """
    repo_path = tmp_path / "mock_repo"
    repo_path.mkdir()

    # Setup expected outcomes and mock data based on tmp_path
    expected_outcomes = setup_expected_outcomes(tmp_path)
    mock_discovery_data = get_mock_discovery_data(tmp_path)

    # Create dummy files so paths exist (needed for absolute path ID generation)
    for abs_p, _, _ in mock_discovery_data:
        Path(abs_p).parent.mkdir(parents=True, exist_ok=True)
        Path(abs_p).touch()

    # Configure mock discovery to return our predefined data
    mock_discover.return_value = async_gen_wrapper(mock_discovery_data) # Note: discover_files yields tuples

    # --- Mock Parsers ---
    # Create mocked parser instances
    mock_python_parser = MagicMock(parser_type="MockPythonParser")
    mock_markdown_parser = MagicMock(parser_type="MockMarkdownParser")
    mock_js_parser = MagicMock(parser_type="MockJSParser")

    # CORRECTED Side effect function (make it async)
    async def parse_side_effect(file_path, file_id):
        # Look up the predefined mock payloads using the file_id passed by the orchestrator
        mock_payloads_for_file = expected_outcomes["parser_outputs"].get(str(file_id)) # Use string ID for lookup
        # Wrap the payloads in the async generator helper
        return async_payload_gen_wrapper(mock_payloads_for_file)

    # Assign the ASYNC side effect to the 'parse' method
    mock_python_parser.parse = AsyncMock(side_effect=parse_side_effect)
    mock_markdown_parser.parse = AsyncMock(side_effect=parse_side_effect)
    mock_js_parser.parse = AsyncMock(side_effect=parse_side_effect)

    # Create mocked classes that return the mocked instances when called
    MockPythonParserClass = MagicMock(return_value=mock_python_parser)
    MockPythonParserClass.__name__ = "MockPythonParser" # Add __name__
    MockMarkdownParserClass = MagicMock(return_value=mock_markdown_parser)
    MockMarkdownParserClass.__name__ = "MockMarkdownParser" # Add __name__
    MockJSParserClass = MagicMock(return_value=mock_js_parser)
    MockJSParserClass.__name__ = "MockJSParser" # Add __name__

    # Populate the *patched* PARSER_MAP dictionary (mock_parser_map_dict)
    mock_parser_map_dict.update({
        "python": MockPythonParserClass,
        "markdown": MockMarkdownParserClass,
        "javascript": MockJSParserClass,
        # No mapping for "xml"
    })
    # --- End Mock Setup ---

    # --- Execute Test ---
    results_dp_objects = []
    async for dp in process_repository(str(repo_path)):
        results_dp_objects.append(dp)

    # --- Assertions ---
    # No longer need to convert to payloads for basic checks, access attributes directly

    # 1. Check total items yielded
    expected_parser_results_count = sum(len(v) for v in expected_outcomes["parser_outputs"].values())
    # Total = 1 Repo + N Files + M Parser Results
    expected_total_yields = 1 + len(mock_discovery_data) + expected_parser_results_count
    assert len(results_dp_objects) == expected_total_yields, f"Incorrect total yielded: {len(results_dp_objects)} vs {expected_total_yields}"

    # 2. Check Repository node (access attributes directly)
    repo_dp = results_dp_objects[0]
    assert isinstance(repo_dp, Repository), "First item should be Repository instance"
    assert repo_dp.type == "Repository", "First item type should be Repository"
    assert str(repo_dp.id) == expected_outcomes["repo_id"], "Repository ID mismatch" # Compare string IDs
    assert repo_dp.path == str(repo_path.absolute()), "Repository path mismatch" # Access direct attribute

    # 3. Check SourceFile nodes (access attributes directly)
    yielded_files = results_dp_objects[1 : 1 + len(mock_discovery_data)]
    assert len(yielded_files) == len(mock_discovery_data), "Incorrect number of SourceFile nodes yielded"

    expected_file_ids = {str(f_id) for f_id in expected_outcomes["file_ids"].values()} # Use string IDs
    yielded_file_ids = set()

    for i, file_dp in enumerate(yielded_files):
        expected_abs_path, expected_rel_path, expected_type = mock_discovery_data[i]
        expected_file_id = str(expected_outcomes["file_ids"][expected_rel_path]) # Get corresponding expected string ID

        assert isinstance(file_dp, SourceFile), f"Item {i+1} should be SourceFile instance"
        assert file_dp.type == "SourceFile", f"File {i} type mismatch"
        assert str(file_dp.id) == expected_file_id, f"File {i} ID mismatch" # Compare string IDs
        assert file_dp.name == os.path.basename(expected_abs_path), f"File {i} name mismatch"
        assert file_dp.file_path == expected_abs_path, f"File {i} file_path mismatch"
        assert file_dp.relative_path == expected_rel_path, f"File {i} relative_path mismatch"
        assert file_dp.file_type == expected_type, f"File {i} file_type mismatch"
        assert str(file_dp.part_of_repository) == expected_outcomes["repo_id"], f"File {i} repo link mismatch" # Compare string IDs
        yielded_file_ids.add(str(file_dp.id)) # Add string ID

    assert yielded_file_ids == expected_file_ids, "Set of yielded file IDs doesn't match expected"


    # 4. Check Parser Output nodes (CodeEntity, Dependency, TextChunk)
    parser_results = results_dp_objects[1 + len(mock_discovery_data):]
    assert len(parser_results) == expected_parser_results_count, "Incorrect number of parser results yielded"

    # Group expected parser outputs by parent file ID for easier checking
    expected_parser_outputs_grouped = {}
    for file_id_str, payloads in expected_outcomes["parser_outputs"].items(): # file_id_str is already string
        expected_parser_outputs_grouped[file_id_str] = {p["id"]: p for p in payloads} # Use ID as key

    yielded_parser_results_grouped = {}
    for dp in parser_results:
        # Determine parent ID based on entity type using direct attribute access
        parent_id = None
        if isinstance(dp, CodeEntity):
            parent_id = dp.defined_in_file
        elif isinstance(dp, Dependency):
            parent_id = dp.used_in_file
        elif isinstance(dp, TextChunk):
            parent_id = dp.chunk_of # Access chunk_of directly

        assert parent_id is not None, f"Could not determine parent ID for yielded item: {dp}"
        parent_id_str = str(parent_id) # Ensure string comparison
        if parent_id_str not in yielded_parser_results_grouped:
            yielded_parser_results_grouped[parent_id_str] = {}
        yielded_parser_results_grouped[parent_id_str][str(dp.id)] = dp # Use string ID

    # Compare yielded vs expected for each file
    assert yielded_parser_results_grouped.keys() == expected_parser_outputs_grouped.keys(), "Mismatch in file IDs for parser results"

    for file_id_str, expected_payloads_dict in expected_parser_outputs_grouped.items():
        yielded_results_dict = yielded_parser_results_grouped[file_id_str]
        assert yielded_results_dict.keys() == expected_payloads_dict.keys(), f"Mismatch in yielded item IDs for file {file_id_str}"

        for item_id, expected_payload in expected_payloads_dict.items():
            yielded_dp = yielded_results_dict[item_id]
            # Basic type check
            assert yielded_dp.type == expected_payload["type"], f"Type mismatch for item {item_id}"
            # Check some key attributes based on type using direct access
            if yielded_dp.type == "TextChunk":
                assert yielded_dp.text_content == expected_payload["text_content"], f"Text content mismatch for chunk {item_id}"
                assert yielded_dp.chunk_index == expected_payload["chunk_index"], f"Chunk index mismatch for {item_id}"
            elif yielded_dp.type in ["FunctionDefinition", "ClassDefinition"]:
                 assert yielded_dp.name == expected_payload["name"], f"Name mismatch for code entity {item_id}"
                 assert yielded_dp.start_line == expected_payload["start_line"], f"Start line mismatch for {item_id}"
                 assert yielded_dp.text_content == expected_payload["text_content"], f"Source code mismatch for {item_id}"
            elif yielded_dp.type == "Dependency":
                 assert yielded_dp.target_module == expected_payload["target_module"], f"Target module mismatch for dep {item_id}"
                 assert yielded_dp.text_content == expected_payload["text_content"], f"Snippet mismatch for dep {item_id}"

    # 5. Verify Mock Calls
    mock_discover.assert_called_once_with(str(repo_path.absolute()))

    # Check that parser classes were instantiated correctly (once per type)
    assert MockPythonParserClass.call_count == 1
    assert MockMarkdownParserClass.call_count == 1
    assert MockJSParserClass.call_count == 1

    # Check that parse was called for supported files with correct file_id
    expected_parse_calls = []
    for abs_p, rel_p, f_type in mock_discovery_data:
        if f_type in mock_parser_map_dict: # Only expect calls for supported types
            file_id = expected_outcomes["file_ids"][rel_p] # Get UUID object
            parser_instance = { # Map type to the *mocked instance*
                "python": mock_python_parser,
                "markdown": mock_markdown_parser,
                "javascript": mock_js_parser,
            }[f_type]
            # Check call arguments on the specific mocked instance
            # Pass the UUID object directly to the mock assertion
            parser_instance.parse.assert_any_call(file_path=abs_p, file_id=str(file_id)) # Pass file_id as string

    # Verify total parse calls match number of supported files
    total_parse_calls = (mock_python_parser.parse.call_count +
                         mock_markdown_parser.parse.call_count +
                         mock_js_parser.parse.call_count)
    supported_file_count = sum(1 for _, _, f_type in mock_discovery_data if f_type in mock_parser_map_dict)
    assert total_parse_calls == supported_file_count


@patch('src.parser.orchestrator.discover_files')
async def test_process_repository_no_files_found(mock_discover, tmp_path: Path):
    """Test processing when discovery yields no files."""
    repo_path = tmp_path / "empty_repo"
    repo_path.mkdir()
    abs_repo_path = str(repo_path.absolute())
    expected_repo_id = str(uuid5(NAMESPACE_OID, abs_repo_path))

    mock_discover.return_value = async_gen_wrapper([]) # Empty generator

    results = []
    async for dp in process_repository(str(repo_path)):
        results.append(dp)

    # Should yield only the Repository node
    assert len(results) == 1, "Expected only Repository node for empty discovery"
    assert isinstance(results[0], Repository), "First item should be Repository instance"
    # Access attributes directly after fixing entities.py
    # --- Corrected Assertion ---
    assert str(results[0].id) == expected_repo_id
    # Access path via metadata now
    assert results[0].metadata.get("path") == abs_repo_path
    mock_discover.assert_called_once_with(abs_repo_path)


@patch('src.parser.orchestrator.discover_files')
@patch('src.parser.orchestrator.PARSER_MAP', new_callable=dict)
@patch('src.parser.orchestrator.logger') # Mock logger to check error logs
async def test_process_repository_parser_error_handling(mock_logger, mock_parser_map_dict, mock_discover, tmp_path: Path):
    """Test graceful handling when a specific parser's 'parse' method raises an exception."""
    repo_path = tmp_path / "repo_with_error"
    repo_path.mkdir()

    # Setup discovery for one python file that will succeed, one that will fail
    py_ok_path = str(repo_path / "ok.py")
    py_err_path = str(repo_path / "error.py")
    Path(py_ok_path).touch()
    Path(py_err_path).touch()

    mock_discovery_data = [
        (py_ok_path, "ok.py", "python"),
        (py_err_path, "error.py", "python"),
    ]
    mock_discover.return_value = async_gen_wrapper(mock_discovery_data)

    # Expected IDs (as strings)
    abs_repo_path = str(repo_path.absolute())
    repo_id = str(uuid5(NAMESPACE_OID, abs_repo_path)) # Keep repo_id as string
    file_ok_id_obj = uuid5(NAMESPACE_OID, os.path.abspath(py_ok_path)) # Keep UUID object for mock call check
    file_err_id_obj = uuid5(NAMESPACE_OID, os.path.abspath(py_err_path)) # Keep UUID object for mock call check
    file_ok_id = str(file_ok_id_obj)
    file_err_id = str(file_err_id_obj)


    # Expected successful payload (as dict)
    # Expected successful payload (as dict, ensure parent_id is string)
    ok_payloads = [create_mock_payload(f"{file_ok_id}:chunk:0", "TextChunk", parent_id=str(file_ok_id), text_content="OK chunk", chunk_index=0)]

    # Mock parser instance and class
    mock_python_parser = MagicMock(parser_type="MockPythonParser")
    MockPythonParserClass = MagicMock(return_value=mock_python_parser)
    MockPythonParserClass.__name__ = "MockPythonParser" # Add __name__
    mock_parser_map_dict["python"] = MockPythonParserClass

    # Configure parse: success for ok.py, raise exception for error.py
    simulated_error = ValueError("KABOOM! Simulated parsing error.")
    # Make the side effect async
    async def error_parse_side_effect(file_path, file_id):
        file_id_str = str(file_id) # Get string ID from passed UUID
        if "ok.py" in file_path:
            assert file_id_str == str(file_ok_id) # Compare strings
            return async_payload_gen_wrapper(ok_payloads)
        elif "error.py" in file_path:
            assert file_id_str == str(file_err_id) # Compare strings
            # Simulate an error *inside* the async generator
            async def error_gen():
                raise simulated_error
            return error_gen()
        else:
            # Return an empty generator for any unexpected calls
            return async_payload_gen_wrapper([])
    mock_python_parser.parse = AsyncMock(side_effect=error_parse_side_effect)

    # --- Execute ---
    results_dp = []
    async for dp in process_repository(str(repo_path)):
        results_dp.append(dp)

    # --- Assertions ---
    # Expected: 1 Repo + 2 Files + results from ok.py (1 payload)
    assert len(results_dp) == 1 + 2 + 1, "Incorrect number of yielded items with parser error"
    # Check types yielded
    assert isinstance(results_dp[0], Repository)
    assert isinstance(results_dp[1], SourceFile)
    assert isinstance(results_dp[2], SourceFile)
    assert isinstance(results_dp[3], TextChunk) # Assuming ok_payloads[0] is TextChunk

    # Check that the successful payload from ok.py is present
    expected_ok_payload_id = ok_payloads[0]["id"]
    assert any(str(dp.id) == expected_ok_payload_id for dp in results_dp), "Payload from ok.py missing"
    # Check that no parser results related to error.py are present
    # Access parent links directly from the object attributes
    # The first 3 results are Repo and SourceFiles, parser results start from index 3
    # The first 3 results are Repo and SourceFiles, parser results start from index 3
    parser_results = results_dp[3:]
    failed_file_results_present = False
    for dp in parser_results:
        # Check if the parent link matches the failed file ID (using direct attributes)
        # Use direct attributes if available, fallback to metadata
        defined_in = getattr(dp, 'defined_in_file', dp.metadata.get('defined_in_file'))
        used_in = getattr(dp, 'used_in_file', dp.metadata.get('used_in_file'))
        chunk_of = getattr(dp, 'chunk_of', dp.metadata.get('chunk_of'))
        if defined_in == file_err_id or used_in == file_err_id or chunk_of == file_err_id:
            failed_file_results_present = True
            break
    assert not failed_file_results_present, "Results from failed parser should not be yielded"


    # Check logs: ensure error was logged for error.py by _process_single_file
    # We check the logger patch applied to the orchestrator module
    error_log_found = False
    for log_call in mock_logger.error.call_args_list:
        args, kwargs = log_call
        if "Error executing parser" in args[0] and "error.py" in args[0] and "KABOOM" in args[0]:
            error_log_found = True
            # Optionally check keyword arguments like exc_info=True
            assert kwargs.get('exc_info') is True, "exc_info=True expected in error log"
            break
    assert error_log_found, "Expected error log for failed parser was not found"


    # Check parse calls were made for both files
    assert mock_python_parser.parse.call_count == 2, "Parse method not called expected number of times"
    # Assert calls using the string file IDs
    mock_python_parser.parse.assert_any_call(file_path=py_ok_path, file_id=file_ok_id)
    mock_python_parser.parse.assert_any_call(file_path=py_err_path, file_id=file_err_id)
