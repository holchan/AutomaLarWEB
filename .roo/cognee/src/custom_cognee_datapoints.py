from typing import List, Optional, Any, Dict
from uuid import UUID, uuid4
from pydantic import Field as PydanticField
from datetime import datetime, timezone

try:
    from cognee.infrastructure.engine.models.DataPoint import DataPoint, MetaData
except ImportError:
    from pydantic import BaseModel
    class MetaData(Dict[str, Any]): pass
    class DataPoint(BaseModel):
        id: UUID = PydanticField(default_factory=uuid4)
        type: str
        metadata: Optional[MetaData] = PydanticField(default_factory=lambda: MetaData(index_fields=[]))
        created_at: int = PydanticField(default_factory=lambda: int(datetime.now(timezone.utc).timestamp() * 1000))
        updated_at: int = PydanticField(default_factory=lambda: int(datetime.now(timezone.utc).timestamp() * 1000))
        version: int = 1
        ontology_valid: bool = False
        topological_rank: Optional[int] = 0
        belongs_to_set: Optional[List["DataPoint"]] = None

class RepositoryNode(DataPoint):
    slug_id: str
    path: str
    metadata: Optional[MetaData] = PydanticField(default_factory=lambda: MetaData(index_fields=["slug_id", "path", "type"]))

class SourceFileNode(DataPoint):
    slug_id: str
    file_path: str
    timestamp: str
    metadata: Optional[MetaData] = PydanticField(default_factory=lambda: MetaData(index_fields=["slug_id", "file_path", "timestamp", "type"])) # timestamp ADDED

class TextChunkNode(DataPoint):
    slug_id: str
    start_line: int
    end_line: int
    chunk_content: str
    metadata: Optional[MetaData] = PydanticField(default_factory=lambda: MetaData(index_fields=["slug_id", "start_line", "end_line", "chunk_content", "type"])) # start_line, end_line ADDED

class CodeEntityNode(DataPoint):
    slug_id: str
    snippet_content: str
    metadata: Optional[MetaData] = PydanticField(default_factory=lambda: MetaData(index_fields=["slug_id", "snippet_content", "type"]))
