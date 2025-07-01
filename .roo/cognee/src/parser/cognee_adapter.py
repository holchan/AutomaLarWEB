from typing import List, Dict, Any, Union
import uuid

from .utils import logger
from .entities import Repository, SourceFile, TextChunk, CodeEntity, Relationship

from cognee.modules.data.models.base import DataPoint, MetaData

CogneeEdgeTuple = Tuple[uuid.UUID, uuid.UUID, str, Dict[str, Any]]

def adapt_parser_entities_to_graph_elements(
    parser_entities: List[Union[Repository, SourceFile, TextChunk, CodeEntity, Relationship]]
) -> Tuple[List[DataPoint], List[CogneeEdgeTuple]]:
    logger.info(f"ADAPTER: Starting adaptation of {len(parser_entities)} parser entities.")

    p_nodes_map: Dict[str, Union[Repository, SourceFile, TextChunk, CodeEntity]] = {
        item.id: item for item in parser_entities if hasattr(item, 'id') and not isinstance(item, Relationship)
    }
    p_relationships_list: List[Relationship] = [
        item for item in parser_entities if isinstance(item, Relationship)
    ]

    cognee_nodes_map: Dict[str, DataPoint] = {}

    for p_slug_id, p_node in p_nodes_map.items():
        cognee_node_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, p_slug_id)

        metadata_payload = MetaData(p_node.model_dump())
        metadata_payload["node_type"] = p_node.type
        metadata_payload["slug_id"] = p_slug_id

        index_fields = ["slug_id", "node_type"]
        if isinstance(p_node, SourceFile):
            index_fields.extend(["repo_id_str", "relative_path_str", "version_id_str"])
        elif isinstance(p_node, Repository):
             index_fields.extend(["path"])

        metadata_payload["index_fields"] = sorted(list(set(index_fields)))

        cognee_node_instance = DataPoint(
            id=cognee_node_uuid,
            type=p_node.type,
            metadata=metadata_payload
        )
        cognee_nodes_map[p_slug_id] = cognee_node_instance

    edge_tuples_for_cognee = []
    for p_rel in p_relationships_list:
        source_node = cognee_nodes_map.get(p_rel.source_id)
        target_node = cognee_nodes_map.get(p_rel.target_id)

        if not source_node or not target_node:
            logger.warning(f"ADAPTER: Skipping edge due to missing node: {p_rel.source_id} -> {p_rel.target_id}")
            continue

        edge_tuple = (source_node.id, target_node.id, p_rel.type.upper(), p_rel.properties or {})
        edge_tuples_for_cognee.append(edge_tuple)

    final_node_list = list(cognee_nodes_map.values())
    logger.info(f"ADAPTER: Finished. Produced {len(final_node_list)} nodes and {len(edge_tuples_for_cognee)} edges.")
    return final_node_list, edge_tuples_for_cognee
