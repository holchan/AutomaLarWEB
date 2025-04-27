import os
import time
import pytest
from uuid import UUID, uuid5, NAMESPACE_OID
from typing import Optional # Added for TextChunk tests

# Attempt to import entities. This assumes the simplified import in entities.py is done
try:
    from src.parser.entities import Repository, SourceFile, CodeEntity, Dependency, TextChunk
except ImportError as e:
    print(f"ImportError in test_entities: {e}")
    # If entities aren't available, skip these tests.
    pytest.skip(f"Skipping entity tests: Failed to import entities - {e}", allow_module_level=True)


# --- Constants for Testing ---
ABS_REPO_PATH_STR = "/test/repo"
FILE_PATH_STR = "/test/repo/src/main.py"
REL_PATH_STR = "src/main.py"
EXPECTED_REPO_ID = str(uuid5(NAMESPACE_OID, ABS_REPO_PATH_STR))
EXPECTED_FILE_ID = str(uuid5(NAMESPACE_OID, FILE_PATH_STR))


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
    assert str(sf.id) == EXPECTED_FILE_ID # Compare str to str
    assert isinstance(sf.timestamp, float)

    # Check direct attributes set after super().__init__
    assert sf.name == "main.py", "SourceFile name mismatch"
    assert sf.file_path == FILE_PATH_STR, "SourceFile file_path mismatch"
    assert sf.relative_path == REL_PATH_STR, "SourceFile relative_path mismatch"
    assert sf.file_type == "python", "SourceFile file_type mismatch"
    assert sf.part_of_repository == str(EXPECTED_REPO_ID), "SourceFile part_of_repository mismatch" # Compare str to str

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

    # Check direct fields
    assert ce.type == entity_type, f"CodeEntity base type mismatch, expected {entity_type}" # Check the specific type passed as base type
    assert str(ce.id) == expected_entity_id # Compare str to str
    assert ce.text_content == source_code, "CodeEntity text_content mismatch" # Check main content field
    assert isinstance(ce.timestamp, float) # Check timestamp
    assert ce.name == name, "CodeEntity name mismatch"
    assert ce.defined_in_file == str(EXPECTED_FILE_ID), "CodeEntity defined_in_file mismatch"
    assert ce.start_line == start_line, "CodeEntity start_line mismatch"
    assert ce.end_line == end_line, "CodeEntity end_line mismatch"
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

    # Check direct fields
    assert dep.type == "Dependency", "Dependency base type mismatch"
    # --- Corrected Assertions ---
    assert str(dep.id) == expected_dep_id # Compare str to str
    assert dep.text_content == snippet, "Dependency text_content mismatch"
    assert dep.target_module == target, "Dependency target_module mismatch"
    assert dep.used_in_file == str(EXPECTED_FILE_ID), "Dependency used_in_file mismatch"
    assert dep.start_line == start_line, "Dependency start_line mismatch"
    assert dep.end_line == end_line, "Dependency end_line mismatch"
    assert isinstance(dep.timestamp, float) # Check timestamp

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
    assert tc.chunk_index == chunk_index
    assert tc.start_line == start_line_val
    assert tc.end_line == end_line_val
    assert isinstance(tc.timestamp, float) # Check timestamp

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

    assert tc.type == "TextChunk", "Minimal TextChunk base type mismatch"
    # --- Corrected Assertions ---
    assert str(tc.id) == expected_chunk_id # Compare str to str
    assert tc.text_content == text, "Minimal TextChunk text_content mismatch"
    assert tc.chunk_of == str(parent_id), "Minimal TextChunk chunk_of mismatch"
    assert tc.chunk_index == chunk_index, "Minimal TextChunk chunk_index mismatch"
    assert tc.start_line is None, "Minimal TextChunk start_line should be None"
    assert tc.end_line is None, "Minimal TextChunk end_line should be None"
    assert isinstance(tc.timestamp, float) # Check timestamp
