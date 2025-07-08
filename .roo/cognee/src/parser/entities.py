from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timezone
from enum import Enum

class ImportType(str, Enum):
    """
    Syntactic type of an import.
    """
    RELATIVE = "relative" # e.g., from . import utils, #include "utils.h"
    ABSOLUTE = "absolute" # e.g., import pandas, #include <vector>

class LinkStatus(str, Enum):
    """
    Lifecycle status of a PendingLink node.
    """
    PENDING_RESOLUTION = "pending_resolution"      # The initial state. Waiting for its dependencies or the heuristic resolver.
    READY_FOR_HEURISTICS = "ready_for_heuristics"  # Promoted by the Janitor, ready for heuristics.
    READY_FOR_LLM = "ready_for_llm"                # Heuristics phase failed or found ambiguity. Ready for LLM review.
    UNRESOLVABLE = "unresolvable"                  # Deemed unresolvable by the system.
    RESOLVED = "resolved"                          # Kept for auditing/caching purposes.

class ResolutionMethod(str, Enum):
    """Which phase solved the link."""
    DIRECT_PATH = "direct_path"
    HEURISTIC_MATCH = "heuristic_match"
    LLM = "llm"

class ReferenceContext(BaseModel):
    """
    Universal representation of an import's context.
    """
    type: ImportType
    path_elements: List[str] = Field(description="Sequence of names in the import path (e.g., ['com', 'google', 'guava']).")
    alias: Optional[str] = Field(None, description="Local alias given to the import, if any (e.g., 'pd' for 'pandas').")

class RawSymbolReference(BaseModel):
    """
    Context of referenced symbol.
    """
    source_entity_id: str = Field(description="Temporary ID (FQN@line) of the entity making the reference (e.g., 'MyNamespace::my_func@50').")
    target_expression: str = Field(description="Literal code used for the reference (e.g., 'pd.DataFrame', 'MyClass', 'utils.helper').")
    reference_type: str = Field(description="Semantic type of the reference (e.g., 'INHERITANCE', 'FUNCTION_CALL', 'IMPORT').")
    context: ReferenceContext

class PendingLink(BaseModel):
    """
    Temporary node of an unresolved link's state and context.
    """
    id: str = Field(description="A unique, deterministic UUID5 hash of the reference's context (e.g., from source file, target expression, and import context).")
    type: str = Field("PendingLink", frozen=True)
    status: LinkStatus = Field(default=LinkStatus.PENDING_RESOLUTION)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reference_data: RawSymbolReference

class ResolutionCache(BaseModel):
    """
    Resolved links node cache.
    """
    id: str = Field(description="A unique, deterministic UUID5 hash matching the ID of the PendingLink it resolves.")
    type: str = Field("ResolutionCache", frozen=True)
    resolved_target_id: str = Field(description="The final, version-aware ID of the CodeEntity the reference resolves to (e.g., '...|src/utils.py|00123-001|0@1-20|helper()').")
    method: ResolutionMethod = Field(description="The tier of the resolver that solved this link (e.g., 'direct_path', 'llm').")

class FileProcessingRequest(BaseModel):
    """
    The primary input model for the main entry point of the parser library.
    """
    absolute_path: str = Field(description="The full, absolute path to the file on disk.")
    repo_path: str = Field(description="The relative path to the repo.")
    repo_id: str = Field(description="The repository identifier (e.g., 'automalar/web').")
    branch: str = Field(description="The name of the branch being processed (e.g., 'main').")
    commit_index: str = Field(description="The current commit count of the branch as a zero-padded string (e.g., '00765').")
    is_delete: bool = Field(description="DELETE removes all graph data for this file path on the specified branch or UPSERT, which parses and ingests the file's current state.")
    import_id: Optional[str] = Field(None, description="The canonical import name for this repository, if it's a library (e.g., 'pandas').")
    root_namespace: Optional[str] = Field(None, description="The root namespace for this project, for languages like Java (e.g., 'com.mycompany.project').")

class Repository(BaseModel):
    """Represents the root repository being processed."""
    id: str = Field(description="Unique ID, GitHub user or company/repository name@branch name (e.g., 'microsoft/graphrag@main').")
    type: str = Field("Repository", frozen=True, description="Type of node.")
    path: str = Field(description="Absolute path to the repository root folder (e.g., 'root/microsoft/graphrag').")
    import_id: Optional[str] = Field(None)

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
    type: str = Field(description="Type of relationship (e.g., 'DEFINED_IN', 'IMPORTS', 'EXTENDS', 'IMPLEMENTS', 'PART_OF', 'CONTAINS', 'IMPLEMENTS_TRAIT', 'REFERENCES_SYMBOL').")

AdaptableNode = Union[Repository, SourceFile, TextChunk, CodeEntity, PendingLink, ResolutionCache]

ParserOutput = Union[
    List[int],
    CodeEntity,
    RawSymbolReference
]

OrchestratorOutput = Union[
    AdaptableNode,
    Relationship,
]
