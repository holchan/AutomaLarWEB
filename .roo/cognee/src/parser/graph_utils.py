# .roo/cognee/src/parser/graph_utils.py
import asyncio
from datetime import datetime, timezone
from typing import List, Tuple, Dict, Any, Optional
import uuid
import time
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception, before_sleep_log

from .utils import logger
from .entities import PendingLink, LinkStatus

from cognee.modules.graph.cognee_graph.CogneeGraphElements import Node
from cognee.infrastructure.databases.graph.get_graph_engine import get_graph_engine

# Import Neo4j-specific exceptions for robust error handling
try:
    import neo4j
    NEO4J_TRANSIENT_EXCEPTIONS = (
        neo4j.exceptions.ServiceUnavailable,
        neo4j.exceptions.SessionExpired,
        neo4j.exceptions.TransientError,
    )
except ImportError:
    # Fallback if neo4j driver is not installed, though it should be.
    NEO4J_TRANSIENT_EXCEPTIONS = ()


_graph_adapter_instance = None
async def get_adapter():
    """A robust singleton accessor for the graph engine adapter."""
    global _graph_adapter_instance
    if _graph_adapter_instance is None:
        _graph_adapter_instance = await get_graph_engine()
    return _graph_adapter_instance

def is_transient_error(exception: BaseException) -> bool:
    """Predicate for tenacity to retry only on specific, recoverable database/network errors."""
    generic_transient_types = (ConnectionError, TimeoutError, asyncio.TimeoutError)
    all_transient_errors = generic_transient_types + NEO4J_TRANSIENT_EXCEPTIONS
    return isinstance(exception, all_transient_errors)

# --- Schema and Index Management ---

async def ensure_all_indexes():
    """Ensures all necessary indexes and constraints exist in Neo4j. This is a safe, idempotent operation."""
    log_prefix = "GRAPH_UTILS(Indexing)"
    logger.info(f"{log_prefix}: Verifying and creating required database indexes...")
    adapter = await get_adapter()

    unique_id_labels = ["Repository", "SourceFile", "TextChunk", "CodeEntity", "PendingLink", "ResolutionCache"]
    required_indexes = [
        ("SourceFile", "content_hash"), ("PendingLink", "status"),
        ("PendingLink", "awaits_fqn"), ("CodeEntity", "canonical_fqn"),
    ]
    required_composite_indexes = [("SourceFile", ("repo_id_str", "relative_path_str", "commit_index"))]

    try:
        for label in unique_id_labels:
            constraint_name = f"constraint_{label.lower()}_unique_slug_id"
            await adapter.execute_query(f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS FOR (n:{label}) REQUIRE n.slug_id IS UNIQUE")
            logger.info(f"{log_prefix}: Ensured UNIQUE constraint (and index) on ({label}, slug_id).")

        for label, attribute in required_indexes:
            index_name = f"idx_{label.lower()}_{attribute.lower()}"
            await adapter.execute_query(f"CREATE INDEX {index_name} IF NOT EXISTS FOR (n:{label}) ON (n.{attribute})")

        for label, attributes in required_composite_indexes:
            attr_str = "_".join(attributes)
            index_name = f"idx_{label.lower()}_{attr_str.lower()}"
            attrs_cypher = ", ".join([f"n.{attr}" for attr in attributes])
            await adapter.execute_query(f"CREATE INDEX {index_name} IF NOT EXISTS FOR (n:{label}) ON ({attrs_cypher})")

        logger.info(f"{log_prefix}: Index verification complete.")
    except Exception as e:
        logger.critical(f"{log_prefix}: FAILED to ensure database indexes. Error: {e}", exc_info=True)

# --- Core Graph Operations with Retries ---

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception(is_transient_error), before_sleep=before_sleep_log(logger, "WARNING"))
async def execute_cypher_query(query: str, params: Dict[str, Any] = None) -> List[Dict]:
    """Executes a raw Cypher query with parameters and returns a list of raw records."""
    adapter = await get_adapter()
    return await adapter.execute_query(query, parameters=params or {})

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception(is_transient_error), before_sleep=before_sleep_log(logger, "WARNING"))
async def find_nodes_with_filter(filter_dict: Dict[str, Any]) -> List[Node]:
    """Generic function to find nodes matching a metadata filter, with retries."""
    if not filter_dict:
        logger.warning("GRAPH_UTILS(find): Empty filter provided. Returning empty list.")
        return []
    adapter = await get_adapter()
    nodes, _ = await adapter.get_filtered_graph_data([filter_dict])
    return [node for node, data in nodes]

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception(is_transient_error), before_sleep=before_sleep_log(logger, "WARNING"))
async def delete_nodes_with_filter(filter_dict: Dict[str, Any]):
    """Generic function to delete nodes matching a metadata filter, with retries."""
    if not filter_dict: return
    adapter = await get_adapter()
    nodes_to_delete, _ = await adapter.get_filtered_graph_data([filter_dict])
    if node_ids_to_delete := [node.id for node, data in nodes_to_delete]:
        logger.info(f"GRAPH_UTILS(delete): Deleting {len(node_ids_to_delete)} nodes.")
        await adapter.delete_nodes(node_ids_to_delete)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception(is_transient_error), before_sleep=before_sleep_log(logger, "WARNING"))
async def save_graph_data(nodes: List[Node], relationships: List[Tuple[str, str, str, Dict[str, Any]]]):
    """Saves a batch of nodes and edges to the graph, with retries."""
    if not nodes and not relationships: return
    adapter = await get_adapter()
    logger.info(f"GRAPH_UTILS(save): Saving {len(nodes)} nodes and {len(relationships)} relationships.")
    if nodes: await adapter.add_nodes(nodes)
    if relationships: await adapter.add_edges(relationships)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception(is_transient_error), before_sleep=before_sleep_log(logger, "WARNING"))
async def atomic_get_and_increment_local_save(repo_id_with_branch: str, relative_path: str, commit_index: int) -> int:
    """Atomically finds or creates a file's version counter and increments it, returning the new value."""
    # This query atomically finds a counter node or creates it, then increments and returns the new value.
    cypher_query = """
    MERGE (v:VersionCounter { repo_id: $repo_id, path: $path, commit: $commit })
    ON CREATE SET v.count = 1
    ON MATCH SET v.count = COALESCE(v.count, 0) + 1
    RETURN v.count as new_count
    """
    params = {"repo_id": repo_id_with_branch, "path": relative_path, "commit": commit_index}
    result = await execute_cypher_query(cypher_query, params)

    if result and result[0]: return result[0].get("new_count")
    logger.error("GRAPH_UTILS(atomic_counter): Atomic increment failed. Returning default of 1.")
    return 1 # Fallback

async def check_content_exists(content_hash: str) -> bool:
    """Checks if a SourceFile node with a specific content hash already exists."""
    nodes = await find_nodes_with_filter({'content_hash': content_hash, 'type': 'SourceFile'})
    return len(nodes) > 0

async def find_code_entity_by_path(repo_id_with_branch: str, relative_path: Optional[str], fqn: str) -> Optional[str]:
    """Finds a CodeEntity by path and/or FQN using an optimized Cypher query."""
    params = {"repo_id": repo_id_with_branch, "fqn": fqn}
    if relative_path:
        query = "MATCH (n:CodeEntity { repo_id_str: $repo_id, relative_path_str: $path, canonical_fqn: $fqn }) RETURN n.id as id LIMIT 1"
        params["path"] = relative_path
    else:
        query = "MATCH (n:CodeEntity { repo_id_str: $repo_id, canonical_fqn: $fqn }) RETURN n.id as id LIMIT 1"

    records = await execute_cypher_query(query, params)
    return records[0].get("id") if records else None

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception(is_transient_error), before_sleep=before_sleep_log(logger, "WARNING"))
async def update_pending_link_status(link_id: str, new_status: LinkStatus, new_metadata: Dict = None):
    """Updates the status and metadata of a single PendingLink node."""
    if not isinstance(new_status, LinkStatus):
        logger.error(f"GRAPH_UTILS(update_pending): Invalid status type: {new_status}. Aborting."); return
    adapter = await get_adapter()
    update_payload = {"status": new_status.value}
    if new_metadata: update_payload.update(new_metadata)
    await adapter.update_node(link_id, update_payload)
