# FILE: src/parser/entities.py

# --- Imports ---
import os, sys
import time
from typing import List, Optional, Dict, Any
from uuid import NAMESPACE_OID, uuid5, UUID # Import UUID
from cognee.infrastructure.engine.models import DataPoint # Assuming DataPoint is available
from pydantic.fields import FieldInfo # Import FieldInfo for patching

# --- Entity Definitions ---

# --- Add text_content to base DataPoint if missing ---
# This is a workaround. Ideally, the base DataPoint should define common fields.
if not hasattr(DataPoint, 'text_content'):
    print("Patching DataPoint to add text_content field", file=sys.stderr)
    DataPoint.model_fields['text_content'] = FieldInfo(annotation=Optional[str], default=None)

# Helper to create metadata dict, ensuring required fields exist
def _create_metadata(entity_specific_type: str, index_fields: List[str] = [], **kwargs) -> Dict[str, Any]:
    """Creates the metadata dict, ensuring required fields and removing None values."""
    metadata = {
        "type": entity_specific_type, # Specific type for metadata context
        "index_fields": index_fields,
        **{k: v for k, v in kwargs.items() if v is not None} # Add other fields if not None
    }
    return metadata

class Repository(DataPoint):
    """Represents the root repository."""
    # --- Remove defined fields ---
    # path: str
    path: str # Define field for direct access

    def __init__(self, repo_path: str):
        abs_path = os.path.abspath(repo_path)
        repo_id = str(uuid5(NAMESPACE_OID, abs_path))
        # Payload for super().__init__ should only contain base fields + metadata
        payload_for_super = dict(
            id=repo_id,
            type="Repository", # Top-level type for DataPoint system
            # Required metadata
            metadata=_create_metadata(
                # Keep path info in metadata as well for consistency/querying
                entity_specific_type="Repository",
                # No specific fields to index for Repository itself
                index_fields=[],
                path=abs_path, # Store path in metadata
            ),
        )
        super().__init__(**payload_for_super)
        # Set subclass-specific fields *after* super().__init__
        object.__setattr__(self, 'path', abs_path) # Use object.__setattr__ to bypass validation if needed

class SourceFile(DataPoint):
    # --- Remove defined fields ---
    """Represents a discovered source file."""
    # --- Define fields ---
    name: str # Basename
    file_path: str # Full original path
    relative_path: str
    file_type: str
    part_of_repository: str # Expecting string ID

    def __init__(self, file_path: str, relative_path: str, repo_id: str, file_type: str):
        abs_path = os.path.abspath(file_path)
        file_name = os.path.basename(file_path)
        file_id = str(uuid5(NAMESPACE_OID, abs_path))
        payload_for_super: Dict[str, Any] = dict(
            id=file_id,
            type="SourceFile",
            # Required metadata
            metadata=_create_metadata(
                entity_specific_type="SourceFile",
                # Index name and path? Or leave empty?
                index_fields=["name", "relative_path"], # Index metadata fields
                # Keep fields in metadata too
                name=file_name,
                file_path=file_path,
                relative_path=relative_path,
                file_type=file_type,
                part_of_repository=str(repo_id), # Ensure string ID here
            ),
        )
        super().__init__(**payload_for_super)
        object.__setattr__(self, 'name', file_name)
        object.__setattr__(self, 'file_path', file_path)
        object.__setattr__(self, 'relative_path', relative_path)
        object.__setattr__(self, 'file_type', file_type)
        object.__setattr__(self, 'part_of_repository', str(repo_id))

class CodeEntity(DataPoint):
    # --- Remove defined fields ---
    """Represents a code entity like a function, class, or method."""
    name: str # Name of the function, class, etc.
    defined_in_file: str # String ID of the source file
    start_line: int
    end_line: int # Use Optional[int] if sometimes unavailable?
    text_content: Optional[str] # Make snippet optional? Or ensure base defines it.
    # entity_type: str # Store the specific type if needed beyond metadata

    def __init__(self, entity_id_str: str, entity_type: str, name: str, source_file_id: str, source_code: str, start_line: int, end_line: int):
          entity_id = str(uuid5(NAMESPACE_OID, str(entity_id_str))) # Ensure base str is string
          payload_for_super = dict(
              id=entity_id,
              type=entity_type, # Use specific type like FunctionDefinition for the base type
              text_content=source_code,
              # Required metadata
              metadata=_create_metadata(
                  entity_specific_type=entity_type,
                  # Include fields in metadata
                  name=name,
                  defined_in_file=str(source_file_id), # Ensure string ID
                  start_line=start_line,
                  end_line=end_line,
                  index_fields=["text_content", "name"], # Index text and name from metadata
                  source_code_snippet_field="text_content", # Keep track of where snippet is
              ),
          )
          super().__init__(**payload_for_super)
          object.__setattr__(self, 'name', name)
          object.__setattr__(self, 'defined_in_file', str(source_file_id))
          object.__setattr__(self, 'start_line', start_line)
          object.__setattr__(self, 'end_line', end_line)
          object.__setattr__(self, 'text_content', source_code) # Set explicitly if not on base

class Dependency(DataPoint):
    # --- Remove defined fields ---
    """Represents an import or include statement."""
    target_module: str
    used_in_file: str
    start_line: int
    end_line: Optional[int] = None # Make end_line optional?
    text_content: Optional[str] = None

    def __init__(self, dep_id_str: str, source_file_id: str, target: str, source_code_snippet: str, start_line: int, end_line: int):
        dep_id = str(uuid5(NAMESPACE_OID, str(dep_id_str))) # Ensure base str is string
        payload_for_super: Dict[str, Any] = dict(
            id=dep_id,
            type="Dependency",
            text_content=source_code_snippet,
            # Required metadata
            metadata=_create_metadata(
                entity_specific_type="Dependency",
                index_fields=["text_content", "target_module"], # Index snippet and target
                target_module=target,
                used_in_file=str(source_file_id), # Ensure string ID
                start_line=start_line,
                end_line=end_line,
            ),
        )
        super().__init__(**payload_for_super)
        object.__setattr__(self, 'target_module', target)
        object.__setattr__(self, 'used_in_file', str(source_file_id))
        object.__setattr__(self, 'start_line', start_line)
        object.__setattr__(self, 'end_line', end_line)
        object.__setattr__(self, 'text_content', source_code_snippet)

class TextChunk(DataPoint):
    """Represents a segment of text."""
    # --- Define fields ---
    # Note: text_content is likely defined in base DataPoint, but listed for clarity
    text_content: Optional[str] = None # Make optional or ensure base has it
    chunk_of: str # String ID of the parent (e.g., SourceFile ID)
    chunk_index: int
    start_line: Optional[int] = None # Keep optional
    end_line: Optional[int] = None # Keep optional

    def __init__(self, chunk_id_str: str, parent_id: str, text: str, chunk_index: int, start_line: Optional[int] = None, end_line: Optional[int] = None):
        chunk_id = str(uuid5(NAMESPACE_OID, str(chunk_id_str)))
        payload_for_super: Dict[str, Any] = dict(
            id=chunk_id,
            type="TextChunk",
            text_content=text, # Pass text_content to base
            metadata=_create_metadata(
                entity_specific_type="TextChunk",
                index_fields=["text_content"],
                # Keep chunk_of, index, lines also in metadata
                chunk_of=str(parent_id), # Ensure string ID
                chunk_index=chunk_index,
                start_line=start_line,
                end_line=end_line,
            ),
        )
        super().__init__(**payload_for_super)
        # Set subclass-specific fields *after* super().__init__
        object.__setattr__(self, 'chunk_of', str(parent_id))
        object.__setattr__(self, 'chunk_index', chunk_index)
        object.__setattr__(self, 'start_line', start_line)
        object.__setattr__(self, 'end_line', end_line)
        object.__setattr__(self, 'text_content', text) # Set explicitly if not on base

# Optional: Rebuild models (keep as is)
if hasattr(DataPoint, 'model_rebuild'):
    Repository.model_rebuild()
    SourceFile.model_rebuild()
    CodeEntity.model_rebuild()
    Dependency.model_rebuild()
    TextChunk.model_rebuild()
