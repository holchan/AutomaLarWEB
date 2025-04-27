import os
import time
import pytest
from uuid import UUID, uuid5, NAMESPACE_OID
from typing import Optional # Added for TextChunk tests

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
    """Helper to get payload dict, trying model_dump first."""
    if hasattr(entity_instance, 'model_dump'):
        try:
            # Use mode='json' to handle types like UUID automatically for serialization checks
            return entity_instance.model_dump(mode='json')
        except Exception as e:
             print(f"Warning: model_dump failed: {e}")
             # Fallback or fail if model_dump doesn't work as expected
             pass
    pytest.fail(f"Could not access model_dump() on entity instance: {entity_instance}")


def test_repository_creation():
    """Test the creation of a Repository entity."""
    repo = Repository(repo_path=ABS_REPO_PATH_STR) # Pass absolute path for ID consistency
    payload = safe_get_payload(repo)

    assert payload.get("type") == "Repository" # Check top-level type
    assert payload.get("id") == EXPECTED_REPO_ID # Compare str to str
    # --- Corrected Timestamp Check ---
    assert isinstance(payload.get("created_at"), int) or isinstance(payload.get("updated_at"), int)

    # Check metadata fields
    metadata = payload.get("metadata", {})
    assert metadata.get("type") == "Repository" # Type should also be in metadata
    assert metadata.get("path") == ABS_REPO_PATH_STR # Path is inside metadata now
    assert metadata.get("index_fields") == []

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
    assert payload.get("id") == EXPECTED_FILE_ID # Compare str to str
    # --- Corrected Timestamp Check ---
    assert isinstance(payload.get("created_at"), int) or isinstance(payload.get("updated_at"), int)

    # Check metadata fields
    metadata = payload.get("metadata", {})
    assert metadata.get("type") == "SourceFile" # Type should also be in metadata
    assert metadata.get("name") == "main.py"
    assert metadata.get("file_path") == FILE_PATH_STR
    assert metadata.get("relative_path") == REL_PATH_STR
    assert metadata.get("file_type") == "python"
    assert metadata.get("part_of_repository") == EXPECTED_REPO_ID
    assert metadata.get("index_fields") == ["name", "relative_path"]

def test_codeentity_creation():
    """Test the creation of a CodeEntity."""
    entity_type = "FunctionDefinition" # Specific type
    name = "my_function"
    start_line = 10
    end_line = 20
    source_code = "def my_function():\n  pass"
    # Construct the string used for ID generation by the parser
    entity_id_base_str = f"{EXPECTED_FILE_ID}:{entity_type}:{name}:{start_line}"
    expected_entity_id = str(uuid5(NAMESPACE_OID, entity_id_base_str))

    ce = CodeEntity(
        entity_id_str=entity_id_base_str, # Pass the base string used for ID gen
        entity_type=entity_type, # Pass the specific type
        name=name,
        source_file_id=EXPECTED_FILE_ID,
        source_code=source_code,
        start_line=start_line,
        end_line=end_line
    )
    payload = safe_get_payload(ce)

    # Check standard top-level fields
    # --- Corrected Assertions ---
    assert payload.get("type") == entity_type # Check the specific type passed
    assert payload.get("id") == expected_entity_id # Compare str to str
    assert payload.get("text_content") == source_code # Check main content field
    assert isinstance(payload.get("created_at"), int) or isinstance(payload.get("updated_at"), int) # Check timestamp

    # Check metadata fields
    metadata = payload.get("metadata", {})
    assert metadata.get("type") == entity_type # Specific type is in metadata
    assert metadata.get("name") == name
    assert metadata.get("defined_in_file") == EXPECTED_FILE_ID
    assert metadata.get("start_line") == start_line
    assert metadata.get("end_line") == end_line
    assert metadata.get("source_code_snippet_field") == "text_content" # Check snippet field name
    assert metadata.get("index_fields") == ["text_content", "name"]
# --- End Correction ---

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
        target=target, # This becomes target_module in metadata
        source_code_snippet=snippet, # This becomes text_content
        start_line=start_line,
        end_line=end_line
    )
    payload = safe_get_payload(dep)

    assert payload.get("type") == "Dependency"
    # --- Corrected Assertions ---
    assert payload.get("id") == expected_dep_id # Compare str to str
    assert payload.get("text_content") == snippet # Check standard field
    assert isinstance(payload.get("created_at"), int) or isinstance(payload.get("updated_at"), int) # Check timestamp
    # --- End Correction ---

    # Check metadata fields
    metadata = payload.get("metadata", {})
    assert metadata.get("type") == "Dependency" # Type should also be in metadata
    assert metadata.get("target_module") == target # target is now in metadata
    assert metadata.get("used_in_file") == EXPECTED_FILE_ID
    assert metadata.get("start_line") == start_line
    assert metadata.get("end_line") == end_line
    assert metadata.get("index_fields") == ["text_content", "target_module"]

def test_textchunk_creation():
    """Test the creation of a TextChunk entity."""
    parent_id = EXPECTED_FILE_ID
    text = "This is a chunk of text."
    chunk_index = 0
    start_line_val: Optional[int] = 1
    end_line_val: Optional[int] = 5
    # Construct the string used for ID generation by the parser
    chunk_id_base_str = f"{parent_id}:chunk:{chunk_index}"
    expected_chunk_id = str(uuid5(NAMESPACE_OID, chunk_id_base_str))

    tc = TextChunk(
        chunk_id_str=chunk_id_base_str, # Pass base string
        parent_id=parent_id, # This becomes chunk_of in metadata
        text=text, # This becomes text_content
        chunk_index=chunk_index,
        start_line=start_line_val, # Optional lines
        end_line=end_line_val   # Optional lines
    )
    payload = safe_get_payload(tc)

    assert payload.get("type") == "TextChunk" # Top level type
    # --- Corrected Assertions ---
    assert payload.get("id") == expected_chunk_id # Compare str to str
    assert payload.get("text_content") == text # Check standard field
    assert isinstance(payload.get("created_at"), int) or isinstance(payload.get("updated_at"), int) # Check timestamp
    # --- End Correction ---

    # Check metadata fields
    metadata = payload.get("metadata", {})
    assert metadata.get("type") == "TextChunk" # Check nested type
    assert metadata.get("chunk_of") == parent_id # chunk_of is now in metadata
    assert metadata.get("chunk_index") == chunk_index
    assert metadata.get("start_line") == start_line_val # start_line is now in metadata
    assert metadata.get("end_line") == end_line_val # end_line is now in metadata
    assert metadata.get("index_fields") == ["text_content"] # Check required field
    # Check optional fields were included in metadata if not None
    assert "start_line" in metadata # Ensure optional fields are present in metadata
    assert "end_line" in metadata


def test_textchunk_creation_minimal():
    """Test TextChunk with minimal arguments (no line numbers)."""
    parent_id = EXPECTED_FILE_ID
    text = "Minimal chunk."
    chunk_index = 1
    chunk_id_base_str = f"{parent_id}:chunk:{chunk_index}"
    expected_chunk_id = str(uuid5(NAMESPACE_OID, chunk_id_base_str))

    tc = TextChunk(
        chunk_id_str=chunk_id_base_str,
        parent_id=parent_id, # This becomes chunk_of in metadata
        text=text, # This becomes text_content
        chunk_index=chunk_index
        # start_line and end_line omitted
    )
    payload = safe_get_payload(tc)

    assert payload.get("type") == "TextChunk"
    # --- Corrected Assertions ---
    assert payload.get("id") == expected_chunk_id # Compare str to str
    assert payload.get("text_content") == text # Check main text field
    assert isinstance(payload.get("created_at"), int) or isinstance(payload.get("updated_at"), int) # Check timestamp
    # --- End Correction ---

    # Check metadata fields
    metadata = payload.get("metadata", {})
    assert metadata.get("type") == "TextChunk" # Check nested type
    assert metadata.get("chunk_of") == parent_id # chunk_of is now in metadata
    assert metadata.get("chunk_index") == chunk_index
    assert metadata.get("index_fields") == ["text_content"] # Check required field
    # Check optional fields are absent in metadata when None
    assert "start_line" not in metadata # Ensure optional fields are absent
    assert "end_line" not in metadata
