from typing import List, Optional, Any
from uuid import UUID, uuid4

try:
    from cognee.infrastructure.engine.models.DataPoint import DataPoint
except ImportError as e:
    print(f"CRITICAL ERROR: Could not import Cognee's DataPoint model: {e}. "
          "Using a placeholder DataPoint. This will not work for actual Cognee ingestion.")
    from pydantic import BaseModel, Field as PydanticField
    class DataPoint(BaseModel):
        id: UUID = PydanticField(default_factory=uuid4)
        type: str

class AdaptedRepositoryDP(DataPoint): pass
class AdaptedSourceFileDP(DataPoint): pass
class AdaptedTextChunkDP(DataPoint): pass
class AdaptedCodeEntityDP(DataPoint): pass
class AdaptedFunctionEntityDP(DataPoint): pass
class AdaptedClassEntityDP(DataPoint): pass

class AdaptedRepositoryDP(DataPoint):
    path: str
    contains_files: List[AdaptedSourceFileDP] = []

    def __init__(self, **data: Any):
        data.setdefault('id', uuid4())
        data.setdefault('type', "AdaptedRepository")
        super().__init__(**data)

class AdaptedSourceFileDP(DataPoint):
    file_path: str
    relative_path: str
    language_key: str
    timestamp: float

    # Relationships
    part_of_repository: Optional[AdaptedRepositoryDP] = None
    contains_chunks: List[AdaptedTextChunkDP] = []
    defines_code_entities: List[AdaptedCodeEntityDP] = []

    imports_names: List[str] = []

    def __init__(self, **data: Any):
        data.setdefault('id', uuid4())
        data.setdefault('type', "AdaptedSourceFile")
        super().__init__(**data)

class AdaptedTextChunkDP(DataPoint):
    original_parser_source_file_id: str
    original_parser_chunk_id: str
    chunk_index: int
    start_line: int
    end_line: int
    chunk_content: str
    chunk_of_file: Optional[AdaptedSourceFileDP] = None
    defines_code_entities: List[AdaptedCodeEntityDP] = []

    def __init__(self, **data: Any):
        data.setdefault('id', uuid4())
        data.setdefault('type', "AdaptedTextChunk")
        super().__init__(**data)

class AdaptedCodeEntityDP(DataPoint):
    original_parser_code_entity_id: str
    original_parser_source_file_id: str
    original_parser_text_chunk_id: str

    entity_parser_type: str
    name: Optional[str] = None
    start_line: int
    end_line: int
    snippet_content: str
    language_key: str
    defined_in_chunk: Optional[AdaptedTextChunkDP] = None
    part_of_file: Optional[AdaptedSourceFileDP] = None

    def __init__(self, **data: Any):
        data.setdefault('id', uuid4())
        if 'type' not in data: data.setdefault('type', "AdaptedCodeEntity")
        super().__init__(**data)


class AdaptedFunctionEntityDP(AdaptedCodeEntityDP):
    calls: List[AdaptedCodeEntityDP] = []

    def __init__(self, **data: Any):
        data.setdefault('type', "AdaptedFunction")
        super().__init__(**data)


class AdaptedClassEntityDP(AdaptedCodeEntityDP):
    inherits_from: List[AdaptedClassEntityDP] = []
    defines_methods: List[AdaptedFunctionEntityDP] = []

    def __init__(self, **data: Any):
        data.setdefault('type', "AdaptedClass")
        super().__init__(**data)

AdaptedRepositoryDP.model_rebuild()
AdaptedSourceFileDP.model_rebuild()
AdaptedTextChunkDP.model_rebuild()
AdaptedCodeEntityDP.model_rebuild()
AdaptedFunctionEntityDP.model_rebuild()
AdaptedClassEntityDP.model_rebuild()
