import os
import time
import pytest
from uuid import UUID, uuid5, NAMESPACE_OID, uuid4
from typing import Optional # Added for TextChunk tests

# Attempt to import entities. This assumes the simplified import in entities.py is done
# and that cognee.low_level.DataPoint is available in the environment.
try:
    from src.parser.entities import Repository, SourceFile, CodeEntity, Dependency, TextChunk
except ImportError as e:
    print(f"ImportError in test_entities: {e}")
    # If DataPoint isn't available, skip these tests.
    pytest.skip(f"Skipping entity tests: Failed to import entities, possibly missing cognee.low_level.DataPoint - {e}", allow_module_level=True)


# --- Constants for Testing ---
ABS_REPO_PATH_STR = "/test/repo"
FILE_PATH_STR = "/test/repo/src/main.py"
REL_PATH_STR = "src/main.py"
EXPECTED_REPO_ID = str(uuid5(NAMESPACE_OID, ABS_REPO_PATH_STR))
EXPECTED_FILE_ID = str(uuid5(NAMESPACE_OID, FILE_PATH_STR))


def test_repository_creation():
    """Test the creation of a Repository entity."""
    repo = Repository(repo_path=ABS_REPO_PATH_STR) # Pass absolute path for ID consistency

    # Access attributes via payload or direct (if base class defines them)
    assert repo.type == "Repository" # Check top-level type
    assert str(repo.id) == EXPECTED_REPO_ID # Compare str to str
    # --- Corrected Timestamp Check ---
    assert isinstance(repo.created_at, int) or isinstance(repo.updated_at, int)
    # Check metadata fields
    metadata = repo.metadata # Access metadata attribute
    assert metadata.get("type") == "Repository" # Type should also be in metadata
    assert metadata.get("index_fields") == []
    assert metadata.get("path") == ABS_REPO_PATH_STR # Check path in metadata
    # --- Corrected Check ---
    assert repo.path == ABS_REPO_PATH_STR # Path is now a top-level field


def test_sourcefile_creation():
    """Test the creation of a SourceFile entity."""
    sf = SourceFile(
        file_path=FILE_PATH_STR,
        relative_path=REL_PATH_STR,
        repo_id=EXPECTED_REPO_ID,
        file_type="python"
    )
    # Check top-level attributes (defined by DataPoint base or passed directly)
    assert sf.type == "SourceFile" # Base type check
    assert str(sf.id) == EXPECTED_FILE_ID # Compare str to str
    assert isinstance(sf.created_at, int) or isinstance(sf.updated_at, int)

    # Check direct attributes set after super().__init__
    assert sf.name == "main.py", "SourceFile name mismatch"
    assert sf.file_path == FILE_PATH_STR, "SourceFile file_path mismatch"
    assert sf.relative_path == REL_PATH_STR, "SourceFile relative_path mismatch"
    assert sf.file_type == "python", "SourceFile file_type mismatch"
    assert sf.part_of_repository == str(EXPECTED_REPO_ID), "SourceFile part_of_repository mismatch" # Compare str to str

    # Check metadata fields passed during init
    metadata = sf.metadata
    assert metadata.get("type") == "SourceFile" # Type should also be in metadata
    assert metadata.get("name") == "main.py" # Check metadata copy
    assert metadata.get("relative_path") == REL_PATH_STR # Check metadata copy
    assert metadata.get("index_fields") == ["name", "relative_path"]

def test_codeentity_creation():
    """Test the creation of a CodeEntity."""
    entity_type = "FunctionDefinition" # Specific type
    name = "my_function"
    start_line = 10
    end_line = 20
    source_code = "def my_function():\n  pass"
    # Construct the string used for ID generation
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

    # Check top-level fields
    assert ce.type == entity_type, f"CodeEntity base type mismatch, expected {entity_type}" # Check the specific type passed as base type
    assert str(ce.id) == expected_entity_id # Compare str to str
    assert ce.text_content == source_code, "CodeEntity text_content mismatch" # Check main content field
    assert isinstance(ce.created_at, int) or isinstance(ce.updated_at, int) # Check timestamp

    # Check metadata fields
    metadata = ce.metadata # Access metadata attribute
    assert metadata.get("type") == entity_type, "CodeEntity metadata type mismatch" # Specific type is in metadata
    # Check direct attributes set after super().__init__
    assert ce.name == name, "CodeEntity name mismatch"
    assert ce.defined_in_file == str(EXPECTED_FILE_ID), "CodeEntity defined_in_file mismatch"
    assert ce.start_line == start_line, "CodeEntity start_line mismatch"
    assert ce.end_line == end_line, "CodeEntity end_line mismatch"
    # --- End Correction ---
    assert metadata.get("index_fields") == ["text_content", "name"], "CodeEntity index_fields mismatch"

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

    # Check top-level type
    assert dep.type == "Dependency", "Dependency base type mismatch"
    # --- Corrected Assertions ---
    assert str(dep.id) == expected_dep_id # Compare str to str
    # Check direct attributes set after super().__init__
    assert dep.text_content == snippet, "Dependency text_content mismatch"
    assert dep.target_module == target, "Dependency target_module mismatch"
    assert dep.used_in_file == str(EXPECTED_FILE_ID), "Dependency used_in_file mismatch"
    assert dep.start_line == start_line, "Dependency start_line mismatch"
    assert dep.end_line == end_line, "Dependency end_line mismatch"
    assert isinstance(dep.created_at, int) or isinstance(dep.updated_at, int) # Check timestamp
    # --- End Correction ---

    # Check metadata fields for details
    metadata = dep.metadata
    assert metadata.get("type") == "Dependency" # Type should also be in metadata
    # --- Corrected Check ---
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

    assert tc.type == "TextChunk", "TextChunk base type mismatch"
    # --- Corrected Assertions ---
    assert str(tc.id) == expected_chunk_id # Compare str to str
    # Check direct attributes set after super().__init__
    assert tc.text_content == text, "TextChunk text_content mismatch"
    assert tc.chunk_of == str(parent_id), "TextChunk chunk_of mismatch"
    assert tc.chunk_index == chunk_index, "TextChunk chunk_index mismatch"
    assert tc.start_line == start_line_val, "TextChunk start_line mismatch"
    assert tc.end_line == end_line_val, "TextChunk end_line mismatch"
    assert isinstance(tc.created_at, int) or isinstance(tc.updated_at, int) # Check timestamp
    # --- End Correction ---

    # Check metadata fields for details
    metadata = tc.metadata
    assert metadata.get("type") == "TextChunk"
    # Check metadata for link and optional fields passed via kwargs
    assert metadata.get("chunk_of") == str(parent_id), "TextChunk chunk_of in metadata mismatch" # Compare str to str
    assert metadata.get("index_fields") == ["text_content"] # Check required field

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

    assert tc.type == "TextChunk", "Minimal TextChunk base type mismatch" # Top level type
    # --- Corrected Assertions ---
    assert str(tc.id) == expected_chunk_id # Compare str to str
    assert tc.text_content == text, "Minimal TextChunk text_content mismatch"
    assert tc.chunk_of == str(parent_id), "Minimal TextChunk chunk_of mismatch"
    assert tc.chunk_index == chunk_index, "Minimal TextChunk chunk_index mismatch"
    assert tc.start_line is None, "Minimal TextChunk start_line should be None"
    assert tc.end_line is None, "Minimal TextChunk end_line should be None"
    assert isinstance(tc.created_at, int) or isinstance(tc.updated_at, int) # Check timestamp
    # --- End Correction ---
    # Check metadata fields
    metadata = tc.metadata
    assert metadata.get("type") == "TextChunk" # Check nested type
    # Check metadata for link
    assert metadata.get("chunk_of") == str(parent_id), "Minimal TextChunk chunk_of in metadata mismatch" # Compare str to str
    assert metadata.get("index_fields") == ["text_content"] # Check required field
    assert "start_line" not in metadata, "Minimal TextChunk should not have start_line in metadata"
    assert "end_line" not in metadata, "Minimal TextChunk should not have end_line in metadata"
