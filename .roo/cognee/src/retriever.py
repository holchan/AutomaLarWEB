# retriever.py
from typing import Any, Dict, List, Optional, Union, Tuple, Type
import json
import re
import time
from uuid import UUID
import asyncio
from collections import OrderedDict
import os
import hashlib

from pydantic import BaseModel, Field, ValidationError, validator

try:
    from cognee.modules.retrieval.base_retriever import BaseRetriever
    from cognee.infrastructure.databases.graph import get_graph_engine, GraphEngine, GraphDBInterface
    from cognee.infrastructure.llm.get_llm_client import get_llm_client, LLMInterface
    from cognee.infrastructure.llm.prompts.render_prompt import render_prompt
    from cognee.shared.logging_utils import get_logger

    from cognee.modules.users.models import User
    from cognee.modules.users.utils import get_default_user

    from cognee.modules.retrieval.utils.brute_force_triplet_search import brute_force_triplet_search

except ImportError as e:
    print(f"CRITICAL Error importing Cognee components: {e}")
    print("Please ensure Cognee is installed correctly and accessible in the Python environment.")
    if "brute_force_triplet_search" in str(e):
        print("Ensure 'brute_force_triplet_search' function is available for import from cognee.modules.retrieval.utils...")
    if "User" in str(e) or "get_default_user" in str(e):
         print("Ensure 'User' model and 'get_default_user' utility are available from cognee.modules.users...")
    raise

logger = get_logger(__name__)

# --- Context Cache (for Phase 1 results) ---
class ContextCache:
    """Simple in-memory cache for _run_retrieval_phase results (triplets) with TTL."""
    def __init__(self, max_size=50, ttl_seconds=600):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.access_times = {}
        logger.info(f"ContextCache initialized with max_size={max_size}, ttl={ttl_seconds}s")

    def get(self, key):
        if key not in self.cache:
            return None
        timestamp = self.access_times.get(key, 0)
        if time.time() - timestamp > self.ttl_seconds:
            logger.debug(f"Cache expired for key: {key}")
            self.remove(key)
            return None
        logger.debug(f"Cache hit for key: {key}")
        self.cache.move_to_end(key)
        # Return deep copy to prevent modifying cache
        try:
            # Attempt deep copy via JSON serialization/deserialization
            return json.loads(json.dumps(self.cache[key]))
        except TypeError:
             logger.warning(f"Could not deep copy cached item for key {key} via JSON. Returning direct reference (potential for modification).")
             # Consider using copy.deepcopy if JSON fails often, but be aware of performance/object complexity
             return self.cache[key] # Fallback, less safe

    def set(self, key, value):
        if len(self.cache) >= self.max_size and key not in self.cache:
            try:
                lru_key, _ = self.cache.popitem(last=False)
                self.remove(lru_key)
                logger.debug(f"Cache full. Removed LRU key: {lru_key}")
            except KeyError: pass # Cache might be empty or key already removed
        logger.debug(f"Setting cache for key: {key}")
        try:
            # Store deep copy via JSON
            self.cache[key] = json.loads(json.dumps(value))
            self.access_times[key] = time.time()
            self.cache.move_to_end(key)
        except TypeError:
            logger.warning(f"Could not deep copy value for cache key {key} via JSON. Storing direct reference.")
            self.cache[key] = value # Fallback, less safe
            self.access_times[key] = time.time()

    def remove(self, key):
        if key in self.cache: del self.cache[key]
        if key in self.access_times: del self.access_times[key]
        logger.debug(f"Removed cache key: {key}")

# --- Pydantic Model for LLM Planning (Index-Based) ---
class RevisedRetrievalPlan(BaseModel):
    """ Structured output from the LLM planning phase, using indices. """
    output: str = Field(..., description="LLM's analysis, chain-of-thought, or message/clarification.")
    loop: bool = Field(False, description="True if another retrieval cycle is needed.")
    search_query: Optional[str] = Field(None, description="If loop is True, the NL query for the next Phase 1 retrieval.")
    done: bool = Field(False, description="True if analysis is complete, proceed to Phase 3.")
    exit: bool = Field(False, description="True if processing should stop immediately (e.g., clarification).")
    relevant_triplet_indices: List[int] = Field(..., description="Mandatory. Zero-based indices of triplets from the input list that are relevant for the next step/summary. Empty list [] means none.")

    @validator('search_query', always=True)
    def check_search_query_if_looping(cls, v, values):
        if values.get('loop') and not v:
            raise ValueError("search_query must be provided if loop is True")
        return v

    @validator('done')
    def check_done_exclusive(cls, v, values):
        if v and (values.get('loop') or values.get('exit')):
            raise ValueError("done cannot be True if loop or exit is True")
        return v

    @validator('exit')
    def check_exit_exclusive(cls, v, values):
        if v and values.get('loop'):
             raise ValueError("exit and loop cannot both be True")
        return v

    @validator('loop', always=True)
    def check_flags_state(cls, v, values):
        if not v and not values.get('done') and not values.get('exit'):
             logger.warning("Plan has loop=False but neither done nor exit is True. Defaulting to exit=True.")
             values['exit'] = True
        return v

# --- Custom Retriever (Refactored: Graph-Centric, Index-Based Planning) ---
class DevCodeRetriever(BaseRetriever):
    """
    Developer-focused retriever using a multi-stage, graph-centric pipeline.
    Relies on Cognee's `brute_force_triplet_search` to find relevant triplets.
    Uses LLM for analysis and planning (selecting relevant triplet indices),
    and final synthesis.

    ASSUMPTIONS:
    - Graph nodes store text chunk content in the 'text' attribute.
    - `brute_force_triplet_search` is available and returns triplets with node/edge details.
    - Canonical Node ID Format: 'path/to/file:entityName' used for node IDs.
    - ':' Separator: Not used in file paths or entity names.
    - LLM used supports structured output (Pydantic models).
    - `_map_datasets_to_graph_collections` method is implemented correctly.
    """

    def __init__(
        self,
        # --- Prompt template paths ---
        analysis_system_prompt_path: str = "prompts/dev_code_analysis_system.txt",
        analysis_user_prompt_path: str = "prompts/dev_code_analysis_user.txt",
        summary_system_prompt_path: str = "prompts/dev_code_summary_system.txt",
        summary_user_prompt_path: str = "prompts/dev_code_summary_user.txt",

        # --- Retrieval Configuration ---
        phase1_top_k: int = 20, # Number of triplets from brute_force_search
        node_properties_to_project: List[str] = [ # Default properties for nodes
            "id", "text", "type", "name", "source_file",
            "start_line", "end_line", "timestamp", "dataset_path"
        ],
        edge_properties_to_project: List[str] = [ # Default properties for edges
            "relationship_type", "timestamp", "dataset_path"
        ],
        max_llm_context_triplets: int = 15, # Max triplets to format for LLM prompt
        max_final_context_triplets: int = 20, # Max triplets in final output context

        # --- Canonical Schema Properties (Must match graph data) ---
        node_id_prop: str = "id",
        node_text_prop: str = "text", # Assumed property holding chunk text
        node_type_prop: str = "type",
        node_timestamp_prop: str = "timestamp",
        node_dataset_path_prop: str = "dataset_path", # Assumed node property for scoping
        edge_type_prop: str = "relationship_type", # Assumed property in edge attributes
        edge_timestamp_prop: str = "timestamp",

        # --- LLM & Loop Control ---
        max_planning_retries: int = 2, # Reduced default, can be tuned

        # --- Cache Configuration ---
        cache_max_size: int = 50,
        cache_ttl_seconds: int = 600,
        type_cache_max_size: int = 100,
        type_cache_ttl_seconds: int = 3600, # 1 hour for schema types
    ):
        # Store config
        self.analysis_system_prompt_path = analysis_system_prompt_path
        self.analysis_user_prompt_path = analysis_user_prompt_path
        self.summary_system_prompt_path = summary_system_prompt_path
        self.summary_user_prompt_path = summary_user_prompt_path

        self.phase1_top_k = phase1_top_k
        # Ensure 'id' and key props are always projected for internal logic
        self.node_properties_to_project = sorted(list(set([
            node_id_prop, node_text_prop, node_type_prop, node_dataset_path_prop, node_timestamp_prop
            ] + node_properties_to_project)))
        self.edge_properties_to_project = sorted(list(set([
             edge_type_prop, edge_timestamp_prop # Assuming edge dataset path comes from nodes
            ] + edge_properties_to_project)))
        self.max_llm_context_triplets = max_llm_context_triplets
        self.max_final_context_triplets = max_final_context_triplets

        # Store Canonical Schema Properties
        self.node_id_prop = node_id_prop
        self.node_text_prop = node_text_prop
        self.node_type_prop = node_type_prop
        self.node_timestamp_prop = node_timestamp_prop
        self.node_dataset_path_prop = node_dataset_path_prop
        self.edge_type_prop = edge_type_prop
        self.edge_timestamp_prop = edge_timestamp_prop

        self.max_planning_retries = max_planning_retries

        # Initialize Caches
        self.context_cache = ContextCache(max_size=cache_max_size, ttl_seconds=cache_ttl_seconds)
        self.type_vocabulary_cache = OrderedDict() # Cache for dynamic schema types
        self.type_cache_max_size = type_cache_max_size
        self.type_cache_ttl_seconds = type_cache_ttl_seconds

        logger.info("DevCodeRetriever initialized (Graph-Centric, Index-Based Planning).")
        logger.info(f" Phase 1 Search: Using 'brute_force_triplet_search', top_k={self.phase1_top_k}")
        logger.info(f" Node Properties Projected: {self.node_properties_to_project}")
        logger.info(f" Edge Properties Projected: {self.edge_properties_to_project}")
        logger.info(f" Assumed Node Text Property: '{self.node_text_prop}'")
        logger.info(f" Assumed Node Dataset Property: '{self.node_dataset_path_prop}'")


    # --- Core Orchestration ---
    async def get_completion(
        self,
        query: str,
        user: Optional[User] = None, # Accept optional User object
        datasets: List[str] = None,  # List of dataset identifiers for scoping
    ) -> Dict[str, Any]:
        """
        Orchestrates the multi-stage, graph-centric retrieval pipeline.

        Args:
            query: The user's natural language query.
            user: The User object for potential scoping (optional, defaults to default user).
            datasets: List of dataset identifiers (e.g., repo names, project IDs)
                      used to scope the graph search. Mandatory.

        Returns:
            A dictionary containing the LLM's output and the relevant context triplets.
            Format: { "output": str, "relevant_context": List[Dict] }
            On error or exit: { "output": str, "relevant_context": List[Dict], "status": str }
        """
        trace = [] # Optional tracing
        start_time = time.time()

        if not datasets:
            logger.error("No datasets provided to get_completion.")
            return {"output": "Error: Retrieval requires specific dataset paths.", "relevant_context": [], "status": "error_missing_datasets"}

        if user is None:
            user = await get_default_user()

        logger.info(f"Starting get_completion for query: '{query}'")
        logger.info(f" User: {user.id}, Datasets Scope: {datasets}")

        current_triplets: List[Dict] = []
        plan: Optional[RevisedRetrievalPlan] = None
        original_query = query

        try:
            # --- Initial Phase 1 Run ---
            stage_start_time = time.time()
            trace.append({"stage": "initial_retrieval", "status": "started"})
            logger.info("Running initial retrieval phase...")

            cache_key_parts = [query] + sorted(datasets) + [str(user.id)] # Include user ID in cache key
            cache_key = f"phase1:{hashlib.sha256('|'.join(cache_key_parts).encode()).hexdigest()}"
            cached_triplets = self.context_cache.get(cache_key)

            if cached_triplets is not None:
                initial_triplets = cached_triplets
                logger.info(f"Retrieved initial triplets from cache ({len(initial_triplets)} items).")
                trace[-1].update({"status": "completed", "source": "cache", "duration": time.time() - stage_start_time, "triplet_count": len(initial_triplets)})
            else:
                initial_triplets = await self._run_retrieval_phase(original_query, user, datasets)
                if initial_triplets:
                    self.context_cache.set(cache_key, initial_triplets)
                logger.info(f"Initial retrieval phase completed ({len(initial_triplets)} triplets found).")
                trace[-1].update({"status": "completed", "source": "new", "duration": time.time() - stage_start_time, "triplet_count": len(initial_triplets)})

            if not initial_triplets:
                logger.warning(f"No relevant triplets found for query: {query}")
                return {"output": f"No relevant results found for query: '{query}'", "relevant_context": [], "status": "no_results"}

            current_triplets = initial_triplets

            # --- Phase 2: Planning Loop ---
            for retry_count in range(self.max_planning_retries + 1):
                is_last_attempt = retry_count == self.max_planning_retries
                stage_start_time = time.time()
                plan_stage_name = f"analysis_planning_attempt_{retry_count + 1}"
                trace.append({"stage": plan_stage_name, "status": "started", "triplet_input_count": len(current_triplets)})
                logger.info(f"Running analysis/planning (Attempt {retry_count + 1}/{self.max_planning_retries + 1})")

                # Ensure context isn't empty before planning
                if not current_triplets and not is_last_attempt:
                     logger.warning("Planning phase entered with empty context. Exiting loop.")
                     # Treat as if no results were found initially
                     return {"output": f"Analysis stopped due to lack of relevant context after loops for query: '{query}'", "relevant_context": [], "status": "no_results_post_loop"}


                plan = await self._analyze_and_plan(original_query, current_triplets, datasets)
                trace[-1].update({"status": "completed", "duration": time.time() - stage_start_time, "plan_details": plan.dict()})

                # --- Process Plan Flags ---
                if plan.exit:
                    logger.info(f"LLM requested exit: {plan.output}")
                    # Prepare context based on the indices selected just before exiting
                    # Use empty list [] for new_triplets as we are not fetching new ones on exit
                    final_context_triplets = await self._prepare_context_for_llm(current_triplets, [], plan.relevant_triplet_indices)
                    cleaned_context = self._clean_triplets_for_output(final_context_triplets)
                    status = "exit_clarification" if "clarification" in plan.output.lower() else "exit_suggestion"
                    return {"output": plan.output, "relevant_context": cleaned_context, "status": status, "trace": trace}

                if plan.loop and not is_last_attempt:
                    logger.info(f"LLM requested loop with new query: '{plan.search_query}'")
                    # Run Phase 1 again with the new query
                    loop_stage_start = time.time()
                    loop_stage_name = f"loop_retrieval_attempt_{retry_count + 1}"
                    trace.append({"stage": loop_stage_name, "status": "started"})
                    logger.info(f"Running loop retrieval phase (query: '{plan.search_query}')...")
                    new_triplets = await self._run_retrieval_phase(plan.search_query, user, datasets)
                    trace[-1].update({"status": "completed", "duration": time.time() - loop_stage_start, "triplet_count": len(new_triplets)})
                    logger.info(f"Loop retrieval phase completed ({len(new_triplets)} new triplets found).")

                    # Prepare context for the *next* planning iteration
                    prep_stage_start = time.time()
                    prep_stage_name = f"loop_context_prep_attempt_{retry_count + 1}"
                    trace.append({"stage": prep_stage_name, "status": "started"})
                    current_triplets = await self._prepare_context_for_llm(current_triplets, new_triplets, plan.relevant_triplet_indices)
                    trace[-1].update({"status": "completed", "duration": time.time() - prep_stage_start, "final_triplet_count": len(current_triplets)})
                    logger.info(f"Context prepared for next loop ({len(current_triplets)} triplets).")
                    continue # Go to the next iteration of the planning loop

                # Proceed to Phase 3 if done=True OR if it's the last attempt (even if loop=True was set)
                if plan.done or is_last_attempt:
                    if is_last_attempt and not plan.done:
                         logger.warning(f"Max planning retries ({self.max_planning_retries}) reached. Proceeding to final summary.")
                         if plan.output: plan.output += "\n(Note: Max planning retries reached)"
                         else: plan.output = "(Note: Max planning retries reached)"

                    logger.info("Planning complete or max retries reached. Proceeding to Phase 3.")
                    # Prepare final context based on the last plan's indices
                    prep_stage_start = time.time()
                    prep_stage_name = "final_context_prep"
                    trace.append({"stage": prep_stage_name, "status": "started"})
                    # Use empty list [] for new_triplets as we are finalizing
                    final_triplets = await self._prepare_context_for_llm(current_triplets, [], plan.relevant_triplet_indices)
                    trace[-1].update({"status": "completed", "duration": time.time() - prep_stage_start, "final_triplet_count": len(final_triplets)})
                    logger.info(f"Final context prepared ({len(final_triplets)} triplets).")

                     # Check if final context is empty before generating summary
                    if not final_triplets:
                        logger.warning(f"No relevant triplets selected for final summary for query: {query}")
                        return {"output": f"No relevant context remained after analysis for query: '{query}'\nAnalysis notes: {plan.output}", "relevant_context": [], "status": "no_results_final"}


                    # --- Phase 3: Generate Final Summary ---
                    stage_start_time = time.time()
                    trace.append({"stage": "final_summary_generation", "status": "started"})
                    final_response = await self._generate_comprehensive_response(
                        original_query, plan.output, final_triplets
                    )
                    trace[-1].update({"status": "completed", "duration": time.time() - stage_start_time})
                    final_response["trace"] = trace # Add trace to final output
                    logger.info(f"get_completion finished in {time.time() - start_time:.2f} seconds.")
                    return final_response

                # Fallback if plan state is somehow invalid
                logger.error(f"Invalid plan state encountered: {plan.dict()}. Aborting.")
                return {"output": "Error: Internal planning state invalid.", "relevant_context": [], "status": "error_internal_plan", "trace": trace}

            # This part should not be reached if the loop logic is correct
            logger.error("Reached end of get_completion loop unexpectedly.")
            return {"output": "Error: Unexpected loop termination.", "relevant_context": [], "status": "error_internal_loop", "trace": trace}

        except Exception as e:
            logger.exception(f"Critical error during get_completion for query '{query}': {str(e)}")
            cleaned_context = self._clean_triplets_for_output(current_triplets[:self.max_final_context_triplets])
            return {"output": f"An error occurred: {str(e)}", "relevant_context": cleaned_context, "status": "error_exception", "trace": trace}


    # --- Phase 1: Retrieval ---
    async def _run_retrieval_phase(self, query: str, user: User, datasets: List[str]) -> List[Dict]:
        """
        Runs the graph-based semantic search using Cognee's brute_force_triplet_search.
        """
        logger.info(f"Executing graph search for query: '{query[:100]}...'")
        start_time = time.time()

        # Map datasets to graph collections/labels
        graph_collections = self._map_datasets_to_graph_collections(datasets)
        if not graph_collections:
             logger.warning(f"Could not map datasets {datasets} to any graph collections. Attempting search with default collections.")
             # Let brute_force_triplet_search use its internal defaults if graph_collections is None
             graph_collections = None

        # Combine node and edge properties needed
        properties_to_request = list(set(self.node_properties_to_project + self.edge_properties_to_project))

        try:
            # Use the imported brute_force_triplet_search function
            raw_triplets = await brute_force_triplet_search(
                query=query,
                user=user,
                top_k=self.phase1_top_k,
                collections=graph_collections,
                properties_to_project=properties_to_request
            )

            processed_triplets = []
            if raw_triplets:
                logger.debug(f"brute_force_triplet_search returned {len(raw_triplets)} raw triplets.")
                for i, triplet in enumerate(raw_triplets):
                    # Perform validation - ensure nodes/edges and required attributes exist
                    if self._validate_triplet_structure(triplet):
                        # Add original index for potential debugging if needed
                        # triplet['_original_index'] = i
                        processed_triplets.append(triplet)
                    else:
                         logger.warning(f"Skipping invalid/incomplete triplet structure at index {i}: Score={triplet.get('score', 'N/A')}")
                         logger.debug(f"Invalid Triplet Detail: {triplet}")


            duration = time.time() - start_time
            logger.info(f"Graph search completed in {duration:.2f}s, yielded {len(processed_triplets)} processed triplets.")
            return processed_triplets

        except Exception as e:
            # Catch specific errors from brute_force_search if possible
            logger.exception(f"Error during _run_retrieval_phase calling brute_force_triplet_search: {e}")
            return []

    # --- Phase 2: LLM Planning ---
    async def _analyze_and_plan(self, original_query: str, current_triplets: List[Dict], datasets: List[str]) -> RevisedRetrievalPlan:
        """
        Analyzes the current triplets and generates a plan using the LLM.
        """
        logger.info(f"Analyzing {len(current_triplets)} triplets for planning...")
        llm_client = get_llm_client()

        # Limit triplets sent to LLM
        triplets_for_llm = current_triplets[:self.max_llm_context_triplets]
        if not triplets_for_llm:
             logger.warning("Analysis phase received no triplets. Generating exit plan.")
             return RevisedRetrievalPlan(output="No relevant information found to analyze.", exit=True, relevant_triplet_indices=[])


        # Get dynamic schema types from the current context
        dynamic_types = self._get_dynamic_types_from_triplets(triplets_for_llm)
        available_node_types = sorted(list(dynamic_types.get("node_types", [])))
        available_edge_types = sorted(list(dynamic_types.get("edge_types", [])))
        logger.debug(f"Context Node Types for LLM: {available_node_types}")
        logger.debug(f"Context Edge Types for LLM: {available_edge_types}")

        # Format triplets for the LLM prompt
        formatted_triplets_for_prompt = self._format_triplets_for_llm(triplets_for_llm)

        prompt_context = {
            "original_query": original_query,
            # Pass triplets as JSON string within the prompt context
            "current_triplets_json": json.dumps(formatted_triplets_for_prompt, indent=2),
            "triplet_input_count": len(triplets_for_llm), # Let LLM know how many it received
            "total_triplet_count": len(current_triplets), # Let LLM know total available
            "available_node_types": ", ".join(available_node_types) or "N/A",
            "available_edge_types": ", ".join(available_edge_types) or "N/A",
        }

        try:
            system_prompt = await render_prompt(self.analysis_system_prompt_path, prompt_context)
            user_prompt = await render_prompt(self.analysis_user_prompt_path, prompt_context)
        except Exception as e:
            logger.error(f"Error rendering analysis prompts: {e}")
            system_prompt = "You are a code analysis planner. Analyze the query and the provided triplets (JSON format). Decide to loop (provide search_query), finish (done=True), or exit. Output a JSON matching the RevisedRetrievalPlan model, including relevant_triplet_indices."
            user_prompt = f"Query: {original_query}\n\nTriplets:\n{json.dumps(formatted_triplets_for_prompt, indent=2)}\n\nBased on the query and triplets, determine the next step (loop, done, exit) and select the indices of relevant triplets."

        try:
            # Specify model if needed, or rely on client default
            # model_name = "gpt-4-turbo-preview"
            plan = await llm_client.acreate_structured_output(
                # model_name = model_name,
                user_prompt=user_prompt,
                system_prompt=system_prompt,
                response_model=RevisedRetrievalPlan
            )
            logger.info("Analysis plan generated successfully.")
            logger.debug(f"Plan details: {plan.dict()}")

            # Validate indices
            max_index = len(triplets_for_llm) - 1
            valid_indices = [idx for idx in plan.relevant_triplet_indices if 0 <= idx <= max_index]
            if len(valid_indices) != len(plan.relevant_triplet_indices):
                logger.warning(f"LLM returned invalid indices. Original: {plan.relevant_triplet_indices}, Validated: {valid_indices}")
                plan.relevant_triplet_indices = valid_indices

            return plan

        except ValidationError as e:
            logger.error(f"LLM output failed Pydantic validation for RevisedRetrievalPlan: {e}")
            return RevisedRetrievalPlan(output=f"LLM output validation failed: {e}", exit=True, relevant_triplet_indices=[])
        except Exception as e:
            logger.exception(f"LLM error during planning phase: {e}")
            return RevisedRetrievalPlan(output=f"LLM call failed during planning: {e}", exit=True, relevant_triplet_indices=[])

    # --- Phase 3: LLM Summarization ---
    async def _generate_comprehensive_response(
        self,
        original_query: str,
        analysis_output: str,
        final_triplets: List[Dict]
    ) -> Dict[str, Any]:
        """
        Generates the final unstructured summary using the LLM based on final triplets.
        """
        logger.info(f"Generating final summary based on {len(final_triplets)} triplets.")
        llm_client = get_llm_client()

        # Format final triplets for the LLM prompt, limiting context size
        triplets_for_summary_prompt = final_triplets[:self.max_llm_context_triplets]
        formatted_triplets = self._format_triplets_for_llm(triplets_for_summary_prompt) # Use same formatter

        prompt_context = {
            "original_query": original_query,
            "analysis_notes": analysis_output,
            "final_triplets_json": json.dumps(formatted_triplets, indent=2),
        }

        try:
            system_prompt = await render_prompt(self.summary_system_prompt_path, prompt_context)
            user_prompt = await render_prompt(self.summary_user_prompt_path, prompt_context)
        except Exception as e:
            logger.error(f"Error rendering summary prompts: {e}")
            system_prompt = "You are a helpful code assistant. Summarize the findings based ONLY on the provided context."
            user_prompt = f"Original Query: {original_query}\nAnalysis Notes: {analysis_output}\n\nRelevant Context (Triplets):\n{json.dumps(formatted_triplets, indent=2)}\n\nProvide a comprehensive summary based on the information above."

        try:
            # model_name = "gpt-4-turbo-preview"
            llm_summary = await llm_client.acreate(
                # model_name=model_name,
                user_prompt=user_prompt,
                system_prompt=system_prompt,
            )
            logger.info("Final summary generated successfully.")

            # Clean the final triplets for the output context (use full final list before limiting for prompt)
            cleaned_triplets = self._clean_triplets_for_output(final_triplets[:self.max_final_context_triplets]) # Limit output

            return {
                "output": llm_summary.strip(),
                "relevant_context": cleaned_triplets
            }

        except Exception as e:
            logger.exception(f"LLM error during summary phase: {e}")
            cleaned_triplets = self._clean_triplets_for_output(final_triplets[:self.max_final_context_triplets])
            fallback_output = f"Error generating summary: {e}\n\nAnalysis Notes:\n{analysis_output}\n\nBased on {len(cleaned_triplets)} relevant items."
            return {
                "output": fallback_output,
                "relevant_context": cleaned_triplets,
                "status": "error_summary_generation"
            }

    # --- Context Preparation & Helper Functions ---

    async def _prepare_context_for_llm(
        self,
        previous_triplets: List[Dict],
        new_triplets: List[Dict],
        relevant_indices: List[int]
    ) -> List[Dict]:
        """
        Selects relevant previous triplets by index, combines with new ones,
        deduplicates, and returns the prepared list sorted by score.
        Assumes input triplets have necessary data loaded.
        """
        logger.debug(f"Preparing context. Previous: {len(previous_triplets)}, New: {len(new_triplets)}, Indices: {relevant_indices}")

        selected_triplets = []
        if previous_triplets and relevant_indices:
            max_idx = len(previous_triplets) - 1
            selected_triplets = [previous_triplets[i] for i in relevant_indices if 0 <= i <= max_idx]
            logger.debug(f"Selected {len(selected_triplets)} triplets from previous context based on indices.")

        combined_triplets = selected_triplets + new_triplets
        logger.debug(f"Combined triplets count before deduplication: {len(combined_triplets)}")

        # Deduplicate based on a unique triplet identifier (source_id:edge_type:target_id)
        deduplicated_triplets_dict = OrderedDict()
        for triplet in combined_triplets:
            try:
                # Handle potential missing keys gracefully
                source_id = triplet.get("source_node", {}).get("id")
                target_id = triplet.get("target_node", {}).get("id")
                edge_type = triplet.get("edge", {}).get("attributes", {}).get(self.edge_type_prop)

                if not all([source_id, target_id, edge_type]):
                    logger.warning(f"Skipping triplet during deduplication due to missing ID/Type. Triplet Score: {triplet.get('score')}")
                    continue

                key_str = f"{source_id}:{edge_type}:{target_id}"
                key = hashlib.sha256(key_str.encode()).hexdigest()

                existing = deduplicated_triplets_dict.get(key)
                current_score = triplet.get("score", 0) # Default score to 0 if missing

                # Keep the one with the highest score
                if not existing or current_score > existing.get("score", 0):
                    deduplicated_triplets_dict[key] = triplet
            except Exception as e:
                 logger.warning(f"Error creating key for triplet during deduplication: {e}. Triplet: {triplet}")

        deduplicated_triplets = list(deduplicated_triplets_dict.values())
        logger.debug(f"Deduplicated triplets count: {len(deduplicated_triplets)}")

        # Sort by score (descending) before returning
        final_prepared_triplets = sorted(deduplicated_triplets, key=lambda t: t.get("score", 0), reverse=True)

        logger.info(f"Context preparation complete. Returning {len(final_prepared_triplets)} triplets.")
        return final_prepared_triplets

    def _format_triplets_for_llm(self, triplets: List[Dict]) -> List[Dict]:
        """ Formats triplets into a JSON-serializable structure for the LLM prompt. """
        formatted = []
        for i, triplet in enumerate(triplets):
            try:
                source_node = triplet.get("source_node", {})
                edge = triplet.get("edge", {})
                target_node = triplet.get("target_node", {})

                source_attrs = source_node.get("attributes", {})
                edge_attrs = edge.get("attributes", {})
                target_attrs = target_node.get("attributes", {})

                # Ensure required props are present, default to None if missing
                source_id = source_node.get(self.node_id_prop)
                source_type = source_attrs.get(self.node_type_prop)
                source_name = source_attrs.get("name")
                source_text = source_attrs.get(self.node_text_prop)

                edge_type = edge_attrs.get(self.edge_type_prop)

                target_id = target_node.get(self.node_id_prop)
                target_type = target_attrs.get(self.node_type_prop)
                target_name = target_attrs.get("name")
                target_text = target_attrs.get(self.node_text_prop)

                # Basic check
                if not all([source_id, edge_type, target_id]):
                     logger.warning(f"Skipping triplet formatting due to missing core IDs/type at index {i}")
                     continue

                formatted_triplet = {
                    "index": i, # Crucial for relevant_triplet_indices
                    "score": round(triplet.get("score", 0), 3),
                    "source": {
                        "id": source_id,
                        "type": source_type,
                        "name": source_name,
                        "text_snippet": self._extract_relevant_snippet(source_text, 5), # Short snippet for LLM
                    },
                    "edge": {
                        "type": edge_type,
                    },
                    "target": {
                        "id": target_id,
                        "type": target_type,
                        "name": target_name,
                        "text_snippet": self._extract_relevant_snippet(target_text, 5),
                    }
                }
                # Clean out None values from inner dicts for cleaner JSON
                formatted["source"] = {k: v for k, v in formatted["source"].items() if v is not None}
                formatted["edge"] = {k: v for k, v in formatted["edge"].items() if v is not None}
                formatted["target"] = {k: v for k, v in formatted["target"].items() if v is not None}

                formatted.append(formatted_triplet)
            except Exception as e:
                logger.warning(f"Error formatting triplet index {i} for LLM: {e}. Triplet: {triplet}")
        return formatted

    def _clean_triplets_for_output(self, triplets: List[Dict]) -> List[Dict]:
        """ Cleans the final list of triplets for the user-facing API response. """
        cleaned = []
        for triplet in triplets:
             try:
                source_node = triplet.get("source_node", {})
                edge = triplet.get("edge", {})
                target_node = triplet.get("target_node", {})

                source_attrs = source_node.get("attributes", {})
                edge_attrs = edge.get("attributes", {})
                target_attrs = target_node.get("attributes", {})

                # Ensure required props are present
                source_id = source_node.get(self.node_id_prop)
                target_id = target_node.get(self.node_id_prop)
                edge_type = edge_attrs.get(self.edge_type_prop)

                if not all([source_id, target_id, edge_type]):
                     logger.warning(f"Skipping triplet cleaning due to missing core IDs/type. Score: {triplet.get('score')}")
                     continue

                source_path, source_name = self._parse_node_id(source_id)
                target_path, target_name = self._parse_node_id(target_id)

                # Select properties to expose
                cleaned_triplet = {
                    "score": round(triplet.get("score", 0), 3),
                    "source_node": {
                        "id": source_id,
                        "type": source_attrs.get(self.node_type_prop),
                        "name": source_name or source_attrs.get("name"), # Prefer parsed name
                        "file_path": source_path,
                        "text_snippet": self._extract_relevant_snippet(source_attrs.get(self.node_text_prop,""), 10), # Longer snippet
                        "timestamp": source_attrs.get(self.node_timestamp_prop),
                        "dataset_path": source_attrs.get(self.node_dataset_path_prop),
                        "start_line": source_attrs.get("start_line"), # Include lines if available
                        "end_line": source_attrs.get("end_line"),
                    },
                    "edge": {
                        "type": edge_type,
                        "timestamp": edge_attrs.get(self.edge_timestamp_prop),
                        # "dataset_path": edge_attrs.get(self.node_dataset_path_prop), # Usually get from nodes
                    },
                    "target_node": {
                        "id": target_id,
                        "type": target_attrs.get(self.node_type_prop),
                        "name": target_name or target_attrs.get("name"),
                        "file_path": target_path,
                        "text_snippet": self._extract_relevant_snippet(target_attrs.get(self.node_text_prop,""), 10),
                        "timestamp": target_attrs.get(self.node_timestamp_prop),
                        "dataset_path": target_attrs.get(self.node_dataset_path_prop),
                        "start_line": target_attrs.get("start_line"),
                        "end_line": target_attrs.get("end_line"),
                    }
                }
                # Clean None values from inner dicts
                cleaned_triplet["source_node"] = {k: v for k, v in cleaned_triplet["source_node"].items() if v is not None}
                cleaned_triplet["edge"] = {k: v for k, v in cleaned_triplet["edge"].items() if v is not None}
                cleaned_triplet["target_node"] = {k: v for k, v in cleaned_triplet["target_node"].items() if v is not None}

                cleaned.append(cleaned_triplet)

             except Exception as e:
                  logger.warning(f"Error cleaning triplet for output: {e}. Triplet: {triplet}")
        return cleaned

    def _validate_triplet_structure(self, triplet: Any) -> bool:
        """ Validates the structure and presence of key fields in a triplet dict. """
        try:
            if not isinstance(triplet, dict): return False
            if not all(k in triplet for k in ["source_node", "edge", "target_node"]): return False

            source_node = triplet["source_node"]
            edge = triplet["edge"]
            target_node = triplet["target_node"]

            if not isinstance(source_node, dict) or not isinstance(edge, dict) or not isinstance(target_node, dict): return False

            # Check node structure
            if self.node_id_prop not in source_node or self.node_id_prop not in target_node: return False
            if "attributes" not in source_node or "attributes" not in target_node: return False
            if not isinstance(source_node["attributes"], dict) or not isinstance(target_node["attributes"], dict): return False

            # Check edge structure
            if "attributes" not in edge or not isinstance(edge["attributes"], dict): return False

            # Check presence of essential attributes used later
            if self.node_text_prop not in source_node["attributes"]: return False
            if self.node_text_prop not in target_node["attributes"]: return False
            if self.edge_type_prop not in edge["attributes"]: return False

            return True
        except Exception as e:
             logger.error(f"Exception during triplet validation: {e}")
             return False


    def _map_datasets_to_graph_collections(self, datasets: List[str]) -> Optional[List[str]]:
        """
        Maps logical dataset identifiers to graph collection names/labels.
        *** IMPLEMENTATION REQUIRED based on indexing strategy. ***
        Example assumes hierarchical naming convention like 'tenant_role_dataset'.
        """
        if not datasets:
            logger.warning("No datasets provided for mapping to graph collections.")
            return None # Or return default graph collections if applicable

        collections = set()
        # Example: Map "tenant/role/repo_name" -> ["tenant_role_repo_name", "tenant_repo_name", "tenant"]
        for d in datasets:
            parts = d.strip('/').split('/')
            if len(parts) == 3:
                tenant, role, dataset_name = parts
                collections.add(f"{tenant}_{role}_{dataset_name}")
                collections.add(f"{tenant}_{dataset_name}")
                collections.add(tenant)
            elif len(parts) == 2:
                 tenant, dataset_name = parts
                 collections.add(f"{tenant}_{dataset_name}")
                 collections.add(tenant)
            elif len(parts) == 1:
                 collections.add(parts[0]) # Assume it's tenant or dataset name directly
            else:
                 logger.warning(f"Unsupported dataset format for collection mapping: {d}. Skipping.")

        unique_collections = sorted(list(collections))
        if not unique_collections:
             logger.error(f"Failed to map datasets {datasets} to any valid graph collections.")
             return None

        logger.debug(f"Mapped datasets {datasets} to graph collections: {unique_collections}")
        return unique_collections


    def _get_dynamic_types_from_triplets(self, triplets: List[Dict]) -> Dict[str, List[str]]:
        """ Extracts distinct node and edge types present in the current triplet list. """
        node_types = set()
        edge_types = set()
        for triplet in triplets:
            try:
                # Add types if they exist and are not None
                st = triplet.get("source_node", {}).get("attributes", {}).get(self.node_type_prop)
                tt = triplet.get("target_node", {}).get("attributes", {}).get(self.node_type_prop)
                et = triplet.get("edge", {}).get("attributes", {}).get(self.edge_type_prop)
                if st: node_types.add(st)
                if tt: node_types.add(tt)
                if et: edge_types.add(et)
            except Exception as e:
                logger.warning(f"Error extracting types from triplet: {e}")
                continue

        return {"node_types": sorted(list(node_types)), "edge_types": sorted(list(edge_types))}

    def _extract_relevant_snippet(self, full_text: Optional[str], max_lines: int = 5) -> Optional[str]:
        """ Extracts a short snippet from the start of the text. """
        if not full_text or not isinstance(full_text, str):
            return None
        lines = full_text.splitlines()
        if not lines:
            return "" # Return empty string if text exists but has no lines after split
        snippet_lines = lines[:max_lines]
        snippet = "\n".join(snippet_lines)
        # Add ellipsis only if there were more lines than max_lines
        if len(lines) > max_lines:
            # Check if snippet already ends with ellipsis to avoid double ellipsis
            if not snippet.rstrip().endswith("..."):
                 snippet += "\n..."
        return snippet

    # --- Canonical ID Parsing Helper ---
    def _parse_node_id(self, node_id: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        """ Parses 'path/to/file:entityName' into (path, name). """
        if not node_id or not isinstance(node_id, str) or ":" not in node_id:
            return None, None
        try:
            path, name = node_id.rsplit(":", 1)
            return path if path else None, name if name else None
        except Exception:
            return None, None

    # --- Type Vocabulary Cache (Example - Adapt if needed) ---
    # This function is kept from the previous version but might need adaptation
    # if you want schema types beyond just what's in the current triplets.
    # If _get_dynamic_types_from_triplets is sufficient, this can be removed.
    async def _get_dynamic_type_vocabulary(self, datasets: List[str], graph_engine: GraphEngine) -> Dict[str, List[str]]:
        """ Fetches distinct node and edge types from the graph DB, scoped by dataset paths. """
        if not datasets: return {"node_types": [], "edge_types": []}

        # Generate cache key based on sorted datasets
        cache_key = "schema_vocab:" + ",".join(sorted(datasets))

        # Check cache
        cached_data = self.type_vocabulary_cache.get(cache_key)
        if cached_data:
            cached_vocab, timestamp = cached_data
            if time.time() - timestamp < self.type_cache_ttl_seconds:
                logger.debug(f"Schema type vocabulary cache hit for datasets: {datasets}")
                # self.type_vocabulary_cache.move_to_end(cache_key) # Handled by OrderedDict if using it directly
                return cached_vocab
            else:
                logger.debug(f"Schema type vocabulary cache expired for datasets: {datasets}")
                # Remove expired entry (assuming type_vocabulary_cache is dict-like)
                if cache_key in self.type_vocabulary_cache: del self.type_vocabulary_cache[cache_key]


        logger.debug(f"Schema type vocabulary cache miss or expired. Querying graph for datasets: {datasets}")

        node_types, edge_types = set(), set()
        try:
            # *** This requires graph engine methods to get schema based on datasets ***
            # Example using Cypher (adjust property names and logic as needed)
            # This assumes nodes have a dataset_path property matching the input datasets
            # If brute_force_search collections already handle scoping, this might be simpler.

            graph_collections = self._map_datasets_to_graph_collections(datasets)
            if not graph_collections: # Or handle based on how your graph scopes data
                logger.warning("Cannot get schema vocabulary without mapped graph collections.")
                return {"node_types": [], "edge_types": []}

            # Placeholder: Assumes graph_engine has methods or runs Cypher scoped by collections/datasets
            # Replace with actual Cognee graph engine schema methods if available
            # Example Cypher queries:
            params = {"collections": graph_collections} # Assuming collections map to labels or indexed property
            node_cypher = f"""
                MATCH (n) WHERE n.`{self.node_dataset_path_prop}` IN $collections // Adjust filter as needed
                AND n.`{self.node_type_prop}` IS NOT NULL
                RETURN DISTINCT n.`{self.node_type_prop}` AS nodeType LIMIT 50
            """
            edge_cypher = f"""
                 MATCH (n)-[r]->(m) WHERE n.`{self.node_dataset_path_prop}` IN $collections // Adjust filter as needed
                 AND r.`{self.edge_type_prop}` IS NOT NULL
                 RETURN DISTINCT r.`{self.edge_type_prop}` AS edgeType LIMIT 50
             """
            # Note: Using graph_engine.execute_query might be needed if direct methods aren't available
            # node_result = await graph_engine.execute_query(node_cypher, params)
            # edge_result = await graph_engine.execute_query(edge_cypher, params)

            # *** Replace below with actual result processing ***
            # Dummy data for now:
            await asyncio.sleep(0.1) # Simulate query
            node_types = {"FUNCTION", "CLASS", "CHUNK", "FILE"}
            edge_types = {"CALLS", "DEFINES", "HAS_CHUNK", "IMPORTS"}


        except Exception as e:
            logger.exception(f"Failed to query dynamic schema type vocabulary: {e}")
            return {"node_types": [], "edge_types": []} # Return empty on error

        vocabulary = {"node_types": sorted(list(node_types)), "edge_types": sorted(list(edge_types))}

        # Update cache (Simple dictionary cache example)
        if len(self.type_vocabulary_cache) >= self.type_cache_max_size:
            # Basic FIFO eviction if using a standard dict
            first_key = next(iter(self.type_vocabulary_cache))
            del self.type_vocabulary_cache[first_key]
            logger.debug(f"Schema type cache full. Removed oldest key: {first_key}")
        self.type_vocabulary_cache[cache_key] = (vocabulary, time.time())
        logger.debug(f"Stored schema type vocabulary in cache for key: {cache_key}")

        return vocabulary


    # --- Placeholder detail fetching (if needed, depends on brute_force_search) ---
    # Keep these as placeholders; only implement if brute_force_search doesn't
    # return sufficient detail in its triplet dictionaries.
    async def _get_node_details(self, node_id: str, graph_engine: GraphEngine) -> Optional[Dict]:
         """ Placeholder: Fetches full node details if not provided by brute_force_search. """
         logger.warning(f"_get_node_details called for {node_id}. Ensure brute_force_search provides needed properties.")
         # Example:
         # try:
         #     node_data = await graph_engine.get_node(node_id) # Assumes method exists
         #     return node_data # Return whatever the graph engine provides
         # except Exception as e:
         #     logger.error(f"Failed to get node details for {node_id}: {e}")
         #     return None
         return None

    async def _get_edge_details(self, triplet_str: str, graph_engine: GraphEngine) -> Optional[Dict]:
         """ Placeholder: Fetches full edge details if not provided by brute_force_search. """
         logger.warning(f"_get_edge_details called for {triplet_str}. Ensure brute_force_search provides needed properties.")
         # Example: Parse triplet_str, query graph for edge by source/target/type
         return None
