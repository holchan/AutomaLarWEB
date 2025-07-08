# .roo/cognee/src/parser/graph_utils.py
import asyncio
import hashlib
from datetime import datetime, timezone
from typing import List, Tuple, Dict, Any, Optional

from .utils import logger
# It only needs to import the Enums and data structures it directly uses
from .entities import LinkStatus, PendingLink

# --- Cognee Core Imports (from our previous research) ---
from cognee.modules.data.models.base import DataPoint, MetaData
from cognee.modules.graph.graph_objects import CogneeEdgeTuple
from cognee.infrastructure.databases.graph import get_graph_db
from cognee.modules.graph.methods.delete import delete_nodes_by_metadata
from cognee.modules.graph.methods.search import find_nodes_by_metadata
from cognee.modules.graph.operations.add import add_nodes, add_edges
from cognee.modules.graph.operations.update import update_node_metadata

# This is a data model used by this module, so it's defined here.
class IngestionHeartbeat(DataPoint):
    type: str = "IngestionHeartbeat"

async def delete_all_versions_of_file(tx_handle: Any, repo_id_with_branch: str, relative_path: str):
    """Deletes all graph nodes associated with a specific file path on a specific branch."""
    log_prefix = f"GRAPH_UTILS (DELETE: {repo_id_with_branch}|{relative_path})"
    logger.info(f"{log_prefix}: Issuing delete command.")
    filter_metadata = { "repo_id_str": repo_id_with_branch, "relative_path_str": relative_path }
    await delete_nodes_by_metadata(tx_handle, filter_metadata, cascade_delete=True)
    logger.info(f"{log_prefix}: Deletion command executed.")

async def get_latest_local_save_count(tx_handle: Any, repo_id_with_branch: str, relative_path: str, commit_index: str) -> int:
    """Finds the highest local save count for a file at a specific commit."""
    log_prefix = f"GRAPH_UTILS (QUERY: {repo_id_with_branch}|{relative_path}@{commit_index})"
    filter_metadata = { "repo_id_str": repo_id_with_branch, "relative_path_str": relative_path }
    custom_filters = {'version_id_str': {'op': 'STARTS_WITH', 'value': f"{commit_index}-"}}

    matching_versions = await find_nodes_by_metadata(
        tx_handle, filter_metadata, node_type='SourceFile', custom_filters=custom_filters
    )

    highest_save_count = -1
    for node in matching_versions:
        version_id = node.metadata.get("version_id_str", "")
        try:
            save_count_str = version_id.split('-')[-1]
            highest_save_count = max(highest_save_count, int(save_count_str))
        except (ValueError, IndexError):
            logger.warning(f"{log_prefix}: Found malformed version_id '{version_id}'. Skipping.")

    return highest_save_count if highest_save_count > -1 else 0

async def save_graph_data(tx_handle: Any, nodes: List[DataPoint], edges: List[CogneeEdgeTuple]):
    """Saves a batch of nodes and edges to the graph within a single transaction."""
    if not nodes and not edges:
        return
    log_prefix = f"GRAPH_UTILS (SAVE)"
    logger.info(f"{log_prefix}: Saving {len(nodes)} nodes and {len(edges)} edges.")
    if nodes:
        await add_nodes(tx_handle, nodes)
    if edges:
        await add_edges(tx_handle, edges)
    logger.info(f"{log_prefix}: Save command executed.")

async def check_content_exists(tx_handle: Any, content_hash: str) -> bool:
    """Checks if a SourceFile node with a specific content hash already exists."""
    logger.debug(f"GRAPH_UTILS: Checking for content hash {content_hash}")
    nodes = await find_nodes_by_metadata(tx_handle, {'content_hash': content_hash}, node_type='SourceFile')
    return len(nodes) > 0

async def find_code_entity_by_path(tx_handle: Any, repo_id: str, branch: str, relative_path: str, fqn: str) -> Optional[str]:
    """Finds the latest version of a CodeEntity by its repo, path, and FQN."""
    # This is a placeholder for a more complex query logic that would be needed.
    return None

async def update_heartbeat(tx_handle: Any, repo_id_with_branch: str):
    """Creates or updates an IngestionHeartbeat node with the current timestamp."""
    heartbeat_id = f"heartbeat://{repo_id_with_branch}"
    logger.debug(f"GRAPH_UTILS: Updating heartbeat for {heartbeat_id}")
    heartbeat_node = IngestionHeartbeat(
        id=heartbeat_id,
        metadata={
            "last_activity_timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "active"
        }
    )
    # Using add_nodes with a deterministic ID achieves an upsert.
    await add_nodes(tx_handle, [heartbeat_node])

async def find_pending_links(tx_handle: Any, status: LinkStatus, limit: int = 100) -> List[PendingLink]:
    """Finds all PendingLink nodes with a given status."""
    logger.debug(f"GRAPH_UTILS: Querying for PendingLinks with status '{status.value}'.")
    found_nodes = await find_nodes_by_metadata(tx_handle, {"status": status.value}, node_type='PendingLink', limit=limit)
    # Re-hydrate the Pydantic model from the raw graph node data
    return [PendingLink(**node.metadata) for node in found_nodes]

async def update_pending_link_status(tx_handle: Any, link_id: str, new_status: LinkStatus):
    """Updates the status of a single PendingLink node."""
    logger.debug(f"GRAPH_UTILS: Updating PendingLink '{link_id}' to status '{new_status.value}'.")
    await update_node_metadata(tx_handle, link_id, {"status": new_status.value})

async def delete_pending_link(tx_handle: Any, link_id: str):
    """Deletes a single PendingLink node by its slug ID."""
    logger.debug(f"GRAPH_UTILS: Deleting PendingLink '{link_id}'.")
    await delete_nodes_by_metadata(tx_handle, {"slug_id": link_id}, node_type="PendingLink")
