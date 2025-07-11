from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timezone
from enum import Enum

class FileProcessingRequest(BaseModel):
    """
    The primary input model for the main entry point of the parser library.
    """
    absolute_path: str = Field(description="The full, absolute path to the file on disk.")
    repo_path: str = Field(description="The relative path to the repo.")
    repo_id: str = Field(description="The repository identifier (e.g., 'automalar/web').")
    branch: str = Field(description="The name of the branch being processed (e.g., 'main').")
    commit_index: int = Field(description="The current commit count of the branch as a zero-padded string (e.g., '234').")
    is_delete: bool = Field(description="DELETE removes all graph data for this file path on the specified branch or UPSERT, which parses and ingests the file's current state.")
    import_id: Optional[str] = Field(None, description="The canonical import name for this repository, if it's a library (e.g., 'pandas').")
    root_namespace: Optional[str] = Field(None, description="The root namespace for this project, for languages like Java (e.g., 'com.mycompany.project').")

class Repository(BaseModel):
    """Represents the root repository being processed."""
    id: str = Field(description="User or company/repository name@branch name (e.g., 'microsoft/graphrag@main').")
    type: str = Field("Repository", frozen=True, description="Type of node.")
    path: str = Field(description="Absolute path to the repository root folder (e.g., 'root/microsoft/graphrag').")
    repo_id: str = Field(description="User or company/repository name (e.g., 'microsoft/graphrag').")
    branch: str = Field(description="Branch name (e.g., 'main').")

class SourceFile(BaseModel):
    """Represents a file within the repository."""
    id: str = Field(description="Composite ID, Repository.id|Relative path to the file@Commit index - local version (e.g., 'microsoft/graphrag@main|src/main.py@234-432').")
    type: str = Field("SourceFile", frozen=True, description="Type of node.")
    relative_path: str = Field(description="Relative path to the file (e.g., 'src/main.py').")
    commit_index: int = Field(description="Commit index number, zero-padded integer, 5 decimal places (e.g., '234').")
    local_save: int = Field(description="Local file versioning (e.g., '432').")
    content_hash: Optional[str] = Field(None, description="SHA256 hash of the file content for idempotency.")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="File ingestion timestamp in ISO 8601 UTC format.")

class TextChunk(BaseModel):
    """Represents a segment of text from a file."""
    id: str = Field(description="Composite ID, Repository.id|SourceFile.id|index of the chunk@Start-End line (e.g., 'microsoft/graphrag@main|src/main.py@234-432|0@1-12').")
    type: str = Field("TextChunk", frozen=True, description="Type of node.")
    chunk_content: str = Field(description="Chunk text content.")
    start_line: int = Field(description="First line index number, point to the starting line number in the source file (e.g., 1).")
    end_line: int = Field(description="Last line index number, point to the ending line number of this chunk in the source file (e.g., 12).")
    chunk_content: str = Field(description="Last line index number, point to the ending line number of this chunk in the source file (e.g., 12).")

class CodeEntity(BaseModel):
    """Represents a code construct (function, class, interface, struct, enum, etc.)."""
    id: str = Field(description="Composite ID, Repository.id|SourceFile.id|TextChunk.id|FQN@Start line (e.g., 'microsoft/graphrag@main|src/main.py@234-432|0@1-12|FuncPtr(int)@9-11').")
    type: str = Field(description="Specific type such as 'FunctionDefinition', 'ClassDefinition', 'InterfaceDefinition'.")
    start_line: int = Field(description="First line index number, point to the starting line number of this code entity in the source file (e.g., 9).")
    end_line: int = Field(description="Last line index number, point to the endiing line number of this code entity in the source file (e.g., 11).")
    canonical_fqn: Optional[str] = Field(None, description="The parser's best-effort, language-specific canonical FQN for this entity.")
    snippet_content: str = Field(description="Code snippet text content.")
    metadata: Optional[Dict[str, Any]] = None

class Relationship(BaseModel):
    """Represents a directed edge/relationship between two nodes (entities or files)."""
    source_id: str = Field(description="ID of the source node.")
    target_id: str = Field(description="ID of the target node.")
    type: str = Field(description="Type of relationship (e.g., 'DEFINED_IN', 'IMPORTS', 'EXTENDS', 'IMPLEMENTS', 'PART_OF', 'CONTAINS', 'IMPLEMENTS_TRAIT', 'REFERENCES_SYMBOL').")
    properties: Optional[Dict[str, Any]] = None

AdaptableNode = Union[Repository, SourceFile, TextChunk, CodeEntity, PendingLink, ResolutionCache]

ParserOutput = Union[
    List[int],
    CodeEntity,
    RawSymbolReference
]

class ImportType(str, Enum):
    """
    Syntactic type of an import, as determined by the parser.
    """
    RELATIVE = "relative" # e.g., from . import utils, #include "utils.h"
    ABSOLUTE = "absolute" # e.g., import pandas, #include <vector>

class LinkStatus(str, Enum):
    """
    Lifecycle status of a PendingLink node.
    """
    PENDING_RESOLUTION = "pending_resolution"      # The initial state. Waiting for its dependencies or the heuristic resolver.
    READY_FOR_HEURISTICS = "ready_for_heuristics"  # Promoted by the Janitor, ready for heuristics.
    AWAITING_TARGET = "awaiting_target"            # For when an LLM provides a hint
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
    Standardized representation for a reference.
    """
    type: ImportType
    path_elements: List[str] = Field(description="Sequence of names in the import path (e.g., ['com', 'google', 'guava']).")
    alias: Optional[str] = Field(None, description="Alias given to the import, if any (e.g., 'pd' for 'pandas').")

class RawSymbolReference(BaseModel):
    """
    Standardized report of a referenced symbol.
    """
    source_entity_id: str = Field(description="Temporary ID (FQN@line) of the entity making the reference (e.g., 'MyNamespace::my_func@50').")
    target_expression: str = Field(description="Literal code used for the reference (e.g., 'pd.DataFrame', 'MyClass', 'utils.helper').")
    reference_type: str = Field(description="Semantic type of the reference (e.g., 'INHERITANCE', 'FUNCTION_CALL', 'IMPORT').")
    context: ReferenceContext
    metadata: Optional[Dict[str, Any]] = None

class PendingLink(BaseModel):
    """
    Temporary node of an unresolved link's state and its context. (e.g., from source file, target expression, and import context)
    """
    id: str = Field(description="A unique, deterministic UUID5 hash of the reference's context.")
    type: str = Field("PendingLink", frozen=True)
    status: LinkStatus = Field(default=LinkStatus.PENDING_RESOLUTION)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reference_data: RawSymbolReference
    awaits_fqn: Optional[str] = Field(None, description="The canonical FQN hint provided by the LLM stage.")

class ResolutionCache(BaseModel):
    """
    Resolved links node cache, store the results of LLM stage resolutions.
    """
    id: str = Field(description="A unique, deterministic UUID5 hash matching the ID of the PendingLink it resolves.")
    type: str = Field("ResolutionCache", frozen=True)
    resolved_target_id: str = Field(description="The final, version-aware ID of the CodeEntity the reference resolves to (e.g., '...|src/utils.py@00123-001|0@1-20|helper()@4').")
    method: ResolutionMethod = Field(description="The tier of the resolver that solved this link (e.g., 'direct_path', 'llm').")

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
