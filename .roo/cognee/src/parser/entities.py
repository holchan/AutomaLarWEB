from pydantic import BaseModel, Field
import time
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timezone

class Repository(BaseModel):
    """Represents the root repository being processed."""
    id: str # Unique string identifier, github user or company/repository name or if local project name (e.g., "microsoft/graphrag" or for local "AutomaLarWEB")
    path: str # Absolute path to the repository (local or remote[github link])
    type: str = Field("Repository", frozen=True)

class SourceFile(BaseModel):
    """Represents a discovered source file within the repository."""
    id: str # Composite ID string (e.g., "microsoft/graphrag:src/main.py" or "AutomaLarWEB:src/main.py")
    type: str = Field("SourceFile", frozen=True)
    file_path: str # Full original absolute path to the file, if remote the link
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class TextChunk(BaseModel):
    """Represents a segment of text, typically from a file."""
    id: str # Composite ID string (e.g., "microsoft/graphrag:src/main.py:index", "AutomaLarWEB:src/main.py:index")
    type: str = Field("TextChunk", frozen=True)
    start_line: int # Starting line where it was derived from the source file
    end_line: int  # Ending line where it was derived from the source file
    chunk_content: str # Chunk text content

class CodeEntity(BaseModel):
    """
    Represents a significant code construct (function, class, interface, struct, enum, etc.).
    Detailed, language-specific information is stored in the `metadata` dictionary.
    """
    id: str     # Composite ID string (e.g., "microsoft/graphrag:src/main.py:index:foo", "AutomaLarWEB:src/main.py:index:foo")
    type: str   # Specific type like "FunctionDefinition", "ClassDefinition", "InterfaceDefinition"
    snippet_content: str # Code snippet text content

class Relationship(BaseModel):
    """
    Represents a directed edge/relationship between two nodes (entities or files).
    """
    source_id: str # String ID of the source node
    target_id: str # String ID of the target node
    type: str      # Type of relationship (e.g., "DEFINED_IN", "IMPORTS", "EXTENDS", "IMPLEMENTS", "PART_OF", "CONTAINS", "IMPLEMENTS_TRAIT")
    properties: Optional[Dict[str, Any]] = None

class CallSiteReference(BaseModel):
    """
    Represents a detected call site within the code before full resolution.
    """
    calling_entity_temp_id: str
    called_name_expr: str
    line_of_call_0_indexed: int
    source_file_id_of_call_site: str
    raw_arg_text: Optional[str] = None
    argument_count: int

ParserOutput = Union[
    List[int],
    CodeEntity,   
    Relationship,
    CallSiteReference
]

OrchestratorPhaseAOutputUnion = Union[
    Repository,
    SourceFile,
    TextChunk,
    CodeEntity,
    Relationship
]

