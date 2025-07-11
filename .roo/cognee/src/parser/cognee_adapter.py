from typing import List, Dict, Any, Union, Tuple
import uuid

from .utils import logger
from .entities import (
    Repository, SourceFile, TextChunk, CodeEntity, Relationship,
    PendingLink, ResolutionCache, AdaptableNode
)

from cognee.modules.graph.cognee_graph.CogneeGraphElements import Node, Edge

CogneeEdgeTuple = Tuple[str, str, str, Dict[str, Any]]

def adapt_parser_entities_to_graph_elements(
    parser_entities: List[Union[AdaptableNode, Relationship]]
) -> Tuple[List[Node], List[CogneeEdgeTuple]]:
    """
    Translates a list of parser-defined Pydantic models into a list of
    Cognee-compatible Node objects and a list of CogneeEdgeTuples.
    """
    log_prefix = "ADAPTER"
    logger.info(f"{log_prefix}: Starting adaptation of {len(parser_entities)} parser entities.")

    p_nodes: List[AdaptableNode] = [item for item in parser_entities if not isinstance(item, Relationship)]
    p_relationships: List[Relationship] = [item for item in parser_entities if isinstance(item, Relationship)]

    cognee_nodes: List[Node] = []
    slug_id_to_node_map: Dict[str, Node] = {}

    for p_node in p_nodes:
        p_slug_id = p_node.id
        attributes = p_node.model_dump()
        attributes["node_type"] = p_node.type
        attributes["slug_id"] = p_slug_id
        index_fields = ["slug_id", "node_type"]
        if isinstance(p_node, SourceFile):
            index_fields.extend(["repo_id_str", "relative_path_str", "content_hash"])
        elif isinstance(p_node, Repository):
            index_fields.append("provides_import_id")
        elif isinstance(p_node, PendingLink):
            index_fields.extend(["status", "awaits_fqn"])
        elif isinstance(p_node, CodeEntity):
            index_fields.append("canonical_fqn")

        attributes["index_fields"] = sorted(list(set(index_fields)))

        cognee_node_instance = Node(
            node_id=p_slug_id,
            attributes=attributes
        )
        cognee_nodes.append(cognee_node_instance)
        slug_id_to_node_map[p_slug_id] = cognee_node_instance
        edge_tuples_for_cognee: List[CogneeEdgeTuple] = []
        for p_rel in p_relationships:
            edge_tuple = (
                p_rel.source_id,
                p_rel.target_id,
                p_rel.type.upper(),
                p_rel.properties or {}
            )
            edge_tuples_for_cognee.append(edge_tuple)
        else:
            logger.warning(f"{log_prefix}: Skipping edge because source or target node was not in the same batch: {p_rel.source_id} -> {p_rel.target_id}")

    logger.info(f"{log_prefix}: Finished. Produced {len(cognee_nodes)} nodes and {len(edge_tuples_for_cognee)} edges.")
    return cognee_nodes, edge_tuples_for_cognee
