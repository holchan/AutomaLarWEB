# src/parser/entities.py
import os
from typing import List, Optional, Dict, Any
from uuid import NAMESPACE_OID, uuid5
import time

# --- Cognee Imports ---
# Attempt to import the real DataPoint, provide a fallback if unavailable
try:
    from cognee.low_level import DataPoint
    COGNEE_AVAILABLE = True
except ImportError:
    COGNEE_AVAILABLE = False
    # Define a fallback DataPoint if Cognee is not installed where this runs
    # This allows the parser module to potentially run standalone for testing
    class DataPoint:
        def __init__(self, **kwargs):
            # Ensure essential keys are present for downstream use
            self.id = kwargs.get("id", str(uuid5(NAMESPACE_OID, str(kwargs))))
            self.payload = kwargs
            self.payload.setdefault("id", self.id)
            self.payload.setdefault("type", "Unknown")
            self.payload.setdefault("timestamp", time.time())

        def model_dump(self) -> Dict[str, Any]:
            """Mimic pydantic method if needed downstream."""
            return self.payload

        def __repr__(self) -> str:
            return f"DataPoint(id={self.id}, type={self.payload.get('type')})"

# --- Entity Definitions ---

class Repository(DataPoint):
    """Represents the root of the scanned directory."""
    def __init__(self, repo_path: str):
        payload = dict(
            type = "Repository",
            path = repo_path,
            timestamp = time.time(),
        )
        # Generate ID based on the absolute path for consistency
        repo_id = str(uuid5(NAMESPACE_OID, os.path.abspath(repo_path)))
        super().__init__(id=repo_id, **payload)

class SourceFile(DataPoint):
    """Represents any discovered source file (code, config, doc)."""
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
        # Generate ID based on the absolute file path
        file_id = str(uuid5(NAMESPACE_OID, os.path.abspath(file_path)))
        super().__init__(id=file_id, **payload)

class CodeEntity(DataPoint):
    """Generic representation for code elements like functions, classes, structs."""
    def __init__(self, entity_id_str: str, entity_type: str, name: str, source_file_id: str, source_code: str, start_line: int, end_line: int):
        payload = dict(
            type = entity_type, # e.g., "FunctionDefinition", "ClassDefinition", "StructDefinition"
            name = name,
            defined_in_file = source_file_id, # Link to parent SourceFile ID
            source_code_snippet = source_code, # Store the specific entity's code
            start_line = start_line, # 1-based line number
            end_line = end_line, # 1-based line number
            timestamp = time.time(),
            # Optional: Add language if needed downstream
            # language = language_from_file_type(file_type)
        )
        # Generate ID based on a combination of file, type, name, and location
        entity_id = str(uuid5(NAMESPACE_OID, f"{source_file_id}:{entity_type}:{name}:{start_line}"))
        super().__init__(id=entity_id, **payload)

class Dependency(DataPoint):
    """Generic representation for imports, includes, use statements."""
    def __init__(self, dep_id_str: str, source_file_id: str, target: str, source_code_snippet: str, start_line: int, end_line: int):
        payload = dict(
            type = "Dependency",
            target_module = target, # The module/file/library being imported/included
            used_in_file = source_file_id, # Link to SourceFile ID where import happens
            source_code_snippet = source_code_snippet, # The line(s) of code for the import
            start_line = start_line, # 1-based line number
            end_line = end_line, # 1-based line number
            timestamp = time.time(),
        )
        # Generate ID based on file, target, and location
        dep_id = str(uuid5(NAMESPACE_OID, f"{source_file_id}:dep:{target}:{start_line}"))
        super().__init__(id=dep_id, **payload)

class TextChunk(DataPoint):
    """Represents a text chunk derived from a file or code entity."""
    def __init__(self, chunk_id_str: str, parent_id: str, text: str, chunk_index: int, start_line: Optional[int] = None, end_line: Optional[int] = None):
        payload = dict(
            type = "TextChunk",
            chunk_of = parent_id, # Link to SourceFile or CodeEntity ID
            text = text,
            chunk_index = chunk_index, # Order of the chunk within its parent
            start_line = start_line, # Optional: 1-based start line within parent
            end_line = end_line, # Optional: 1-based end line within parent
            timestamp = time.time(),
            metadata = {"index_fields": ["text"]}, # Hint for Cognee indexing
        )
        # Generate ID based on parent and index
        chunk_id = str(uuid5(NAMESPACE_OID, f"{parent_id}:chunk:{chunk_index}"))
        super().__init__(id=chunk_id, **payload)

# Optional: Rebuild models if using Pydantic features within Cognee's DataPoint
# if COGNEE_AVAILABLE and hasattr(DataPoint, 'model_rebuild'):
#     Repository.model_rebuild()
#     SourceFile.model_rebuild()
#     CodeEntity.model_rebuild()
#     Dependency.model_rebuild()
#     TextChunk.model_rebuild()
