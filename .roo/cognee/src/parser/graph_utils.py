import asyncio
from typing import List, Tuple, Dict, Any

from .utils import logger
from .entities import DataPoint, Relationship, CogneeEdgeTuple

from cognee.infrastructure.databases.graph import get_graph_engine
from cognee.modules.graph.methods.delete_graph_nodes import delete_nodes_by_metadata
from cognee.modules.graph.methods.search_graph_nodes import find_nodes_by_metadata
from cognee.modules.graph.operations.add_nodes import add_nodes
from cognee.modules.graph.operations.add_edges import add_edges

async def delete_all_versions_of_file(tx_handle: Any, repo_id_with_branch: str, relative_path: str):
    """
    Deletes all graph nodes (SourceFile and its descendants) associated with
    a specific file path on a specific branch, using the provided transaction handle.
    """
    log_prefix = f"GRAPH_UTILS (DELETE: {repo_id_with_branch}|{relative_path})"
    logger.info(f"{log_prefix}: Issuing delete command for all versions.")

    filter_metadata = { "repo_id_str": repo_id_with_branch, "relative_path_str": relative_path }
    await delete_nodes_by_metadata(tx_handle, filter_metadata, cascade_delete=True)
    logger.info(f"{log_prefix}: Deletion command executed.")

async def get_latest_local_save_count(tx_handle: Any, repo_id_with_branch: str, relative_path: str, commit_index: str) -> int:
    """
    Finds the highest local save count for a file at a specific commit by querying the graph
    using the provided transaction handle.
    """
    log_prefix = f"GRAPH_UTILS (QUERY: {repo_id_with_branch}|{relative_path}@{commit_index})"

    filter_metadata = { "repo_id_str": repo_id_with_branch, "relative_path_str": relative_path }
    all_file_versions = await find_nodes_by_metadata(tx_handle, filter_metadata, node_type='SourceFile')

    version_prefix_to_match = f"{commit_index}-"
    highest_save_count = -1

    for node in all_file_versions:
        version_id = node.metadata.get("version_id_str", "")
        if version_id.startswith(version_prefix_to_match):
            try:
                save_count_str = version_id.split('-')[-1]
                highest_save_count = max(highest_save_count, int(save_count_str))
            except (ValueError, IndexError):
                logger.warning(f"{log_prefix}: Found malformed version_id '{version_id}'. Skipping.")

    final_count = highest_save_count if highest_save_count != -1 else 0
    logger.debug(f"{log_prefix}: Found latest local save count as: {final_count}.")
    return final_count

async def save_graph_data(tx_handle: Any, nodes: List[DataPoint], edges: List[CogneeEdgeTuple]):
    """
    Saves a batch of nodes and edges to the graph within a single transaction.
    """
    log_prefix = f"GRAPH_UTILS (SAVE)"
    logger.info(f"{log_prefix}: Saving {len(nodes)} nodes and {len(edges)} edges to the graph.")
    if nodes:
        await add_nodes(tx_handle, nodes)
    if edges:
        await add_edges(tx_handle, edges)
    logger.info(f"{log_prefix}: Save command executed.")
