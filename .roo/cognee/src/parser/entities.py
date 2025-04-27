# FILE: src/parser/entities.py

# --- Imports ---
import os
import time
from typing import List, Optional, Dict, Any
from uuid import NAMESPACE_OID, uuid5, UUID # Import UUID
from pydantic import BaseModel, Field # Use Pydantic BaseModel directly

# --- Entity Definitions (Standalone Pydantic Models) ---

# Helper to create metadata dict, ensuring required fields exist
# NOTE: This helper is no longer used by the standalone models below,
# but kept in case it's used elsewhere or for future reference.
def _create_metadata(entity_specific_type: str, index_fields: List[str] = [], **kwargs) -> Dict[str, Any]:
    """Creates the metadata dict, ensuring required fields and removing None values."""
    metadata = {
        "type": entity_specific_type, # Specific type for metadata context
        "index_fields": index_fields,
        **{k: v for k, v in kwargs.items() if v is not None} # Add other fields if not None
    }
    return metadata

class Repository(BaseModel):
    """Represents the root repository."""
    id: str
    type: str = "Repository"
    path: str
    # Add timestamp if needed
    timestamp: float = Field(default_factory=time.time)

    def __init__(self, repo_path: str):
        abs_path = os.path.abspath(repo_path)
        repo_id = str(uuid5(NAMESPACE_OID, abs_path))
        payload = dict(
            id=repo_id,
            path=abs_path,
        )
        super().__init__(**payload)

class SourceFile(BaseModel):
    """Represents a discovered source file."""
    # --- Define fields ---
    id: str
    type: str = "SourceFile"
    name: str # Basename
    file_path: str # Full original path
    relative_path: str
    file_type: str
    part_of_repository: str # Expecting string ID
    timestamp: float = Field(default_factory=time.time)

    def __init__(self, file_path: str, relative_path: str, repo_id: str, file_type: str):
        abs_path = os.path.abspath(file_path)
        file_name = os.path.basename(file_path)
        file_id = str(uuid5(NAMESPACE_OID, abs_path))
        payload: Dict[str, Any] = dict(
            id=file_id,
            name=file_name,
            file_path=file_path,
            relative_path=relative_path,
            file_type=file_type,
            part_of_repository=str(repo_id), # Ensure string ID
        )
        super().__init__(**payload)

class CodeEntity(BaseModel):
    """Represents a code entity like a function, class, or method."""
    id: str
    type: str # This will hold FunctionDefinition, ClassDefinition etc.
    name: str # Name of the function, class, etc.
    defined_in_file: str # String ID of the source file
    start_line: int
    end_line: int # Use Optional[int] if sometimes unavailable?
    text_content: Optional[str] # Make snippet optional? Or ensure base defines it.
    timestamp: float = Field(default_factory=time.time)

    def __init__(self, entity_id_str: str, entity_type: str, name: str, source_file_id: str, source_code: str, start_line: int, end_line: int):
          entity_id = str(uuid5(NAMESPACE_OID, str(entity_id_str))) # Ensure base str is string
          payload = dict(
              id=entity_id,
              type=entity_type, # Use specific type like FunctionDefinition for the base type
              name=name,
              defined_in_file=str(source_file_id), # Ensure string ID
              text_content=source_code,
              start_line=start_line,
              end_line=end_line,
          )
          super().__init__(**payload)

class Dependency(BaseModel):
    """Represents an import or include statement."""
    id: str
    type: str = "Dependency"
    target_module: str
    used_in_file: str
    start_line: int
    end_line: Optional[int] = None # Make end_line optional?
    text_content: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)

    def __init__(self, dep_id_str: str, source_file_id: str, target: str, source_code_snippet: str, start_line: int, end_line: int):
        dep_id = str(uuid5(NAMESPACE_OID, str(dep_id_str))) # Ensure base str is string
        payload: Dict[str, Any] = dict(
            id=dep_id,
            target_module=target,
            used_in_file=str(source_file_id), # Ensure string ID
            text_content=source_code_snippet,
            start_line=start_line,
            end_line=end_line,
        )
        super().__init__(**payload)

class TextChunk(BaseModel):
    """Represents a segment of text."""
    # --- Define fields ---
    id: str
    type: str = "TextChunk"
    text_content: Optional[str] = None # Make optional or ensure base has it
    chunk_of: str # String ID of the parent (e.g., SourceFile ID)
    chunk_index: int
    start_line: Optional[int] = None # Keep optional
    end_line: Optional[int] = None # Keep optional
    timestamp: float = Field(default_factory=time.time)

    def __init__(self, chunk_id_str: str, parent_id: str, text: str, chunk_index: int, start_line: Optional[int] = None, end_line: Optional[int] = None):
        chunk_id = str(uuid5(NAMESPACE_OID, str(chunk_id_str)))
        payload: Dict[str, Any] = dict(
            id=chunk_id,
            text_content=text,
            chunk_of=str(parent_id), # Ensure string ID
            chunk_index=chunk_index,
            start_line=start_line,
            end_line=end_line,
        )
        # Filter out None values for optional fields before passing to Pydantic
        payload = {k: v for k, v in payload.items() if v is not None}
        super().__init__(**payload)
