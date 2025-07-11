# .roo/cognee/src/parser/dispatcher.py
import asyncio
from typing import Dict, List

from .utils import logger
from .configs import QUIESCENCE_PERIOD_SECONDS
from .entities import CodeEntity, LinkStatus
from .graph_enhancement_engine import (
    run_tier2_enhancement,
    run_tier3_enhancement,
    run_repair_worker,
)
# Import the new graph utils function for marking failures
from .graph_utils import find_nodes_with_filter, update_pending_link_status, mark_enhancement_failed

class IntelligentEnrichmentDispatcher:
    """
    A stateful but efficient dispatcher that triggers graph enhancement tasks
    only when a repository has been inactive for a defined period. This is the
    central conductor of the asynchronous enhancement process.
    """
    _instance = None

    def __init__(self):
        # A dictionary to keep track of the "countdown" task for each repository.
        self.watched_repos: Dict[str, asyncio.Task] = {}
        self.log_prefix = "DISPATCHER"
        logger.info(f"{self.log_prefix}: Dispatcher initialized.")

    async def _run_full_enhancement_cycle(self, repo_id_with_branch: str):
        """
        The full, orchestrated sequence of enhancement tasks for a quiescent repository.
        Includes robust error handling for failed tasks.
        """
        log_prefix = f"ENHANCEMENT_CYCLE({repo_id_with_branch})"
        logger.info(f"{log_prefix}: Starting full enhancement cycle.")

        try:
            # 1. Promote all PENDING_RESOLUTION links for this repo to READY_FOR_HEURISTICS.
            links_to_promote = await find_nodes_with_filter({
                "type": "PendingLink",
                "status": LinkStatus.PENDING_RESOLUTION.value,
                "repo_id_str": repo_id_with_branch
            })
            if links_to_promote:
                logger.info(f"{log_prefix}: Promoting {len(links_to_promote)} links to Tier 2.")
                for link_node in links_to_promote:
                    await update_pending_link_status(link_node.id, LinkStatus.READY_FOR_HEURISTICS)

            # 2. Run Tier 2 (Heuristics) and Tier 3 (LLM) enhancements concurrently.
            # return_exceptions=True prevents one failed task from stopping the others.
            enhancement_tasks = [
                run_tier2_enhancement(repo_id_with_branch),
                run_tier3_enhancement(repo_id_with_branch)
            ]
            results = await asyncio.gather(*enhancement_tasks, return_exceptions=True)

            # 3. Check for and handle any failures.
            for result in results:
                if isinstance(result, Exception):
                    logger.critical(f"{log_prefix}: An enhancement task failed. Marking cycle as FAILED.", exc_info=result)
                    # Mark the repo's heartbeat to prevent retries of the failed cycle.
                    await mark_enhancement_failed(repo_id_with_branch, str(result))
                    # We break after the first failure to avoid multiple notifications.
                    break
            else:
                 # This 'else' belongs to the 'for' loop, it runs if the loop completed without a break.
                logger.info(f"{log_prefix}: Full enhancement cycle completed successfully.")

        except Exception as e:
            # This outer block catches failures in the promotion step itself.
            logger.error(f"{log_prefix}: A critical error occurred during the enhancement cycle. Error: {e}", exc_info=True)
            await mark_enhancement_failed(repo_id_with_branch, str(e))

    async def _watch_for_quiescence(self, repo_id_with_branch: str):
        """
        The "countdown timer" for a single repository. It waits for the quiescence
        period. If it completes without being cancelled, it triggers the enhancement cycle.
        """
        try:
            logger.info(f"{self.log_prefix}: Starting quiescence watch for '{repo_id_with_branch}'. Timer: {QUIESCENCE_PERIOD_SECONDS}s.")
            await asyncio.sleep(QUIESCENCE_PERIOD_SECONDS)

            logger.info(f"{self.log_prefix}: Quiescence detected for '{repo_id_with_branch}'. Dispatching full enhancement cycle.")
            await self._run_full_enhancement_cycle(repo_id_with_branch)

        except asyncio.CancelledError:
            logger.info(f"{self.log_prefix}: Watch cancelled for '{repo_id_with_branch}'. Activity detected, timer reset.")
        finally:
            self.watched_repos.pop(repo_id_with_branch, None)

    async def notify_ingestion_activity(self, repo_id_with_branch: str, newly_created_entities: List[CodeEntity]):
        """
        The main entry point, called by the Orchestrator after every successful file ingestion.
        It starts or resets the quiescence timer and triggers the immediate repair worker.
        """
        # Immediately run the repair worker. This is fast and has its own error handling.
        await run_repair_worker(newly_created_entities)

        # Reset the quiescence timer for the repository.
        if repo_id_with_branch in self.watched_repos:
            self.watched_repos[repo_id_with_branch].cancel()

        self.watched_repos[repo_id_with_branch] = asyncio.create_task(
            self._watch_for_quiescence(repo_id_with_branch)
        )

# Singleton pattern to ensure there's only one dispatcher in the application.
_dispatcher_instance = None
def get_dispatcher() -> "IntelligentEnrichmentDispatcher":
    global _dispatcher_instance
    if _dispatcher_instance is None:
        _dispatcher_instance = IntelligentEnrichmentDispatcher()
    return _dispatcher_instance
