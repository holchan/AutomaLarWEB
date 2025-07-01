from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timezone

class FileProcessingRequest(BaseModel):
    """
    This is the primary input model for the main entry point of the parser library.
    """
    absolute_path: str = Field(description="The full, absolute path to the file on disk.")
    repo_path: str = Field(description="The relative path to the repo.")
    repo_id: str = Field(description="The repository identifier (e.g., 'automalar/web').")
    branch: str = Field(description="The name of the branch being processed (e.g., 'main').")
    commit_index: str = Field(description="The current commit count of the branch as a zero-padded string (e.g., '00765').")
    is_delete: bool = Field(description="DELETE removes all graph data for this file path on the specified branch or UPSERT, which parses and ingests the file's current state.")

class Repository(BaseModel):
    """Represents the root repository being processed."""
    id: str = Field(description="Unique ID, GitHub user or company/repository name@branch name (e.g., 'microsoft/graphrag@main').")
    type: str = Field("Repository", frozen=True, description="Type of node.")
    path: str = Field(description="Absolute path to the repository root folder (e.g., 'root/microsoft/graphrag').")

class SourceFile(BaseModel):
    """Represents a file within the repository."""
    id: str = Field(description="Composite ID, Repository.id|Relative path to the file (e.g., 'microsoft/graphrag@main|src/main.py').")
    type: str = Field("SourceFile", frozen=True, description="Type of node.")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="File ingestion timestamp in ISO 8601 UTC format.")

class TextChunk(BaseModel):
    """Represents a segment of text from a file."""
    id: str = Field(description="Composite ID, Repository.id|SourceFile.id|index of the chunk@Start-End line (e.g., 'microsoft/graphrag@main|src/main.py|0@1-12').")
    type: str = Field("TextChunk", frozen=True, description="Type of node.")
    chunk_content: str = Field(description="Chunk text content.")

class CodeEntity(BaseModel):
    """Represents a code construct (function, class, interface, struct, enum, etc.)."""
    id: str = Field(description="Composite ID, Repository.id|SourceFile.id|TextChunk.id|FQN@Start line (e.g., 'microsoft/graphrag@main|src/main.py|0@1-12|FuncPtr(int)@9').")
    type: str = Field(description="Specific type such as 'FunctionDefinition', 'ClassDefinition', 'InterfaceDefinition'.")
    snippet_content: str = Field(description="Code snippet text content.")

class Relationship(BaseModel):
    """Represents a directed edge/relationship between two nodes (entities or files)."""
    source_id: str = Field(description="ID of the source node.")
    target_id: str = Field(description="ID of the target node.")
    type: str = Field(description="Type of relationship (e.g., 'DEFINED_IN', 'IMPORTS', 'EXTENDS', 'IMPLEMENTS', 'PART_OF', 'CONTAINS', 'IMPLEMENTS_TRAIT').")

class CallSiteReference(BaseModel):
    """
    Intermediate data representing a detected call site, before resolution into a CALLS relationship.
    """
    calling_entity_temp_id: str = Field(description="Temporary ID (FQN@line) of the function or method making the call.")
    called_name_expr: str = Field(description="Syntactic name/expression being called (e.g., 'foo', 'obj.bar', 'Ns::func').")
    line_of_call_0_indexed: int = Field(description="Zero-indexed line number in the source file where the call occurs.")
    source_file_id_of_call_site: str = Field(description="Slug ID of the SourceFile (e.g., 'repo_id|relative_path') containing the call site.")
    raw_arg_text: Optional[str] = Field(default=None, description="Raw text of the arguments (e.g., 'arg1, (a+b)').")
    argument_count: int = Field(description="Number of top-level arguments passed in the call.")

ParserOutput = Union[
    List[int], # For slice_lines.
    CodeEntity, # Temp. CodeEntities from parser.
    Relationship, # Temp. Relationships from parser.
    CallSiteReference # Call sites from parser.
]

OrchestratorPhaseAOutputUnion = Union[
    Repository,
    SourceFile,
    TextChunk,
    CodeEntity,
    Relationship
]

OrchestratorPhaseBOutput = Union[
    Relationship,
]

