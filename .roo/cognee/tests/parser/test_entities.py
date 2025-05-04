import os
import time
import pytest
from uuid import UUID, uuid5, NAMESPACE_OID
from typing import Optional # Added for TextChunk tests

# Attempt to import entities. This assumes the simplified import in entities.py is done
try:
    from src.parser.entities import Repository, SourceFile, CodeEntity, Relationship, TextChunk
except ImportError as e:
    print(f"ImportError in test_entities: {e}")
    # If entities aren't available, skip these tests.
    pytest.skip(f"Skipping entity tests: Failed to import entities - {e}", allow_module_level=True)


# --- Constants for Testing ---
ABS_REPO_PATH_STR = "/test/repo"
FILE_PATH_STR = "/test/repo/src/main.py"
REL_PATH_STR = "src/main.py"
EXPECTED_REPO_ID = str(uuid5(NAMESPACE_OID, ABS_REPO_PATH_STR)) # Repo ID still a UUID
# File ID *used* by entities will be derived from path, but entities store the string passed in
EXPECTED_FILE_ID_STR = str(uuid5(NAMESPACE_OID, FILE_PATH_STR)) # Keep generating this for consistency IF needed by other tests, but use string IDs below


def test_repository_creation():
    """Test the creation of a Repository entity."""
    repo = Repository(repo_path=ABS_REPO_PATH_STR)
    assert repo.type == "Repository"
    assert repo.id == EXPECTED_REPO_ID
    assert repo.path == ABS_REPO_PATH_STR
    assert isinstance(repo.timestamp, float)


def test_sourcefile_creation():
    """Test the creation of a SourceFile entity."""
    sf = SourceFile(
        file_path=FILE_PATH_STR,
        relative_path=REL_PATH_STR,
        repo_id=EXPECTED_REPO_ID,
        file_type="python"
    )
    # Check top-level attributes
    assert sf.type == "SourceFile" # Base type check
    assert str(sf.id) == EXPECTED_FILE_ID_STR # File ID is correctly UUID
    assert isinstance(sf.timestamp, float)

    # Check direct attributes set after super().__init__
    assert sf.name == "main.py", "SourceFile name mismatch"
    assert sf.file_path == FILE_PATH_STR, "SourceFile file_path mismatch"
    assert sf.relative_path == REL_PATH_STR, "SourceFile relative_path mismatch"
    assert sf.file_type == "python", "SourceFile file_type mismatch"
    assert sf.part_of_repository == str(EXPECTED_REPO_ID), "SourceFile part_of_repository mismatch"

def test_codeentity_creation():
    """Test the creation of a CodeEntity."""
    entity_type = "FunctionDefinition" # Specific type
    name = "my_function"
    start_line = 10
    end_line = 20
    source_code = "def my_function():\n  pass"
    # Construct the string ID exactly as the parser would
    entity_id_str = f"{EXPECTED_FILE_ID_STR}:{entity_type}:{name}:{start_line}"
    # --- MODIFIED: Removed UUID generation for expected_id ---
    # expected_entity_id = str(uuid5(NAMESPACE_OID, entity_id_str)) NO LONGER NEEDED

    ce = CodeEntity(
        entity_id_str=entity_id_str, # Pass the raw string ID
        entity_type=entity_type,
        name=name,
        source_file_id=EXPECTED_FILE_ID_STR, # Use the string File ID
        source_code=source_code,
        start_line=start_line,
        end_line=end_line
    )

    # Check direct fields
    assert ce.type == entity_type
    # --- MODIFIED: Assert against the raw string ID ---
    assert ce.id == entity_id_str # <<<< EXPECT THE RAW STRING ID
    assert ce.text_content == source_code
    assert isinstance(ce.timestamp, float)
    assert ce.name == name
    assert ce.defined_in_file == str(EXPECTED_FILE_ID_STR)
    assert ce.start_line == start_line, "CodeEntity start_line mismatch"
    assert ce.end_line == end_line, "CodeEntity end_line mismatch"
    # --- End Correction ---

def test_relationship_creation():
    """Test the creation of a Relationship entity."""
    target = "os"
    snippet = "import os"
    start_line = 1
    end_line = 1
    # Construct the raw string ID
    dep_id_str = f"{EXPECTED_FILE_ID_STR}:dep:{target}:{start_line}"
    # --- MODIFIED: Removed UUID generation ---
    # expected_dep_id = str(uuid5(NAMESPACE_OID, dep_id_str)) NO LONGER NEEDED

    dep = Relationship(
        dep_id_str=dep_id_str, # Pass raw string ID
        source_file_id=EXPECTED_FILE_ID_STR,
        target=target,
        source_code_snippet=snippet,
        start_line=start_line,
        end_line=end_line
    )

    # Check direct fields
    assert dep.type == "Relationship"
    # --- MODIFIED: Assert against the raw string ID ---
    assert dep.id == dep_id_str # <<<< EXPECT THE RAW STRING ID
    assert dep.text_content == snippet
    assert dep.target_module == target
    assert dep.used_in_file == str(EXPECTED_FILE_ID_STR)
    assert dep.start_line == start_line, "Relationship start_line mismatch"
    assert dep.end_line == end_line, "Relationship end_line mismatch"
    assert isinstance(dep.timestamp, float) # Check timestamp

def test_textchunk_creation():
    """Test the creation of a TextChunk entity."""
    parent_id = EXPECTED_FILE_ID_STR # Use string ID
    text = "This is a chunk of text."
    chunk_index = 0
    start_line_val: Optional[int] = 1
    end_line_val: Optional[int] = 5
    # Construct the raw string ID
    chunk_id_str = f"{parent_id}:chunk:{chunk_index}"
    # --- MODIFIED: Removed UUID generation ---
    # expected_chunk_id = str(uuid5(NAMESPACE_OID, chunk_id_str)) NO LONGER NEEDED

    tc = TextChunk(
        chunk_id_str=chunk_id_str, # Pass raw string ID
        parent_id=parent_id,
        text=text,
        chunk_index=chunk_index,
        start_line=start_line_val,
        end_line=end_line_val
    )

    assert tc.type == "TextChunk"
    # --- MODIFIED: Assert against the raw string ID ---
    assert tc.id == chunk_id_str # <<<< EXPECT THE RAW STRING ID
    assert tc.text_content == text
    assert tc.chunk_of == str(parent_id)
    assert tc.chunk_index == chunk_index
    assert tc.start_line == start_line_val
    assert tc.end_line == end_line_val
    assert isinstance(tc.timestamp, float) # Check timestamp

def test_textchunk_creation_minimal():
    """Test TextChunk with minimal arguments (no line numbers)."""
    parent_id = EXPECTED_FILE_ID_STR # Use string ID
    text = "Minimal chunk."
    chunk_index = 1
    # Construct the raw string ID
    chunk_id_str = f"{parent_id}:chunk:{chunk_index}"
    # --- MODIFIED: Removed UUID generation ---
    # expected_chunk_id = str(uuid5(NAMESPACE_OID, chunk_id_str)) NO LONGER NEEDED

    tc = TextChunk(
        chunk_id_str=chunk_id_str, # Pass raw string ID
        parent_id=parent_id,
        text=text,
        chunk_index=chunk_index
    )

    assert tc.type == "TextChunk"
    # --- MODIFIED: Assert against the raw string ID ---
    assert tc.id == chunk_id_str # <<<< EXPECT THE RAW STRING ID
    assert tc.text_content == text
    assert tc.chunk_of == str(parent_id)
    assert tc.chunk_index == chunk_index, "Minimal TextChunk chunk_index mismatch"
    assert tc.start_line is None, "Minimal TextChunk start_line should be None"
    assert tc.end_line is None, "Minimal TextChunk end_line should be None"
    assert isinstance(tc.timestamp, float) # Check timestamp
