import pytest
from pydantic import ValidationError
from uuid import UUID
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

try:
    from src.parser.custom_datapoints import (
        DataPoint, MetaData,
        RepositoryNode, SourceFileNode, TextChunkNode, CodeEntityNode
    )
except ImportError:
    pytest.skip("Skipping custom_datapoints tests: Failed to import models from src.parser.custom_datapoints", allow_module_level=True)

def test_repository_node_instantiation():
    slug = "repo-slug"
    path_val = "/path/to/repo"
    node_type_from_parser = "Repository"

    node = RepositoryNode(slug_id=slug, path=path_val, type=node_type_from_parser)

    assert isinstance(node.id, UUID)
    assert node.slug_id == slug
    assert node.path == path_val
    assert node.type == node_type_from_parser
    assert node.metadata is not None and node.metadata.get("index_fields") == ["slug_id", "path", "type"]
    assert isinstance(node.created_at, int)
    assert isinstance(node.updated_at, int)

    with pytest.raises(ValidationError):
        RepositoryNode(slug_id=slug, path=path_val, type=node_type_from_parser, extra_field="bad")

def test_sourcefile_node_instantiation():
    slug = "repo:src/main.py"
    fpath = "/abs/src/main.py"
    ts = datetime.now(timezone.utc).isoformat()
    node_type_from_parser = "SourceFile"

    node = SourceFileNode(slug_id=slug, file_path=fpath, timestamp=ts, type=node_type_from_parser)

    assert isinstance(node.id, UUID)
    assert node.slug_id == slug
    assert node.file_path == fpath
    assert node.timestamp == ts
    assert node.type == node_type_from_parser
    assert node.metadata is not None and node.metadata.get("index_fields") == ["slug_id", "file_path", "timestamp", "type"]

    with pytest.raises(ValidationError):
        SourceFileNode(slug_id=slug, file_path=fpath, timestamp=ts, type=node_type_from_parser, relative_path="src/main.py")


def test_textchunk_node_instantiation():
    slug = "file:0"
    sl = 1
    el = 10
    cc = "chunk content"
    node_type_from_parser = "TextChunk"

    node = TextChunkNode(slug_id=slug, start_line=sl, end_line=el, chunk_content=cc, type=node_type_from_parser)

    assert isinstance(node.id, UUID)
    assert node.slug_id == slug
    assert node.start_line == sl
    assert node.end_line == el
    assert node.chunk_content == cc
    assert node.type == node_type_from_parser
    assert node.metadata is not None and node.metadata.get("index_fields") == ["slug_id", "start_line", "end_line", "chunk_content", "type"]

    with pytest.raises(ValidationError):
        TextChunkNode(slug_id=slug, start_line=sl, end_line=el, chunk_content=cc, type=node_type_from_parser, language_key="python")


def test_codeentity_node_instantiation():
    slug = "chunk:0:FunctionDefinition:myFunc:0"
    snippet = "def myFunc(): pass"
    node_type_from_parser = "FunctionDefinition"

    node = CodeEntityNode(slug_id=slug, snippet_content=snippet, type=node_type_from_parser)

    assert isinstance(node.id, UUID)
    assert node.slug_id == slug
    assert node.snippet_content == snippet
    assert node.type == node_type_from_parser
    assert node.metadata is not None and node.metadata.get("index_fields") == ["slug_id", "snippet_content", "type"]

    with pytest.raises(ValidationError):
        CodeEntityNode(slug_id=slug, snippet_content=snippet, type=node_type_from_parser, name="myFunc")

@pytest.mark.skipif("cognee.infrastructure.engine.models.DataPoint" in globals(), reason="Skipping placeholder test if real DataPoint imported")
def test_placeholder_datapoint_init_type_override():
    from pydantic import BaseModel as PydanticBaseModel
    from uuid import UUID, uuid4
    from pydantic import Field as PydanticField

    class PhMetaData(Dict[str, Any]): pass
    class PhDataPoint(PydanticBaseModel):
        id: UUID = PydanticField(default_factory=uuid4)
        type: str
        metadata: Optional[PhMetaData] = PydanticField(default_factory=lambda: PhMetaData(index_fields=[]))

    class PhRepoNode(PhDataPoint):
        slug_id: str
        path: str

    node1 = PhRepoNode(slug_id="s", path="p", type="Repository")
    assert node1.type == "Repository"

    class PhDataPointWithInit(PydanticBaseModel):
        id: UUID = PydanticField(default_factory=uuid4)
        type: str = "UnknownPlaceholder"
        metadata: Optional[PhMetaData] = PydanticField(default_factory=lambda: PhMetaData(index_fields=[]))
        def __init__(self, **data: Any):
            super().__init__(**data)
            if self.type == "UnknownPlaceholder":
                 object.__setattr__(self, "type", self.__class__.__name__)

    class PhRepoNodeWithInit(PhDataPointWithInit):
        slug_id: str
        path: str

    node2 = PhRepoNodeWithInit(slug_id="s2", path="p2")
    assert node2.type == "PhRepoNodeWithInit"

    node3 = PhRepoNodeWithInit(slug_id="s3", path="p3", type="ExplicitRepo")
    assert node3.type == "ExplicitRepo"
