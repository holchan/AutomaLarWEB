from typing import AsyncGenerator
from uuid import uuid5, NAMESPACE_OID
import pytest
import asyncio
import os
from pathlib import Path
# Use unittest.mock for its robust patching capabilities, especially with async
from unittest.mock import AsyncMock, MagicMock, patch, call, ANY # Import ANY
from typing import List, Dict, Any, Optional, Tuple

# Ensure pytest-asyncio is installed and usable
pytestmark = pytest.mark.asyncio

# Import the function to test and entity types for verification
try:
    from src.parser.orchestrator import process_repository, _process_single_file # Import helper too
    # Import specific entity types for instantiation in mocks and type checks
    from src.parser.entities import Repository, SourceFile, TextChunk, CodeEntity, Relationship
except ImportError as e:
     pytest.skip(f"Skipping orchestrator tests: Failed to import dependencies - {e}", allow_module_level=True)


# --- Mock Data Setup ---

# Helper to create mock payloads (dictionaries representing entity data)
def create_mock_payload(id_val: str, type_val: str, parent_id: str = None, text_content: str = "", **kwargs) -> dict:
    """Creates a dictionary representing entity data for mocking."""
    payload = {
        "id": id_val,
        "type": type_val,
        "text_content": text_content, # Added text_content
        # Add keys based on type for more realistic mocks if needed by assertions
        "chunk_of": parent_id if type_val == "TextChunk" else None,
        "defined_in_file": parent_id if type_val in ["FunctionDefinition", "ClassDefinition"] else None,
        "used_in_file": parent_id if type_val == "Relationship" else None,
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

# --- Updated Helper to create standalone entity instances ---
def create_entity_instance(payload: Dict):
    """Creates a standalone entity instance from a payload dictionary."""
    type_val = payload.get("type")
    str_parent_id = str(payload.get("chunk_of") or payload.get("defined_in_file") or payload.get("used_in_file"))

    dp = None
    if type_val == "TextChunk":
        dp = TextChunk(
            chunk_id_str=payload.get("id"),
            parent_id=str_parent_id,
            text=payload.get("text_content", ""),
            chunk_index=payload.get("chunk_index"),
            start_line=payload.get("start_line"),
            end_line=payload.get("end_line")
        )
    elif type_val in ["FunctionDefinition", "ClassDefinition", "StructDefinition", "EnumDefinition", "TraitDefinition", "Implementation", "MacroDefinition", "ModuleDefinition"]:
        dp = CodeEntity(
            entity_id_str=payload.get("id"),
            entity_type=type_val,
            name=payload.get("name"),
            source_file_id=str_parent_id,
            source_code=payload.get("text_content", ""),
            start_line=payload.get("start_line"),
            end_line=payload.get("end_line")
        )
    elif type_val == "Relationship":
        dp = Relationship(
            dep_id_str=payload.get("id"),
            source_file_id=str_parent_id,
            target=payload.get("target_module"),
            source_code_snippet=payload.get("text_content", ""),
            start_line=payload.get("start_line"),
            end_line=payload.get("end_line")
        )
    else:
        print(f"Warning: Mock instance creator encountered unknown type: {type_val}")
    return dp

# Define expected IDs and mock parser outputs based on mock discovery
def setup_expected_outcomes(base_path: Path) -> dict:
    """Calculates expected IDs and defines mock parser outputs."""
    mock_discovery = get_mock_discovery_data(base_path)
    repo_root = base_path / "mock_repo"
    abs_repo_path = str(repo_root.absolute())
    # --- Corrected setup_expected_outcomes ---
    outcomes = {
        "repo_id": str(uuid5(NAMESPACE_OID, abs_repo_path)),
        "file_ids": {}, # Map rel_path -> file_id (string)
        "parser_outputs": {}, # Map file_id (string) -> list of ENTITY INSTANCES
    }
    for abs_p, rel_p, f_type in mock_discovery:
        file_id_str = str(uuid5(NAMESPACE_OID, os.path.abspath(abs_p))) # Calculate string ID
        outcomes["file_ids"][rel_p] = file_id_str # Store string ID

        mock_payloads = [] # Start with empty list
        if f_type == "python":
            mock_payloads = [
                create_mock_payload(f"{file_id_str}:chunk:0", "TextChunk", parent_id=file_id_str, chunk_index=0, text_content="mock python text chunk 1"),
                create_mock_payload(f"{file_id_str}:FunctionDefinition:main:10", "FunctionDefinition", parent_id=file_id_str, name="main", start_line=10, end_line=15, text_content="def main():\n  pass"),
                create_mock_payload(f"{file_id_str}:dep:os:1", "Relationship", parent_id=file_id_str, target_module="os", start_line=1, end_line=1, text_content="import os"),
            ]
        elif f_type == "markdown":
            mock_payloads = [
                create_mock_payload(f"{file_id_str}:chunk:0", "TextChunk", parent_id=file_id_str, chunk_index=0, text_content="mock markdown text chunk 1"),
                create_mock_payload(f"{file_id_str}:chunk:1", "TextChunk", parent_id=file_id_str, chunk_index=1, text_content="mock markdown text chunk 2"),
             ]
        elif f_type == "javascript":
             mock_payloads = [
                create_mock_payload(f"{file_id_str}:ClassDefinition:App:5", "ClassDefinition", parent_id=file_id_str, name="App", start_line=5, end_line=20, text_content="class App {}"),
                create_mock_payload(f"{file_id_str}:dep:react:1", "Relationship", parent_id=file_id_str, target_module="react", start_line=1, end_line=1, text_content="import React from 'react'"),
             ]

        # Convert payloads to entity instances
        outcomes["parser_outputs"][file_id_str] = [create_entity_instance(p) for p in mock_payloads if create_entity_instance(p) is not None]


    return outcomes


# Async generator helper for discovery mock
async def async_gen_wrapper(item_list: List[tuple]):
    """Wraps a list of items in a simple async generator."""
    for item in item_list:
        yield item
        await asyncio.sleep(0) # Yield control


# --- Test Cases ---

@patch('src.parser.orchestrator.discover_files')
@patch('src.parser.orchestrator._process_single_file') # <<< MOCK the helper
async def test_process_repository_basic_flow(mock_process_single_file, mock_discover, tmp_path: Path):
    """
    Tests the main success path: discovery, repo/file yielding, parser dispatch, result yielding.
    """
    repo_path = tmp_path / "mock_repo"
    repo_path.mkdir()

    # Setup expected outcomes and mock data based on tmp_path
    expected_outcomes = setup_expected_outcomes(tmp_path)
    mock_discovery_data = get_mock_discovery_data(tmp_path)

    # Create dummy files so paths exist
    for abs_p, _, _ in mock_discovery_data:
        Path(abs_p).parent.mkdir(parents=True, exist_ok=True)
        Path(abs_p).touch()

    # Configure mock discovery
    mock_discover.return_value = async_gen_wrapper(mock_discovery_data)

    # --- Configure mock _process_single_file side effect ---
    # This async function will BE the side effect
    async def process_side_effect(parser_instance, file_path, file_id):
        file_id_str = str(file_id)
        print(f"--- Mock _process_single_file ASYNC side effect called for {file_id_str} ---") # DEBUG
        results = expected_outcomes["parser_outputs"].get(file_id_str, [])
        print(f"--- Mock _process_single_file ASYNC returning {len(results)} items for {file_id_str} ---") # DEBUG
        # Directly return the list - gather will await this coroutine
        return results

    mock_process_single_file.side_effect = process_side_effect

    # --- Execute Test ---
    results_dp_objects = []
    async for dp in process_repository(str(repo_path)):
        results_dp_objects.append(dp)

    # --- Assertions ---
    # 1. Check total items yielded
    expected_parser_results_count = sum(len(v) for v in expected_outcomes["parser_outputs"].values())
    # Total = 1 Repo + N Files + M Parser Results
    expected_total_yields = 1 + len(mock_discovery_data) + expected_parser_results_count
    assert len(results_dp_objects) == expected_total_yields, f"Incorrect total yielded: {len(results_dp_objects)} vs {expected_total_yields}"

    # 2. Check Repository node
    repo_dp = results_dp_objects[0]
    assert isinstance(repo_dp, Repository), f"First item should be Repository, got {type(repo_dp)}"
    assert repo_dp.id == expected_outcomes["repo_id"]

    # 3. Check SourceFile nodes
    yielded_files = results_dp_objects[1 : 1 + len(mock_discovery_data)]
    assert len(yielded_files) == len(mock_discovery_data), "Incorrect number of SourceFile nodes yielded"
    assert all(isinstance(dp, SourceFile) for dp in yielded_files)
    yielded_file_ids = {dp.id for dp in yielded_files}
    expected_file_ids = set(expected_outcomes["file_ids"].values())
    assert yielded_file_ids == expected_file_ids

    # 4. Check Parser results
    parser_results = results_dp_objects[1 + len(mock_discovery_data):]
    assert len(parser_results) == expected_parser_results_count
    yielded_parser_ids = {dp.id for dp in parser_results}
    expected_parser_ids = set()
    for file_id_str in expected_outcomes["parser_outputs"]:
        expected_parser_ids.update(dp.id for dp in expected_outcomes["parser_outputs"][file_id_str])
    assert yielded_parser_ids == expected_parser_ids

    # 5. Check mock calls
    mock_discover.assert_called_once_with(str(repo_path.absolute()))


@patch('src.parser.orchestrator.discover_files')
@patch('src.parser.orchestrator._process_single_file') # <<< MOCK the helper
@patch('src.parser.orchestrator.logger')
async def test_process_repository_parser_error_handling(mock_logger, mock_process_single_file, mock_discover, tmp_path: Path):
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
    repo_id = str(uuid5(NAMESPACE_OID, abs_repo_path))
    file_ok_id = str(uuid5(NAMESPACE_OID, os.path.abspath(py_ok_path)))
    file_err_id = str(uuid5(NAMESPACE_OID, os.path.abspath(py_err_path)))

    # Expected successful payload (as dict)
    ok_payload = create_mock_payload(f"{file_ok_id}:chunk:0", "TextChunk", parent_id=file_ok_id, text_content="OK chunk", chunk_index=0)
    ok_entity = create_entity_instance(ok_payload)

    # Configure mock _process_single_file side effect
    simulated_error = ValueError("KABOOM! Simulated parsing error.")
    # This async function IS the side effect
    async def error_side_effect(parser_instance, file_path, file_id):
        file_id_str = str(file_id)
        print(f"--- Error ASYNC Side Effect called for {file_id_str} ---") # DEBUG
        if "ok.py" in file_path:
            assert file_id_str == file_ok_id
            print(f"--- Error ASYNC Side Effect: Returning OK entity list for {file_id_str} ---") # DEBUG
            return [ok_entity] # Return the list directly
        elif "error.py" in file_path:
            assert file_id_str == file_err_id
            print(f"--- Error ASYNC Side Effect: Raising error for {file_id_str} ---") # DEBUG
            raise simulated_error # Raise directly from the awaited coroutine
        else:
             print(f"--- Error ASYNC Side Effect: Returning empty list for {file_id_str} ---") # DEBUG
             return [] # Return empty list directly

    mock_process_single_file.side_effect = error_side_effect

    # --- Execute ---
    results_dp = []
    async for dp in process_repository(str(repo_path), concurrency_limit=1):
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
    expected_ok_payload_id = ok_payload.get("id")
    assert any(str(dp.id) == expected_ok_payload_id for dp in results_dp), "Payload from ok.py missing"
    # Check that no parser results related to error.py are present
    # Access parent links directly from the object attributes
    # The first 3 results are Repo and the two SourceFiles
    parser_results = results_dp[3:]
    failed_file_results_present = False
    for dp in parser_results:
        # Check if the parent link matches the failed file ID (using direct attributes)
        defined_in = getattr(dp, 'defined_in_file', None) # Use getattr with default None
        used_in = getattr(dp, 'used_in_file', None)
        chunk_of = getattr(dp, 'chunk_of', None)
        # Compare against string ID
        str_file_err_id = str(file_err_id) # Ensure comparison is string vs string
        if defined_in == str_file_err_id or used_in == str_file_err_id or chunk_of == str_file_err_id:
             failed_file_results_present = True
             break
    assert not failed_file_results_present, "Results from failed parser should not be yielded"


    # Check logs: ensure error was logged for error.py by the main loop
    error_log_found = False
    for log_call in mock_logger.error.call_args_list:
        args, kwargs = log_call
        # Check the log message generated by the gather loop
        if args and isinstance(args[0], str):
           if args[0].startswith("A file processing task failed:") and "KABOOM" in args[0]:
            error_log_found = True
            break
    assert error_log_found, "Expected error log for failed task was not found"


    # Check _process_single_file calls were made for both files
    assert mock_process_single_file.call_count == 2, "_process_single_file method not called expected number of times"
    # Assert calls using the string file IDs
    mock_process_single_file.assert_any_call(ANY, py_ok_path, file_ok_id)
    mock_process_single_file.assert_any_call(ANY, py_err_path, file_err_id)
