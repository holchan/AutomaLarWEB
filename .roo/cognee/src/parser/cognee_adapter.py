# .roo/cognee/src/parser/cognee_adapter.py
from typing import List, Dict, Any, Union, Tuple
import uuid
from datetime import datetime

from .utils import logger
# IMPORTANT: It imports all possible entities it might receive from the orchestrator
from .entities import (
    Repository, SourceFile, TextChunk, CodeEntity, Relationship,
    PendingLink, ResolutionCache
)

# --- Cognee Core Imports ---
from cognee.modules.data.models.base import DataPoint, MetaData
from cognee.modules.graph.graph_objects import CogneeEdgeTuple # Assumed path

# This is the list of all our parser-defined models that can be converted to a DataPoint node.
AdaptableNode = Union[Repository, SourceFile, TextChunk, CodeEntity, PendingLink, ResolutionCache]

def adapt_parser_entities_to_graph_elements(
    parser_entities: List[Union[AdaptableNode, Relationship]]
) -> Tuple[List[DataPoint], List[CogneeEdgeTuple]]:
    """
    Translates a list of parser-defined Pydantic models into a list of
    Cognee-compatible DataPoint nodes and a list of CogneeEdgeTuples.
    """
    log_prefix = "ADAPTER"
    logger.info(f"{log_prefix}: Starting adaptation of {len(parser_entities)} parser entities.")

    # 1. Separate nodes from relationships
    p_nodes: List[AdaptableNode] = [item for item in parser_entities if not isinstance(item, Relationship)]
    p_relationships: List[Relationship] = [item for item in parser_entities if isinstance(item, Relationship)]

    cognee_nodes: List[DataPoint] = []
    # This map is crucial for creating edges later, mapping our string ID to the final UUID
    slug_id_to_uuid_map: Dict[str, uuid.UUID] = {}

    for p_node in p_nodes:
        # Every adaptable node MUST have a unique 'id' string field.
        p_slug_id = p_node.id
        cognee_node_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, p_slug_id)
        slug_id_to_uuid_map[p_slug_id] = cognee_node_uuid

        # Create the metadata payload, ensuring all data is preserved.
        metadata_payload = MetaData(p_node.model_dump())
        metadata_payload["node_type"] = p_node.type
        metadata_payload["slug_id"] = p_slug_id # Store the human-readable ID for easy debugging

        # --- Define which fields should be indexed for fast queries ---
        index_fields = ["slug_id", "node_type"]
        if isinstance(p_node, SourceFile):
            # These fields are used by graph_utils to find files
            index_fields.extend(["repo_id_str", "relative_path_str", "version_id_str", "content_hash"])
        elif isinstance(p_node, Repository):
            # This is used to find libraries by their public name
            index_fields.append("provides_import_id")
        elif isinstance(p_node, PendingLink):
            # This is used by the linking engine workers to find work
            index_fields.append("status")
        elif isinstance(p_node, CodeEntity):
            # This is used by the linking engine to find link targets
            index_fields.append("canonical_fqn") # Assuming we add this field later

        metadata_payload["index_fields"] = sorted(list(set(index_fields)))

        cognee_node_instance = DataPoint(
            id=cognee_node_uuid,
            type=p_node.type, # Use our internal type as the graph node type/label
            metadata=metadata_payload
        )
        cognee_nodes.append(cognee_node_instance)

    # 2. Create edges using the UUIDs of the nodes we just processed
    edge_tuples_for_cognee: List[CogneeEdgeTuple] = []
    for p_rel in p_relationships:
        source_uuid = slug_id_to_uuid_map.get(p_rel.source_id)
        target_uuid = slug_id_to_uuid_map.get(p_rel.target_id)

        # It is critical that the orchestrator only gives us relationships
        # where both source and target nodes are also in the batch.
        if not source_uuid or not target_uuid:
            logger.warning(f"{log_prefix}: Skipping edge creation due to missing node ID in batch: {p_rel.source_id} -> {p_rel.target_id}")
            continue

        # The properties field allows adding metadata to edges, which can be powerful.
        edge_properties = p_rel.properties or {}
        edge_tuple = (source_uuid, target_uuid, p_rel.type.upper(), edge_properties)
        edge_tuples_for_cognee.append(edge_tuple)

    logger.info(f"{log_prefix}: Finished. Produced {len(cognee_nodes)} nodes and {len(edge_tuples_for_cognee)} edges.")
    return cognee_nodes, edge_tuples_for_cognee
