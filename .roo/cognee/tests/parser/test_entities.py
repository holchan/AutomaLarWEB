import os
import time
import pytest
from uuid import UUID, uuid5, NAMESPACE_OID

# Attempt to import entities. This assumes the simplified import in entities.py is done
# and cognee.low_level.DataPoint is available in the test environment.
try:
    from src.parser.entities import Repository, SourceFile, CodeEntity, Dependency, TextChunk
except ImportError as e:
    # If DataPoint isn't available, skip these tests.
    pytest.skip(f"Skipping entity tests: Failed to import entities, possibly missing cognee.low_level.DataPoint - {e}", allow_module_level=True)


# Define constants for testing consistency
REPO_PATH_STR = "/test/repo" # Use string for paths initially
ABS_REPO_PATH_STR = os.path.abspath(REPO_PATH_STR)
FILE_PATH_STR = os.path.join(ABS_REPO_PATH_STR, "src/main.py")
REL_PATH_STR = "src/main.py"

# Pre-calculate expected IDs for verification
EXPECTED_REPO_ID = str(uuid5(NAMESPACE_OID, ABS_REPO_PATH_STR))
EXPECTED_FILE_ID = str(uuid5(NAMESPACE_OID, FILE_PATH_STR))

def safe_get_payload(entity_instance):
    """Helper to get payload, trying model_dump first."""
    if hasattr(entity_instance, 'model_dump'):
        try:
            return entity_instance.model_dump()
        except Exception:
            # Fallback if model_dump fails or isn't the right method
            pass
    if hasattr(entity_instance, 'payload'):
        return entity_instance.payload
    pytest.fail("Could not access payload or model_dump on entity instance")


def test_repository_creation():
    """Test the creation of a Repository entity."""
    repo = Repository(repo_path=ABS_REPO_PATH_STR)
    payload = safe_get_payload(repo)

    assert payload.get("type") == "Repository"
    assert payload.get("path") == ABS_REPO_PATH_STR
    assert payload.get("id") == EXPECTED_REPO_ID
    assert isinstance(payload.get("timestamp"), float)
    assert time.time() - payload.get("timestamp", 0) < 5 # Check timestamp is recent

    # Check valid UUID
    assert isinstance(UUID(payload.get("id")), UUID)

def test_sourcefile_creation():
    """Test the creation of a SourceFile entity."""
    sf = SourceFile(
        file_path=FILE_PATH_STR,
        relative_path=REL_PATH_STR,
        repo_id=EXPECTED_REPO_ID,
        file_type="python"
    )
    payload = safe_get_payload(sf)

    assert payload.get("type") == "SourceFile"
    assert payload.get("name") == "main.py"
    assert payload.get("file_path") == FILE_PATH_STR
    assert payload.get("relative_path") == REL_PATH_STR
    assert payload.get("file_type") == "python"
    assert payload.get("part_of_repository") == EXPECTED_REPO_ID
    assert payload.get("id") == EXPECTED_FILE_ID
    assert isinstance(payload.get("timestamp"), float)
    assert isinstance(UUID(payload.get("id")), UUID)

def test_codeentity_creation():
    """Test the creation of a CodeEntity."""
    entity_type = "FunctionDefinition"
    name = "my_function"
    start_line = 10
    end_line = 20
    source_code = "def my_function():\n  pass"
    # Construct the string used for ID generation by the parser
    # This matches the logic within the CodeEntity __init__
    entity_id_base_str = f"{EXPECTED_FILE_ID}:{entity_type}:{name}:{start_line}"
    expected_entity_id = str(uuid5(NAMESPACE_OID, entity_id_base_str))

    ce = CodeEntity(
        entity_id_str=entity_id_base_str, # Pass the base string used for ID gen
        entity_type=entity_type,
        name=name,
        source_file_id=EXPECTED_FILE_ID,
        source_code=source_code,
        start_line=start_line,
        end_line=end_line
    )
    payload = safe_get_payload(ce)

    assert payload.get("type") == entity_type
    assert payload.get("name") == name
    assert payload.get("defined_in_file") == EXPECTED_FILE_ID
    assert payload.get("source_code_snippet") == source_code
    assert payload.get("start_line") == start_line
    assert payload.get("end_line") == end_line
    assert payload.get("id") == expected_entity_id
    assert isinstance(payload.get("timestamp"), float)
    assert isinstance(UUID(payload.get("id")), UUID)

def test_dependency_creation():
    """Test the creation of a Dependency entity."""
    target = "os"
    snippet = "import os"
    start_line = 1
    end_line = 1
    # Construct the string used for ID generation by the parser
    dep_id_base_str = f"{EXPECTED_FILE_ID}:dep:{target}:{start_line}"
    expected_dep_id = str(uuid5(NAMESPACE_OID, dep_id_base_str))

    dep = Dependency(
        dep_id_str=dep_id_base_str, # Pass base string
        source_file_id=EXPECTED_FILE_ID,
        target=target,
        source_code_snippet=snippet,
        start_line=start_line,
        end_line=end_line
    )
    payload = safe_get_payload(dep)

    assert payload.get("type") == "Dependency"
    assert payload.get("target_module") == target
    assert payload.get("used_in_file") == EXPECTED_FILE_ID
    assert payload.get("source_code_snippet") == snippet
    assert payload.get("start_line") == start_line
    assert payload.get("end_line") == end_line
    assert payload.get("id") == expected_dep_id
    assert isinstance(payload.get("timestamp"), float)
    assert isinstance(UUID(payload.get("id")), UUID)

def test_textchunk_creation():
    """Test the creation of a TextChunk entity."""
    parent_id = EXPECTED_FILE_ID
    text = "This is a chunk of text."
    chunk_index = 0
    # Construct the string used for ID generation by the parser
    chunk_id_base_str = f"{parent_id}:chunk:{chunk_index}"
    expected_chunk_id = str(uuid5(NAMESPACE_OID, chunk_id_base_str))

    tc = TextChunk(
        chunk_id_str=chunk_id_base_str, # Pass base string
        parent_id=parent_id,
        text=text,
        chunk_index=chunk_index,
        start_line=1, # Optional lines
        end_line=5   # Optional lines
    )
    payload = safe_get_payload(tc)

    assert payload.get("type") == "TextChunk"
    assert payload.get("chunk_of") == parent_id
    assert payload.get("text") == text
    assert payload.get("chunk_index") == chunk_index
    assert payload.get("start_line") == 1
    assert payload.get("end_line") == 5
    assert payload.get("id") == expected_chunk_id
    assert "metadata" in payload
    assert payload.get("metadata") == {"index_fields": ["text"]}
    assert isinstance(payload.get("timestamp"), float)
    assert isinstance(UUID(payload.get("id")), UUID)

def test_textchunk_creation_minimal():
    """Test TextChunk with minimal arguments (no line numbers)."""
    parent_id = EXPECTED_FILE_ID
    text = "Minimal chunk."
    chunk_index = 1
    chunk_id_base_str = f"{parent_id}:chunk:{chunk_index}"
    expected_chunk_id = str(uuid5(NAMESPACE_OID, chunk_id_base_str))

    tc = TextChunk(
        chunk_id_str=chunk_id_base_str,
        parent_id=parent_id,
        text=text,
        chunk_index=chunk_index
        # start_line and end_line omitted
    )
    payload = safe_get_payload(tc)

    assert payload.get("type") == "TextChunk"
    assert payload.get("chunk_of") == parent_id
    assert payload.get("text") == text
    assert payload.get("chunk_index") == chunk_index
    assert payload.get("start_line") is None # Check optional fields are None when omitted
    assert payload.get("end_line") is None
    assert payload.get("id") == expected_chunk_id
    assert payload.get("metadata") == {"index_fields": ["text"]}
