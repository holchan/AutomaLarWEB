import os
from typing import List, Optional, Dict, Any
from uuid import NAMESPACE_OID, uuid5
import time

# --- Cognee Imports ---
# Directly import the required base class.
# If 'cognee' or 'cognee.low_level.DataPoint' is not available in the
# environment where this code runs, Python will raise a standard ImportError.
from cognee.low_level import DataPoint

# --- Entity Definitions ---
# Docstrings added previously remain

class Repository(DataPoint):
    """
    Represents the root of the scanned directory or repository.
    Inherits from DataPoint.
    Attributes: ... (docstring content)
    """
    def __init__(self, repo_path: str):
        payload = dict(
            type = "Repository",
            path = repo_path,
            timestamp = time.time(),
        )
        repo_id = str(uuid5(NAMESPACE_OID, os.path.abspath(repo_path)))
        super().__init__(id=repo_id, **payload)

class SourceFile(DataPoint):
    """
    Represents any discovered source file (code, configuration, documentation, etc.).
    Inherits from DataPoint.
    Attributes: ... (docstring content)
    """
    def __init__(self, file_path: str, relative_path: str, repo_id: str, file_type: str):
        payload = dict(
            type = "SourceFile",
            name = os.path.basename(file_path),
            file_path = file_path, # Absolute path
            relative_path = relative_path, # Path relative to repo root
            file_type = file_type, # e.g., 'python', 'markdown', 'dockerfile'
            part_of_repository = repo_id, # Link to parent repository ID
            timestamp = time.time(),
        )
        file_id = str(uuid5(NAMESPACE_OID, os.path.abspath(file_path)))
        super().__init__(id=file_id, **payload)

class CodeEntity(DataPoint):
    """
    Generic representation for code elements like functions, classes, structs, enums, etc.
    Inherits from DataPoint.
    Attributes: ... (docstring content)
    """
    def __init__(self, entity_id_str: str, entity_type: str, name: str, source_file_id: str, source_code: str, start_line: int, end_line: int):
        payload = dict(
            type = entity_type,
            name = name,
            defined_in_file = source_file_id,
            source_code_snippet = source_code,
            start_line = start_line,
            end_line = end_line,
            timestamp = time.time(),
        )
        # ID generation uses the unique string passed in
        entity_id = str(uuid5(NAMESPACE_OID, entity_id_str))
        super().__init__(id=entity_id, **payload)

class Dependency(DataPoint):
    """
    Represents imports, includes, use statements, or other forms of code dependencies.
    Inherits from DataPoint.
    Attributes: ... (docstring content)
    """
    def __init__(self, dep_id_str: str, source_file_id: str, target: str, source_code_snippet: str, start_line: int, end_line: int):
        payload = dict(
            type = "Dependency",
            target_module = target,
            used_in_file = source_file_id,
            source_code_snippet = source_code_snippet,
            start_line = start_line,
            end_line = end_line,
            timestamp = time.time(),
        )
        # ID generation uses the unique string passed in
        dep_id = str(uuid5(NAMESPACE_OID, dep_id_str))
        super().__init__(id=dep_id, **payload)

class TextChunk(DataPoint):
    """
    Represents a segment of text derived from a file or a specific code entity.
    Inherits from DataPoint.
    Attributes: ... (docstring content)
    """
    def __init__(self, chunk_id_str: str, parent_id: str, text: str, chunk_index: int, start_line: Optional[int] = None, end_line: Optional[int] = None):
        payload = dict(
            type = "TextChunk",
            chunk_of = parent_id,
            text = text,
            chunk_index = chunk_index,
            start_line = start_line,
            end_line = end_line,
            timestamp = time.time(),
            metadata = {"index_fields": ["text"]},
        )
        # ID generation uses the unique string passed in
        chunk_id = str(uuid5(NAMESPACE_OID, chunk_id_str))
        super().__init__(id=chunk_id, **payload)

# Optional: Rebuild models if using Pydantic features within Cognee's DataPoint
if hasattr(DataPoint, 'model_rebuild'):
    try:
        Repository.model_rebuild()
        SourceFile.model_rebuild()
        CodeEntity.model_rebuild()
        Dependency.model_rebuild()
        TextChunk.model_rebuild()
    except Exception as e:
        # Log if model rebuild fails, might indicate incompatibility
        # Requires logger setup from .utils
        # print(f"Warning: Failed to rebuild Pydantic models for custom entities: {e}")
        pass
