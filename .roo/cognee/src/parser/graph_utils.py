import asyncio
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime, timezone

from .utils import logger
from .entities import PendingLink, LinkStatus

from cognee.infrastructure.engine.models.DataPoint import DataPoint, MetaData
from cognee.modules.graph.graph_objects import CogneeEdgeTuple
from cognee.infrastructure.databases.graph.get_graph_engine import get_graph_engine
from cognee.modules.graph.methods.delete import delete_nodes_by_metadata
from cognee.modules.graph.methods.search import find_nodes_by_metadata
from cognee.modules.graph.operations.add import add_nodes, add_edges
from cognee.modules.graph.operations.update import update_node_metadata

class IngestionHeartbeat(DataPoint):
    type: str = "IngestionHeartbeat"

GRAPH_ADAPTER = None
async def get_adapter():
    global GRAPH_ADAPTER
    if GRAPH_ADAPTER is None:
        GRAPH_ADAPTER = await get_graph_engine()
    return GRAPH_ADAPTER

async def find_nodes_with_filter(filter_dict: Dict[str, Any], limit: int = None) -> List[Node]:
    """Generic function to find nodes matching a metadata filter."""
    adapter = await get_adapter()
    nodes, _ = await adapter.get_filtered_graph_data([filter_dict], limit=limit)
    return [node for node, _ in nodes]

async def delete_nodes_with_filter(filter_dict: Dict[str, Any]):
    """Generic function to delete nodes matching a metadata filter."""
    adapter = await get_adapter()
    nodes_to_delete, _ = await adapter.get_filtered_graph_data([filter_dict])
    node_ids_to_delete = [node.id for node, _ in nodes_to_delete]
    if node_ids_to_delete:
        logger.info(f"GRAPH_UTILS: Deleting {len(node_ids_to_delete)} nodes matching filter {filter_dict}")
        await adapter.delete_nodes(node_ids_to_delete)

async def save_graph_data(nodes: List[Node], edges: List[CogneeEdgeTuple]):
    """Saves a batch of nodes and edges to the graph."""
    if not nodes and not edges:
        return
    adapter = await get_adapter()
    log_prefix = "GRAPH_UTILS (SAVE)"
    logger.info(f"{log_prefix}: Saving {len(nodes)} nodes and {len(edges)} edges.")
    if nodes:
        await adapter.add_nodes(nodes)
    if edges:
        await adapter.add_edges(edges)
    logger.info(f"{log_prefix}: Save command executed.")

async def update_node_metadata(node_id: str, new_metadata: Dict[str, Any]):
    """Updates specific metadata fields for a single node."""
    adapter = await get_adapter()
    await adapter.update_node(node_id, new_metadata)

async def update_heartbeat(repo_id_with_branch: str):
    """Creates or updates an IngestionHeartbeat node with the current timestamp."""
    adapter = await get_adapter()
    heartbeat_id = f"heartbeat://{repo_id_with_branch}"
    heartbeat_node = IngestionHeartbeat(
        id=heartbeat_id,
        attributes={
            "last_activity_timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "active"
        }
    )
    await adapter.add_node(heartbeat_node)
