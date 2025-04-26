# FILE: src/parser/entities.py

# --- Imports ---
import os
import time
from typing import List, Optional, Dict, Any
from uuid import NAMESPACE_OID, uuid5, UUID # Added UUID for type hints if needed
from cognee.low_level import DataPoint # Direct import

# --- Entity Definitions ---

class Repository(DataPoint):
    """Represents the root repository."""
    def __init__(self, repo_path: str):
        repo_id = str(uuid5(NAMESPACE_OID, os.path.abspath(repo_path)))
        payload = dict(
            id=repo_id,
            type="Repository", # Top-level type for DataPoint system
            metadata=dict(
                type="Repository", # Type within metadata (required)
                path=os.path.abspath(repo_path), # Store absolute path
                index_fields=[], # Required, but maybe none to index here
            ),
            timestamp=time.time(),
        )
        super().__init__(**payload)

class SourceFile(DataPoint):
    """Represents a discovered source file."""
    def __init__(self, file_path: str, relative_path: str, repo_id: str, file_type: str):
        file_id = str(uuid5(NAMESPACE_OID, os.path.abspath(file_path)))
        payload = dict(
            id=file_id,
            type="SourceFile",
            metadata=dict(
                type="SourceFile", # Required
                name=os.path.basename(file_path),
                file_path=file_path,
                relative_path=relative_path,
                file_type=file_type,
                part_of_repository=repo_id,
                index_fields=[], # Required
            ),
            timestamp=time.time(),
        )
        super().__init__(**payload)

class CodeEntity(DataPoint):
    """Represents a code element like a function or class."""
    def __init__(self, entity_id_str: str, entity_type: str, name: str, source_file_id: str, source_code: str, start_line: int, end_line: int):
         entity_id = str(uuid5(NAMESPACE_OID, entity_id_str))
         payload = dict(
             id=entity_id,
             type=entity_type, # Use specific type (e.g., FunctionDefinition)
             text_content=source_code, # Store main content here
             metadata=dict(
                 type=entity_type, # Required
                 name=name,
                 defined_in_file=source_file_id,
                 start_line=start_line,
                 end_line=end_line,
                 source_code_snippet_field="text_content", # Point to main content field
                 index_fields=["text_content", "name"], # Index content and name
             ),
             timestamp=time.time(),
         )
         super().__init__(**payload)

class Dependency(DataPoint):
    """Represents an import or include statement."""
    def __init__(self, dep_id_str: str, source_file_id: str, target: str, source_code_snippet: str, start_line: int, end_line: int):
        dep_id = str(uuid5(NAMESPACE_OID, dep_id_str))
        payload = dict(
            id=dep_id,
            type="Dependency",
            text_content=source_code_snippet, # Store snippet as main content
            metadata=dict(
                type="Dependency", # Required
                target_module=target,
                used_in_file=source_file_id,
                start_line=start_line,
                end_line=end_line,
                index_fields=["text_content", "target_module"], # Index snippet and target
            ),
            timestamp=time.time(),
        )
        super().__init__(**payload)

class TextChunk(DataPoint):
    """Represents a segment of text."""
    def __init__(self, chunk_id_str: str, parent_id: str, text: str, chunk_index: int, start_line: Optional[int] = None, end_line: Optional[int] = None):
        chunk_id = str(uuid5(NAMESPACE_OID, chunk_id_str))
        payload = dict(
            id=chunk_id,
            type="TextChunk", # Top-level type
            text_content=text, # Main content field
            metadata=dict(
                type="TextChunk", # Required nested type
                chunk_of=parent_id,
                chunk_index=chunk_index,
                start_line=start_line,
                end_line=end_line,
                index_fields=["text_content"], # Required, index the text
            ),
            timestamp=time.time(),
        )
         # Remove None values from metadata before passing (optional fields)
        payload["metadata"] = {k: v for k, v in payload["metadata"].items() if v is not None}
        super().__init__(**payload)

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
