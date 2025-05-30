import pytest
import asyncio
import uuid
from typing import List, Dict, Any, Union, Tuple, AsyncGenerator

from pydantic import BaseModel as PydanticBaseModel

try:
    from src.parser.entities import Repository as ParserRepository, \
                                      SourceFile as ParserSourceFile, \
                                      TextChunk as ParserTextChunk, \
                                      CodeEntity as ParserCodeEntity, \
                                      Relationship as ParserRelationship
except ImportError:
    pytest.skip("Skipping adapter tests: Failed to import parser entities", allow_module_level=True)

try:
    from src.parser.custom_datapoints import (
        DataPoint, MetaData,
        RepositoryNode, SourceFileNode, TextChunkNode,
        CodeEntityNode
    )
except ImportError:
    pytest.skip("Skipping adapter tests: Failed to import custom datapoint nodes", allow_module_level=True)

try:
    from src.parser.cognee_adapter import adapt_parser_to_graph_elements, OrchestratorStreamItem, CogneeEdgeTuple
except ImportError:
    pytest.skip("Skipping adapter tests: Failed to import cognee_adapter", allow_module_level=True)


pytestmark = pytest.mark.asyncio

async def mock_orchestrator_stream(items: List[OrchestratorStreamItem]) -> AsyncGenerator[OrchestratorStreamItem, None]:
    for item in items:
        yield item
        await asyncio.sleep(0)

async def test_adapt_empty_stream():
    stream = mock_orchestrator_stream([])
    nodes, edges = await adapt_parser_to_graph_elements(stream)
    assert len(nodes) == 0
    assert len(edges) == 0

async def test_adapt_repository_node():
    parser_repo = ParserRepository(id="repo-slug-1", path="/path/to/repo")
    stream = mock_orchestrator_stream([parser_repo])

    nodes, edges = await adapt_parser_to_graph_elements(stream)

    assert len(nodes) == 1
    assert len(edges) == 0

    repo_node = nodes[0]
    assert isinstance(repo_node, RepositoryNode)
    assert repo_node.slug_id == "repo-slug-1"
    assert repo_node.path == "/path/to/repo"
    assert repo_node.type == "Repository"
    assert isinstance(repo_node.id, uuid.UUID)
    assert repo_node.metadata.get("index_fields") == ["slug_id", "path", "type"]

async def test_adapt_sourcefile_node():
    parser_sf = ParserSourceFile(id="repo:src/main.py", file_path="/abs/src/main.py", timestamp="2023-01-01T12:00:00Z")
    sf_context = {"relative_path": "src/main.py", "language_key": "python"}

    stream_item: OrchestratorStreamItem = (parser_sf, sf_context)
    stream = mock_orchestrator_stream([stream_item])

    nodes, edges = await adapt_parser_to_graph_elements(stream)

    assert len(nodes) == 1
    assert len(edges) == 0

    sf_node = nodes[0]
    assert isinstance(sf_node, SourceFileNode)
    assert sf_node.slug_id == "repo:src/main.py"
    assert sf_node.file_path == "/abs/src/main.py"
    assert sf_node.timestamp == "2023-01-01T12:00:00Z"
    assert sf_node.type == "SourceFile"
    assert not hasattr(sf_node, "relative_path")
    assert not hasattr(sf_node, "language_key")
    assert isinstance(sf_node.id, uuid.UUID)
    assert sf_node.metadata.get("index_fields") == ["slug_id", "file_path", "timestamp", "type"]


async def test_adapt_textchunk_node():
    parser_tc = TextChunk(id="file:0", start_line=1, end_line=10, chunk_content="Hello world")
    stream = mock_orchestrator_stream([parser_tc])

    nodes, edges = await adapt_parser_to_graph_elements(stream)

    assert len(nodes) == 1
    tc_node = nodes[0]
    assert isinstance(tc_node, TextChunkNode)
    assert tc_node.slug_id == "file:0"
    assert tc_node.start_line == 1
    assert tc_node.end_line == 10
    assert tc_node.chunk_content == "Hello world"
    assert tc_node.type == "TextChunk"
    assert not hasattr(tc_node, "language_key")
    assert isinstance(tc_node.id, uuid.UUID)
    assert tc_node.metadata.get("index_fields") == ["slug_id", "start_line", "end_line", "chunk_content", "type"]

async def test_adapt_codeentity_node():
    parser_ce = CodeEntity(id="chunk:0:FunctionDefinition:myFunc:0", type="FunctionDefinition", snippet_content="def myFunc(): pass")
    stream = mock_orchestrator_stream([parser_ce])

    nodes, edges = await adapt_parser_to_graph_elements(stream)

    assert len(nodes) == 1
    ce_node = nodes[0]
    assert isinstance(ce_node, CodeEntityNode)
    assert ce_node.slug_id == "chunk:0:FunctionDefinition:myFunc:0"
    assert ce_node.snippet_content == "def myFunc(): pass"
    assert ce_node.type == "FunctionDefinition"
    assert not hasattr(ce_node, "name")
    assert not hasattr(ce_node, "language_key")
    assert isinstance(ce_node.id, uuid.UUID)
    assert ce_node.metadata.get("index_fields") == ["slug_id", "snippet_content", "type"]


async def test_adapt_nodes_and_relationships():
    repo1 = ParserRepository(id="repo1", path="/repo1")
    sf1_id = "repo1:file1.py"
    sf1_context = {"relative_path": "file1.py", "language_key": "python"}
    sf1 = ParserSourceFile(id=sf1_id, file_path="/repo1/file1.py", timestamp="ts1")

    ce1_id = f"{sf1_id}:0:FunctionDef:foo:0"
    ce1 = CodeEntity(id=ce1_id, type="FunctionDef", snippet_content="def foo(): global_var")

    rel1 = ParserRelationship(source_id=repo1.id, target_id=sf1.id, type="CONTAINS_FILE")
    rel2 = ParserRelationship(source_id=sf1.id, target_id=ce1.id, type="DEFINES_ENTITY")
    rel_import = ParserRelationship(source_id=sf1.id, target_id="os", type="IMPORTS")

    stream_items: List[OrchestratorStreamItem] = [
        repo1,
        (sf1, sf1_context),
        ce1,
        rel1,
        rel2,
        rel_import
    ]
    stream = mock_orchestrator_stream(stream_items)
    nodes, edges = await adapt_parser_to_graph_elements(stream)

    assert len(nodes) == 3
    assert len(edges) == 2

    node_map_by_slug = {n.slug_id: n for n in nodes}
    assert repo1.id in node_map_by_slug
    assert sf1.id in node_map_by_slug
    assert ce1.id in node_map_by_slug

    repo_node_uuid = node_map_by_slug[repo1.id].id
    sf_node_uuid = node_map_by_slug[sf1.id].id
    ce_node_uuid = node_map_by_slug[ce1.id].id

    expected_edge1: CogneeEdgeTuple = (repo_node_uuid, sf_node_uuid, "CONTAINS_FILE", {})
    expected_edge2: CogneeEdgeTuple = (sf_node_uuid, ce_node_uuid, "DEFINES_ENTITY", {})

    assert expected_edge1 in edges
    assert expected_edge2 in edges

    sf_node_retrieved = node_map_by_slug[sf1.id]
    assert isinstance(sf_node_retrieved, SourceFileNode)
    assert not hasattr(sf_node_retrieved, "imports_module_names")


async def test_relationship_with_properties():
    sf_id = "repo:file.py"
    sf_context = {"relative_path": "file.py", "language_key": "python"}
    sf = ParserSourceFile(id=sf_id, file_path="/file.py", timestamp="ts")

    ce_id = f"{sf_id}:0:FunctionDef:bar:0"
    ce = CodeEntity(id=ce_id, type="FunctionDef", snippet_content="def bar(): pass")

    rel_props = {"line": 10, "detail": "important call"}
    rel = ParserRelationship(source_id=sf.id, target_id=ce.id, type="HAS_FUNCTION", properties=rel_props)

    stream = mock_orchestrator_stream([(sf, sf_context), ce, rel])
    nodes, edges = await adapt_parser_to_graph_elements(stream)

    assert len(nodes) == 2
    assert len(edges) == 1

    edge = edges[0]
    assert edge[2] == "HAS_FUNCTION"
    assert edge[3] == rel_props
