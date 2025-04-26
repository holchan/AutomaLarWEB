from uuid import uuid5, NAMESPACE_OID
import pytest
import asyncio
import os
from pathlib import Path
# Use unittest.mock for its robust patching capabilities, especially with async
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import List, Dict, Any, Optional, Tuple # <<< ADD List and Tuple here >>>

# Ensure pytest-asyncio is installed and usable
pytestmark = pytest.mark.asyncio

# Import the function to test and entity types for verification
try:
    from src.parser.orchestrator import process_repository
    from src.parser.entities import Repository, SourceFile, DataPoint # Use DataPoint for type hints if needed
except ImportError as e:
     pytest.skip(f"Skipping orchestrator tests: Failed to import dependencies - {e}", allow_module_level=True)


# --- Mock Data Setup ---

# Helper to create mock payloads (simpler than full DataPoint objects for mocking)
def create_mock_payload(id_val: str, type_val: str, parent_id: str = None, **kwargs) -> dict:
    """Creates a dictionary representing a DataPoint payload for mocking."""
    payload = {
        "id": id_val,
        "type": type_val,
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
        "parser_outputs": {} # Map file_id -> list of mock payloads
    }

    for abs_p, rel_p, f_type in mock_discovery:
        file_id = str(uuid5(NAMESPACE_OID, os.path.abspath(abs_p)))
        outcomes["file_ids"][rel_p] = file_id

        # Define mock outputs *only* for supported types with parsers
        if f_type == "python":
            outcomes["parser_outputs"][file_id] = [
                create_mock_payload(f"{file_id}:chunk:0", "TextChunk", parent_id=file_id, chunk_index=0, text="mock python text"),
                create_mock_payload(f"{file_id}:FunctionDefinition:main:10", "FunctionDefinition", parent_id=file_id, name="main", start_line=10),
            ]
        elif f_type == "markdown":
             outcomes["parser_outputs"][file_id] = [
                create_mock_payload(f"{file_id}:chunk:0", "TextChunk", parent_id=file_id, chunk_index=0, text="mock markdown text"),
             ]
        elif f_type == "javascript":
             outcomes["parser_outputs"][file_id] = [
                create_mock_payload(f"{file_id}:ClassDefinition:App:5", "ClassDefinition", parent_id=file_id, name="App", start_line=5),
             ]
        # No output defined for 'xml'

    return outcomes

# Async generator helper for mocks - yields mock objects having a 'payload' attribute
async def async_payload_gen_wrapper(payload_list: List[dict]):
    """Wraps a list of payloads in an async generator yielding mock objects."""
    if payload_list is None: payload_list = []
    for payload in payload_list:
        mock_dp = MagicMock()
        # Attach the payload to the mock object
        mock_dp.payload = payload
        yield mock_dp
        await asyncio.sleep(0) # Yield control

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

    # Side effect function for the mocked 'parse' methods
    def parse_side_effect(file_path, file_id):
        # Look up the predefined mock payloads using the file_id passed by the orchestrator
        mock_payloads_for_file = expected_outcomes["parser_outputs"].get(file_id)
        # Wrap the payloads in the async generator helper
        return async_payload_gen_wrapper(mock_payloads_for_file)

    # Assign the side effect to the 'parse' method of each mock instance
    mock_python_parser.parse = AsyncMock(side_effect=parse_side_effect)
    mock_markdown_parser.parse = AsyncMock(side_effect=parse_side_effect)
    mock_js_parser.parse = AsyncMock(side_effect=parse_side_effect)

    # Create mocked classes that return the mocked instances when called
    MockPythonParserClass = MagicMock(return_value=mock_python_parser)
    MockMarkdownParserClass = MagicMock(return_value=mock_markdown_parser)
    MockJSParserClass = MagicMock(return_value=mock_js_parser)

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
    # Get payloads for easier checking using model_dump
    results_payloads = [dp.model_dump(mode='json') for dp in results_dp_objects]

    # 1. Check total items yielded
    expected_parser_results_count = sum(len(v) for v in expected_outcomes["parser_outputs"].values())
    expected_total_yields = 1 + len(mock_discovery_data) + expected_parser_results_count
    assert len(results_payloads) == expected_total_yields, "Incorrect total number of yielded DataPoints"

    # 2. Check Repository node
    assert results_payloads[0].get("type") == "Repository", "First item should be Repository"
    assert results_payloads[0].get("id") == expected_outcomes["repo_id"], "Repository ID mismatch"
    assert results_payloads[0].get("path") == str(repo_path.absolute()), "Repository path mismatch"

    # 3. Check SourceFile nodes
    yielded_files = results_payloads[1 : 1 + len(mock_discovery_data)]
    assert len(yielded_files) == len(mock_discovery_data), "Incorrect number of SourceFile nodes yielded"
    assert all(f.get("type") == "SourceFile" for f in yielded_files), "Expected only SourceFile nodes after Repository"
    # Check details and IDs
    found_rel_paths = set()
    for i, file_info in enumerate(mock_discovery_data):
        abs_p, rel_p, f_type = file_info
        expected_file_id = expected_outcomes["file_ids"][rel_p]
        # Find the corresponding yielded file
        found_file = next((f for f in yielded_files if f.get("relative_path") == rel_p), None)
        assert found_file is not None, f"Did not find yielded SourceFile for {rel_p}"
        assert found_file.get("id") == expected_file_id, f"SourceFile ID mismatch for {rel_p}"
        assert found_file.get("file_type") == f_type, f"SourceFile file_type mismatch for {rel_p}"
        assert found_file.get("part_of_repository") == expected_outcomes["repo_id"], f"SourceFile repo link mismatch for {rel_p}"
        found_rel_paths.add(rel_p)
    assert len(found_rel_paths) == len(mock_discovery_data), "Duplicate or missing SourceFiles yielded"

    # 4. Check Parser Results (order might vary due to asyncio.gather)
    yielded_parser_results = results_payloads[1 + len(mock_discovery_data):]
    yielded_parser_ids = {p.get("id") for p in yielded_parser_results}

    expected_parser_payloads_flat = []
    for file_id in expected_outcomes["file_ids"].values():
        expected_parser_payloads_flat.extend(expected_outcomes["parser_outputs"].get(file_id, []))
    expected_parser_ids = {p.get("id") for p in expected_parser_payloads_flat}

    assert yielded_parser_ids == expected_parser_ids, "Mismatch in yielded parser result IDs"
    # Optional deep check: compare sorted lists of dictionaries
    # assert sorted(yielded_parser_results, key=lambda x: x['id']) == sorted(expected_parser_payloads_flat, key=lambda x: x['id'])

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
            file_id = expected_outcomes["file_ids"][rel_p]
            parser_instance = { # Map type to the *mocked instance*
                "python": mock_python_parser,
                "markdown": mock_markdown_parser,
                "javascript": mock_js_parser,
            }[f_type]
            # Check call arguments on the specific mocked instance
            parser_instance.parse.assert_any_call(file_path=abs_p, file_id=file_id)

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
    # Access attributes directly
    assert results[0].id == expected_repo_id
    assert results[0].path == abs_repo_path
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

    # Expected IDs
    abs_repo_path = str(repo_path.absolute())
    repo_id = str(uuid5(NAMESPACE_OID, abs_repo_path))
    file_ok_id = str(uuid5(NAMESPACE_OID, os.path.abspath(py_ok_path)))
    file_err_id = str(uuid5(NAMESPACE_OID, os.path.abspath(py_err_path)))

    # Expected successful payload
    ok_payloads = [create_mock_payload(f"{file_ok_id}:chunk:0", "TextChunk", file_ok_id)]

    # Mock parser instance and class
    mock_python_parser = MagicMock(parser_type="MockPythonParser")
    MockPythonParserClass = MagicMock(return_value=mock_python_parser)
    mock_parser_map_dict["python"] = MockPythonParserClass

    # Configure parse: success for ok.py, raise exception for error.py
    simulated_error = ValueError("KABOOM! Simulated parsing error.")
    def error_parse_side_effect(file_path, file_id):
        if "ok.py" in file_path:
            assert file_id == file_ok_id # Verify correct ID passed
            return async_payload_gen_wrapper(ok_payloads)
        elif "error.py" in file_path:
            assert file_id == file_err_id
            # Simulate an error during the async generator's iteration
            async def error_gen():
                raise simulated_error
                yield # Need yield to be an async generator
            return error_gen()
        else:
            return async_payload_gen_wrapper([])
    mock_python_parser.parse = AsyncMock(side_effect=error_parse_side_effect)

    # --- Execute ---
    results_dp = []
    async for dp in process_repository(str(repo_path)):
        results_dp.append(dp)

    # --- Assertions ---
    # Expected: 1 Repo + 2 Files + results from ok.py (1 payload)
    assert len(results_dp) == 1 + 2 + 1, "Incorrect number of yielded items with parser error"
    # Get payloads for easier checking using model_dump
    results_payloads = [dp.model_dump(mode='json') for dp in results_dp]

    # Check that results from ok.py are present
    assert any(p.get("id") == ok_payloads[0]["id"] for p in results_payloads), "Payload from ok.py missing"
    # Check that no parser results related to error.py are present
    # Access parent links directly from the object attributes if possible, or check metadata in dumped payload
    # Assuming parent links are top-level attributes based on entity definitions
    assert not any(dp.defined_in_file == file_err_id or dp.used_in_file == file_err_id or dp.chunk_of == file_err_id for dp in results_dp[3:]), "Results from failed parser should not be yielded"

    # Check logs: ensure error was logged for error.py by _process_single_file
    # We check the logger patch applied to the orchestrator module
    error_log_found = False
    for log_call in mock_logger.error.call_args_list:
        args, kwargs = log_call
        if "Error executing parser" in args[0] and "error.py" in args[0] and "KABOOM" in args[0]:
            error_log_found = True
            break
    assert error_log_found, "Expected error log for failed parser was not found"

    # Check parse calls were made for both files
    assert mock_python_parser.parse.call_count == 2
    mock_python_parser.parse.assert_any_call(file_path=py_ok_path, file_id=file_ok_id)
    mock_python_parser.parse.assert_any_call(file_path=py_err_path, file_id=file_err_id)
