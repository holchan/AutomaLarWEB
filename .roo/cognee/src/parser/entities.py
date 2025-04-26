# FILE: src/parser/entities.py

# --- Imports ---
import os
import time
from typing import List, Optional, Dict, Any
from uuid import NAMESPACE_OID, uuid5, UUID # Import UUID
from cognee.low_level import DataPoint

# --- Entity Definitions ---

# Helper to create metadata dict, ensuring required fields exist
def _create_metadata(entity_specific_type: str, index_fields: List[str] = [], **kwargs) -> Dict[str, Any]:
    """Creates the metadata dict, ensuring required fields and removing None values."""
    meta = {
        "type": entity_specific_type, # Required field
        "index_fields": index_fields, # Required field
        **kwargs # Add other custom metadata
    }
    # Remove None values from optional metadata fields passed via kwargs
    return {k: v for k, v in meta.items() if v is not None}

class Repository(DataPoint):
    """Represents the root repository."""
    def __init__(self, repo_path: str):
        abs_path = os.path.abspath(repo_path)
        repo_id = str(uuid5(NAMESPACE_OID, abs_path))
        payload = dict(
            id=repo_id,
            type="Repository", # Top-level type for DataPoint system
            # Custom fields directly in payload
            path=abs_path,
            # Required metadata
            metadata=_create_metadata(
                entity_specific_type="Repository",
                # No specific fields to index for Repository itself
                index_fields=[],
            ),
            # timestamp is likely added by DataPoint base, check if needed here
            # timestamp=time.time(),
        )
        super().__init__(**payload)

class SourceFile(DataPoint):
    """Represents a discovered source file."""
    def __init__(self, file_path: str, relative_path: str, repo_id: str, file_type: str):
        abs_path = os.path.abspath(file_path)
        file_id = str(uuid5(NAMESPACE_OID, abs_path))
        payload = dict(
            id=file_id,
            type="SourceFile",
            # Custom fields directly in payload
            name=os.path.basename(file_path),
            file_path=file_path, # Keep original path if useful
            relative_path=relative_path,
            file_type=file_type,
            part_of_repository=repo_id,
            # Required metadata
            metadata=_create_metadata(
                entity_specific_type="SourceFile",
                # Index name and path? Or leave empty?
                index_fields=["name", "relative_path"],
            ),
            # timestamp=time.time(),
        )
        super().__init__(**payload)

class CodeEntity(DataPoint):
    """Represents a code element like a function or class."""
    def __init__(self, entity_id_str: str, entity_type: str, name: str, source_file_id: str, source_code: str, start_line: int, end_line: int):
         entity_id = str(uuid5(NAMESPACE_OID, entity_id_str))
         payload = dict(
             id=entity_id,
             type=entity_type, # Use specific type like FunctionDefinition
             # Custom fields directly in payload
             name=name,
             defined_in_file=source_file_id,
             start_line=start_line,
             end_line=end_line,
             text_content=source_code, # Assume base DataPoint has text_content field
             # Required metadata
             metadata=_create_metadata(
                 entity_specific_type=entity_type,
                 # Indicate which field holds the primary text for indexing
                 index_fields=["text_content", "name"],
             ),
             # timestamp=time.time(),
         )
         super().__init__(**payload)

class Dependency(DataPoint):
    """Represents an import or include statement."""
    def __init__(self, dep_id_str: str, source_file_id: str, target: str, source_code_snippet: str, start_line: int, end_line: int):
        dep_id = str(uuid5(NAMESPACE_OID, dep_id_str))
        payload = dict(
            id=dep_id,
            type="Dependency",
            # Custom fields directly in payload
            target_module=target,
            used_in_file=source_file_id,
            start_line=start_line,
            end_line=end_line,
            text_content=source_code_snippet, # Snippet as main content?
            metadata=_create_metadata(
                entity_specific_type="Dependency",
                index_fields=["text_content", "target_module"],
            ),
            # timestamp=time.time(),
        )
        super().__init__(**payload)

class TextChunk(DataPoint):
    """Represents a segment of text."""
    def __init__(self, chunk_id_str: str, parent_id: str, text: str, chunk_index: int, start_line: Optional[int] = None, end_line: Optional[int] = None):
        chunk_id = str(uuid5(NAMESPACE_OID, chunk_id_str))
        payload = dict(
            id=chunk_id,
            type="TextChunk", # Top-level type
            # Custom fields directly in payload
            chunk_of=parent_id,
            chunk_index=chunk_index,
            start_line=start_line, # Keep optional fields here
            end_line=end_line,
            text_content=text, # Main content field
            # Required metadata
            metadata=_create_metadata(
                entity_specific_type="TextChunk",
                index_fields=["text_content"], # Index the text
                # Pass optional fields to helper so they are removed if None
                start_line=start_line,
                end_line=end_line,
            ),
            # timestamp=time.time(),
        )
        super().__init__(**payload)

# Optional: Rebuild models (keep as is)
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
