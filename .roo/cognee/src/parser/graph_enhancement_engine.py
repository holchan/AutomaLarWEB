# .roo/cognee/src/parser/graph_enhancement_engine.py
import asyncio
from typing import List, Any, Optional, Dict
from pydantic import BaseModel
from collections import defaultdict

from .utils import logger, read_file_content
from .entities import LinkStatus, RawSymbolReference, ResolutionMethod, Relationship, CodeEntity
from .configs import BATCH_SIZE_LLM_ENHANCEMENT
from .graph_utils import (
    find_nodes_with_filter,
    update_pending_link_status,
    save_graph_data,
    delete_nodes_with_filter,
    execute_cypher_query,
    find_code_entity_by_path,
)
from .entities import ResolutionCache

# --- Pydantic model to enforce structured LLM output ---
class LLMResolutionAnswer(BaseModel):
    link_id: str
    # The LLM's one and only job is to fill this field.
    # It should be null if it cannot find a single, best answer.
    resolved_canonical_fqn: Optional[str]

#--------------------------------------------------------------------------------#
# Private Helper Functions
#--------------------------------------------------------------------------------#

async def _create_final_link(pending_link_node: Any, target_id: str, method: ResolutionMethod, repo_id_str: str):
    """Helper to create the final relationship, cache the result, and delete the debt."""
    log_prefix = f"ENHANCEMENT ({repo_id_str})"
    ref_data = RawSymbolReference(**pending_link_node.attributes['reference_data'])

    relationship_to_create = Relationship(
        source_id=ref_data.source_entity_id,
        target_id=target_id,
        type=ref_data.reference_type,
        properties=ref_data.metadata or {}
    )

    cache_node = ResolutionCache(id=pending_link_node.id, resolved_target_id=target_id, method=method)

    await save_graph_data(nodes=[cache_node], relationships=[relationship_to_create])
    await delete_nodes_with_filter({"type": "PendingLink", "slug_id": pending_link_node.id})
    logger.info(f"{log_prefix}: Successfully resolved link {pending_link_node.id} to {target_id} via {method.value}.")

async def _promote_to_llm(pending_link_node: Any, candidates: List[str], repo_id_str: str):
    """Helper to escalate a link to the LLM tier, attaching candidate info."""
    log_prefix = f"ENHANCEMENT ({repo_id_str})"
    logger.info(f"{log_prefix}: Promoting link {pending_link_node.id} to LLM tier with {len(candidates)} candidates.")
    metadata_update = {"candidates": candidates or []}
    await update_pending_link_status(pending_link_node.id, LinkStatus.READY_FOR_LLM, metadata_update)

#--------------------------------------------------------------------------------#
# Public Task: Tier 2 Enhancement
#--------------------------------------------------------------------------------#

async def run_tier2_enhancement(repo_id_with_branch: str):
    """A one-shot task to run all Tier 2 heuristics for a specific repository."""
    log_prefix = f"ENHANCEMENT(Tier2) for {repo_id_with_branch}"
    logger.info(f"{log_prefix}: Starting run.")

    links_to_process = await find_nodes_with_filter({
        "type": "PendingLink",
        "status": LinkStatus.READY_FOR_HEURISTICS.value,
        "repo_id_str": repo_id_with_branch
    })

    logger.info(f"{log_prefix}: Found {len(links_to_process)} links to process.")

    for link_node in links_to_process:
        try:
            ref_data = RawSymbolReference(**link_node.attributes['reference_data'])

            # --- Attempt 1: Internal Link by Exact FQN Match ---
            exact_matches = await find_nodes_with_filter({"type": "CodeEntity", "canonical_fqn": ref_data.target_expression, "repo_id_str": repo_id_with_branch})
            if len(exact_matches) == 1:
                await _create_final_link(link_node, exact_matches[0].id, ResolutionMethod.HEURISTIC_MATCH, repo_id_with_branch)
                continue

            # --- Attempt 2: Verified Suffix Match (using direct Cypher for Neo4j) ---
            suffix_matches = []
            if "::" in ref_data.target_expression or "." in ref_data.target_expression:
                cypher_query = "MATCH (n:CodeEntity) WHERE n.repo_id_str = $repo_id AND n.canonical_fqn ENDS WITH $suffix RETURN n"
                params = {"repo_id": repo_id_with_branch, "suffix": ref_data.target_expression}
                suffix_matches = await execute_cypher_query(cypher_query, params)
                if len(suffix_matches) == 1:
                    await _create_final_link(link_node, suffix_matches[0].id, ResolutionMethod.HEURISTIC_MATCH, repo_id_with_branch)
                    continue

            # --- If all attempts fail or are ambiguous, promote to LLM tier ---
            all_candidates = [node.id for node in exact_matches] + [node.id for node in suffix_matches]
            await _promote_to_llm(link_node, candidates=list(set(all_candidates)), repo_id_str=repo_id_with_branch)

        except Exception as e:
            logger.error(f"{log_prefix}: Failed to process link {link_node.id}. Marking as UNRESOLVABLE. Error: {e}", exc_info=True)
            await update_pending_link_status(link_node.id, LinkStatus.UNRESOLVABLE, {"reason": str(e)})

    logger.info(f"{log_prefix}: Run complete.")

#--------------------------------------------------------------------------------#
# Public Task: Tier 3 Enhancement (The "Consult, Verify, Cache" Engine)
#--------------------------------------------------------------------------------#

async def run_tier3_enhancement(repo_id_with_branch: str):
    """A one-shot task to run all Tier 3 LLM resolutions for a specific repository."""
    log_prefix = f"ENHANCEMENT(Tier3) for {repo_id_with_branch}"
    logger.info(f"{log_prefix}: Starting run.")

    links_to_process = await find_nodes_with_filter({
        "type": "PendingLink",
        "status": LinkStatus.READY_FOR_LLM.value,
        "repo_id_str": repo_id_with_branch
    })

    if not links_to_process:
        logger.info(f"{log_prefix}: No links ready for LLM processing.")
        return

    links_by_file: Dict[str, List[Any]] = defaultdict(list)
    for link_node in links_to_process:
        # Extract the relative path from the source entity ID
        # e.g., from 'my-repo@main|src/app.py@1-1|0@1-20|...''
        try:
            source_file_path = link_node.attributes['reference_data']['source_entity_id'].split('|', 2)[1].split('@')[0]
            links_by_file[source_file_path].append(link_node)
        except IndexError:
            logger.warning(f"{log_prefix}: Could not parse source file path from link {link_node.id}. Skipping.")

    logger.info(f"{log_prefix}: Found {len(links_to_process)} links across {len(links_by_file)} files for LLM processing.")

    for source_file_path, links in links_by_file.items():
        try:
            # 1. CONSTRUCT PROMPT (The "Case File")
            # In a real implementation, you would fetch the file content here using the source_file_path
            # For now, we use a placeholder.
            file_content_placeholder = f"// Content of {source_file_path} would be here."

            unresolved_references_for_prompt = []
            for link_node in links:
                unresolved_references_for_prompt.append({
                    "link_id": link_node.id,
                    "target_expression": link_node.attributes['reference_data']['target_expression'],
                    "candidates": link_node.attributes.get('candidates', [])
                })

            prompt = f"..." # The full prompt template from our plan would go here

            # 2. CONSULT: Call the LLM with structured output enforcement
            # from cognee.modules.llm import get_completion
            # llm_response = await get_completion(prompt, response_format=LLMResolutionAnswer.model_json_schema())
            # llm_answers = [LLMResolutionAnswer(**item) for item in llm_response]
            llm_answers: List[LLMResolutionAnswer] = [] # Placeholder response

            # 3. VERIFY AND ACT
            for answer in llm_answers:
                link_node_to_update = next((l for l in links if l.id == answer.link_id), None)
                if not link_node_to_update: continue

                if not answer.resolved_canonical_fqn:
                    logger.warning(f"{log_prefix}: LLM returned null for link {answer.link_id}. Marking as UNRESOLVABLE.")
                    await update_pending_link_status(answer.link_id, LinkStatus.UNRESOLVABLE, {"reason": "LLM returned null."})
                    continue

                verified_target_id = await find_code_entity_by_path(repo_id_with_branch, None, answer.resolved_canonical_fqn)

                if verified_target_id:
                    logger.info(f"{log_prefix}: LLM hint for link {answer.link_id} ('{answer.resolved_canonical_fqn}') was VERIFIED.")
                    await _create_final_link(link_node_to_update, verified_target_id, ResolutionMethod.LLM, repo_id_with_branch)
                else:
                    logger.warning(f"{log_prefix}: LLM hint for link {answer.link_id} ('{answer.resolved_canonical_fqn}') COULD NOT BE VERIFIED. Deferring.")
                    await update_pending_link_status(answer.link_id, LinkStatus.AWAITING_TARGET, {"awaits_fqn": answer.resolved_canonical_fqn})

        except Exception as e:
            logger.error(f"{log_prefix}: Failed to process LLM batch for file {source_file_path}. Marking batch as FAILED. Error: {e}", exc_info=True)
            for link_node in links:
                await update_pending_link_status(link_node.id, LinkStatus.UNRESOLVABLE, {"reason": "LLM batch processing failed."})

    logger.info(f"{log_prefix}: Run complete.")

#--------------------------------------------------------------------------------#
# Public Task: Repair Worker
#--------------------------------------------------------------------------------#

async def run_repair_worker(newly_created_entities: List[CodeEntity]):
    """A one-shot task to satisfy any 'AWAITING_TARGET' links."""
    if not newly_created_entities: return
    log_prefix = "ENHANCEMENT(Repair)"
    logger.info(f"{log_prefix}: Checking {len(newly_created_entities)} new entities against awaited links.")

    for entity in newly_created_entities:
        if not entity.canonical_fqn: continue

        repo_id_str = entity.id.split('|')[0]
        awaited_links = await find_nodes_with_filter({
            "type": "PendingLink",
            "status": LinkStatus.AWAITING_TARGET.value,
            "awaits_fqn": entity.canonical_fqn,
            "repo_id_str": repo_id_str
        })

        if awaited_links:
            logger.info(f"{log_prefix}: Found {len(awaited_links)} links waiting for FQN '{entity.canonical_fqn}'.")
            for link_node in awaited_links:
                logger.info(f"{log_prefix}: Satisfying awaited link {link_node.id} with new entity {entity.id}.")
                await _create_final_link(link_node, entity.id, ResolutionMethod.LLM, repo_id_str)
