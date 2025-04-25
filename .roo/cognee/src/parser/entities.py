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
    """
    Represents the root of the scanned directory or repository.

    Inherits from DataPoint.

    Attributes:
        id (str): A unique identifier for the repository (UUID v5 based on absolute path).
        payload (dict): Dictionary containing repository details.
            - type (str): Always "Repository".
            - path (str): The absolute path to the repository root.
            - timestamp (float): Unix timestamp of when the entity was created.
    """
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
    """
    Represents any discovered source file (code, configuration, documentation, etc.).

    Inherits from DataPoint.

    Attributes:
        id (str): A unique identifier for the file (UUID v5 based on absolute path).
        payload (dict): Dictionary containing file details.
            - type (str): Always "SourceFile".
            - name (str): The base name of the file (e.g., "main.py").
            - file_path (str): The absolute path to the file.
            - relative_path (str): The path to the file relative to the repository root.
            - file_type (str): The detected type of the file (e.g., 'python', 'markdown').
            - part_of_repository (str): The ID of the parent Repository entity.
            - timestamp (float): Unix timestamp of when the entity was created.
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
        # Generate ID based on the absolute file path
        file_id = str(uuid5(NAMESPACE_OID, os.path.abspath(file_path)))
        super().__init__(id=file_id, **payload)

class CodeEntity(DataPoint):
    """
    Generic representation for code elements like functions, classes, structs, enums, etc.

    Inherits from DataPoint.

    Attributes:
        id (str): A unique identifier for the code entity (UUID v5 based on file ID, type, name, and start line).
        payload (dict): Dictionary containing code entity details.
            - type (str): The specific type of code entity (e.g., "FunctionDefinition", "ClassDefinition").
            - name (str): The name of the code entity.
            - defined_in_file (str): The ID of the parent SourceFile entity.
            - source_code_snippet (str): The exact source code lines defining this entity.
            - start_line (int): The 1-based starting line number of the entity in the file.
            - end_line (int): The 1-based ending line number of the entity in the file.
            - timestamp (float): Unix timestamp of when the entity was created.
    """
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
    """
    Represents imports, includes, use statements, or other forms of code dependencies.

    Inherits from DataPoint.

    Attributes:
        id (str): A unique identifier for the dependency (UUID v5 based on file ID, target, and start line).
        payload (dict): Dictionary containing dependency details.
            - type (str): Always "Dependency".
            - target_module (str): The name or path of the module, file, or library being depended upon.
            - used_in_file (str): The ID of the SourceFile entity where the dependency is declared.
            - source_code_snippet (str): The exact source code lines declaring the dependency (e.g., 'import os').
            - start_line (int): The 1-based starting line number of the dependency declaration.
            - end_line (int): The 1-based ending line number of the dependency declaration.
            - timestamp (float): Unix timestamp of when the entity was created.
    """
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
    """
    Represents a segment of text derived from a file or a specific code entity.

    Inherits from DataPoint.

    Attributes:
        id (str): A unique identifier for the text chunk (UUID v5 based on parent ID and chunk index).
        payload (dict): Dictionary containing text chunk details.
            - type (str): Always "TextChunk".
            - chunk_of (str): The ID of the parent entity (SourceFile or CodeEntity) this chunk belongs to.
            - text (str): The actual text content of the chunk.
            - chunk_index (int): The sequential index of this chunk within its parent.
            - start_line (Optional[int]): The 1-based starting line number of the chunk within the parent's source code (if applicable).
            - end_line (Optional[int]): The 1-based ending line number of the chunk within the parent's source code (if applicable).
            - timestamp (float): Unix timestamp of when the entity was created.
            - metadata (dict): Additional metadata, including hints for indexing.
    """
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
