from typing import List, Dict, Any, AsyncGenerator, Optional, Tuple, Union
from pydantic import BaseModel as ParserBaseModel
import uuid

from .utils import logger

from .entities import (
    Repository as ParserRepository, SourceFile as ParserSourceFile,
    TextChunk as ParserTextChunk, CodeEntity as ParserCodeEntity,
    Relationship as ParserRelationship
)
from .custom_datapoints import (
    DataPoint, MetaData,
    RepositoryNode, SourceFileNode, TextChunkNode,
    CodeEntityNode
)

CogneeEdgeTuple = Tuple[uuid.UUID, uuid.UUID, str, Dict[str, Any]]
OrchestratorStreamItem = Union[
    ParserRepository,
    Tuple[ParserSourceFile, Dict[str, str]],
    ParserTextChunk, ParserCodeEntity, ParserRelationship
]

async def adapt_parser_to_graph_elements(
    parser_entity_stream: AsyncGenerator[OrchestratorStreamItem, None]
) -> Tuple[List[DataPoint], List[CogneeEdgeTuple]]:
    p_nodes_map: Dict[str, ParserBaseModel] = {}
    p_relationships_list: List[ParserRelationship] = []

    async for item_from_orchestrator in parser_entity_stream:
        p_entity: ParserBaseModel
        if isinstance(item_from_orchestrator, tuple) and \
           len(item_from_orchestrator) == 2 and \
           isinstance(item_from_orchestrator[0], ParserSourceFile) and \
           isinstance(item_from_orchestrator[1], dict):
            p_entity = item_from_orchestrator[0]
            p_nodes_map[p_entity.id] = p_entity
        elif isinstance(item_from_orchestrator, (ParserRepository, ParserTextChunk, ParserCodeEntity)):
            p_entity = item_from_orchestrator
            p_nodes_map[p_entity.id] = p_entity
        elif isinstance(item_from_orchestrator, ParserRelationship):
            p_relationships_list.append(item_from_orchestrator)
        else:
            logger.warning(f"Adapter: Unknown item type from orchestrator: {type(item_from_orchestrator)}")

    cognee_nodes_map: Dict[str, DataPoint] = {}
    edge_tuples_for_cognee: List[CogneeEdgeTuple] = []

    for p_slug_id, p_node in p_nodes_map.items():
        cognee_node_instance: Optional[DataPoint] = None
        cognee_node_uuid = uuid.uuid4()

        if isinstance(p_node, ParserRepository):
            cognee_node_instance = RepositoryNode(
                id=cognee_node_uuid,
                slug_id=p_node.id,
                path=p_node.path,
                type=p_node.type
            )
        elif isinstance(p_node, ParserSourceFile):
            cognee_node_instance = SourceFileNode(
                id=cognee_node_uuid,
                slug_id=p_node.id,
                file_path=p_node.file_path,
                timestamp=p_node.timestamp,
                type=p_node.type
            )
        elif isinstance(p_node, ParserTextChunk):
            cognee_node_instance = TextChunkNode(
                id=cognee_node_uuid,
                slug_id=p_node.id,
                start_line=p_node.start_line, end_line=p_node.end_line,
                chunk_content=p_node.chunk_content,
                type=p_node.type
            )
        elif isinstance(p_node, ParserCodeEntity):
            cognee_node_instance = CodeEntityNode(
                id=cognee_node_uuid,
                slug_id=p_node.id,
                snippet_content=p_node.snippet_content,
                type=p_node.type
            )

        if cognee_node_instance:
            cognee_nodes_map[p_slug_id] = cognee_node_instance

    for p_rel in p_relationships_list:
        source_cognee_node = cognee_nodes_map.get(p_rel.source_id)

        if not source_cognee_node:
            logger.warning(f"Adapter: Source node for slug_id '{p_rel.source_id}' not found for relationship.")
            continue

        rel_type_upper = p_rel.type.upper()

        if rel_type_upper == "IMPORTS":
            logger.debug(f"Adapter: 'IMPORTS' relationship from {p_rel.source_id} to literal '{p_rel.target_id}' is dropped.")
            continue

        target_cognee_node = cognee_nodes_map.get(p_rel.target_id)
        if not target_cognee_node:
            logger.warning(f"Adapter: Target node for slug_id '{p_rel.target_id}' not found for relationship type '{rel_type_upper}'.")
            continue

        edge_props = p_rel.properties or {}
        edge_tuple: CogneeEdgeTuple = (
            source_cognee_node.id,
            target_cognee_node.id,
            rel_type_upper,
            edge_props
        )
        edge_tuples_for_cognee.append(edge_tuple)

    return list(cognee_nodes_map.values()), edge_tuples_for_cognee
