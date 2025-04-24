# retrieve.py
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

# --- Cognee Imports ---
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

# --- Custom Retriever ---
class DevCodeRetriever(BaseRetriever):
    """
    Developer-focused retriever using a multi-stage, graph-centric pipeline.
    Relies on Cognee's `brute_force_triplet_search` to find relevant triplets.
    Uses LLM for analysis and planning (selecting relevant triplet indices),
    and final synthesis. No internal caching is used.
    """

    def __init__(
        self,
        # --- Prompt template paths ---
        analysis_system_prompt_path: str = "prompts/dev_code_analysis_system.txt",
        analysis_user_prompt_path: str = "prompts/dev_code_analysis_user.txt",
        summary_system_prompt_path: str = "prompts/dev_code_summary_system.txt",
        summary_user_prompt_path: str = "prompts/dev_code_summary_user.txt",

        # --- Retrieval Configuration ---
        phase1_top_k: int = 20,
        node_properties_to_project: List[str] = [
            "id", "text", "type", "name", "source_file",
            "start_line", "end_line", "timestamp", "dataset_path"
        ],
        edge_properties_to_project: List[str] = [ # Default list
            "relationship_type", "timestamp", "dataset_path"
        ],
        max_llm_context_triplets: int = 30,
        max_final_context_triplets: int = 20,

        # --- Canonical Schema Properties ---
        node_id_prop: str = "id",
        node_text_prop: str = "text",
        node_type_prop: str = "type",
        node_timestamp_prop: str = "timestamp",
        node_dataset_path_prop: str = "dataset_path",
        edge_type_prop: str = "type",
        edge_timestamp_prop: str = "timestamp",
        edge_dataset_path_prop: str = "dataset_path",

        # --- LLM & Loop Control ---
        max_planning_retries: int = 2,
    ):
        # Store config
        self.analysis_system_prompt_path = analysis_system_prompt_path
        self.analysis_user_prompt_path = analysis_user_prompt_path
        self.summary_system_prompt_path = summary_system_prompt_path
        self.summary_user_prompt_path = summary_user_prompt_path

        self.phase1_top_k = phase1_top_k

        # Store Canonical Schema Properties first
        self.node_id_prop = node_id_prop
        self.node_text_prop = node_text_prop
        self.node_type_prop = node_type_prop
        self.node_timestamp_prop = node_timestamp_prop
        self.node_dataset_path_prop = node_dataset_path_prop
        self.edge_type_prop = edge_type_prop
        self.edge_timestamp_prop = edge_timestamp_prop
        self.edge_dataset_path_prop = edge_dataset_path_prop

        # Ensure key properties are always projected
        self.node_properties_to_project = sorted(list(set([
            self.node_id_prop, self.node_text_prop, self.node_type_prop,
            self.node_dataset_path_prop, self.node_timestamp_prop
            ] + node_properties_to_project)))
        self.edge_properties_to_project = sorted(list(set([
            self.edge_type_prop, self.edge_timestamp_prop, self.edge_dataset_path_prop
            ] + edge_properties_to_project)))

        self.max_llm_context_triplets = max_llm_context_triplets
        self.max_final_context_triplets = max_final_context_triplets
        self.max_planning_retries = max_planning_retries

        logger.info("DevCodeRetriever initialized (Graph-Centric, Index-Based Planning, No Cache).")
        logger.info(f" Phase 1 Search: Using 'brute_force_triplet_search', top_k={self.phase1_top_k}")
        logger.info(f" Node Properties Projected: {self.node_properties_to_project}")
        logger.info(f" Edge Properties Projected: {self.edge_properties_to_project}")
        logger.info(f" Assumed Node Text Property: '{self.node_text_prop}'")
        logger.info(f" Assumed Node Dataset Property: '{self.node_dataset_path_prop}'")
        logger.info(f" Assumed Edge Type Property: '{self.edge_type_prop}'")
        logger.info(f" Assumed Edge Dataset Property: '{self.edge_dataset_path_prop}'")


    # --- Core Orchestration ---
    async def get_completion(
        self,
        query: str,
        user: Optional[User] = None,
        datasets: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Orchestrates the multi-stage, graph-centric retrieval pipeline.
        """
        trace = []
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
            # --- Initial Phase 1 Run (No Caching) ---
            stage_start_time = time.time()
            trace.append({"stage": "initial_retrieval", "status": "started"})
            logger.info("Running initial retrieval phase...")

            initial_triplets = await self._run_retrieval_phase(original_query, user, datasets)
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

                if not current_triplets and not is_last_attempt:
                    logger.warning("Planning phase entered with empty context. Exiting loop.")
                    return {"output": f"Analysis stopped due to lack of relevant context after loops for query: '{query}'", "relevant_context": [], "status": "no_results_post_loop"}

                plan = await self._analyze_and_plan(original_query, current_triplets, datasets)
                trace[-1].update({"status": "completed", "duration": time.time() - stage_start_time, "plan_details": plan.dict()})

                # --- Process Plan Flags ---
                if plan.exit:
                    logger.info(f"LLM requested exit: {plan.output}")
                    final_context_triplets = await self._prepare_context_for_llm(current_triplets, [], plan.relevant_triplet_indices)
                    cleaned_context = self._clean_triplets_for_output(final_context_triplets)
                    status = "exit_clarification" if "clarification" in plan.output.lower() else "exit_suggestion"
                    return {"output": plan.output, "relevant_context": cleaned_context, "status": status, "trace": trace}

                if plan.loop and not is_last_attempt:
                    logger.info(f"LLM requested loop with new query: '{plan.search_query}'")
                    loop_stage_start = time.time()
                    loop_stage_name = f"loop_retrieval_attempt_{retry_count + 1}"
                    trace.append({"stage": loop_stage_name, "status": "started"})
                    logger.info(f"Running loop retrieval phase (query: '{plan.search_query}')...")
                    new_triplets = await self._run_retrieval_phase(plan.search_query, user, datasets)
                    trace[-1].update({"status": "completed", "duration": time.time() - loop_stage_start, "triplet_count": len(new_triplets)})
                    logger.info(f"Loop retrieval phase completed ({len(new_triplets)} new triplets found).")

                    prep_stage_start = time.time()
                    prep_stage_name = f"loop_context_prep_attempt_{retry_count + 1}"
                    trace.append({"stage": prep_stage_name, "status": "started"})
                    current_triplets = await self._prepare_context_for_llm(current_triplets, new_triplets, plan.relevant_triplet_indices)
                    trace[-1].update({"status": "completed", "duration": time.time() - prep_stage_start, "final_triplet_count": len(current_triplets)})
                    logger.info(f"Context prepared for next loop ({len(current_triplets)} triplets).")
                    continue

                if plan.done or is_last_attempt:
                    if is_last_attempt and not plan.done:
                        logger.warning(f"Max planning retries ({self.max_planning_retries}) reached. Proceeding to final summary.")
                        if plan.output: plan.output += "\n(Note: Max planning retries reached)"
                        else: plan.output = "(Note: Max planning retries reached)"

                    logger.info("Planning complete or max retries reached. Proceeding to Phase 3.")
                    prep_stage_start = time.time()
                    prep_stage_name = "final_context_prep"
                    trace.append({"stage": prep_stage_name, "status": "started"})
                    final_triplets = await self._prepare_context_for_llm(current_triplets, [], plan.relevant_triplet_indices)
                    trace[-1].update({"status": "completed", "duration": time.time() - prep_stage_start, "final_triplet_count": len(final_triplets)})
                    logger.info(f"Final context prepared ({len(final_triplets)} triplets).")

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
                    final_response["trace"] = trace
                    logger.info(f"get_completion finished in {time.time() - start_time:.2f} seconds.")
                    return final_response

                logger.error(f"Invalid plan state encountered: {plan.dict()}. Aborting.")
                return {"output": "Error: Internal planning state invalid.", "relevant_context": [], "status": "error_internal_plan", "trace": trace}

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

        graph_collections = self._map_datasets_to_graph_collections(datasets)
        if not graph_collections:
            logger.warning(f"Could not map datasets {datasets} to any graph collections. Attempting search with default collections.")
            graph_collections = None

        properties_to_request = list(set(self.node_properties_to_project + self.edge_properties_to_project))

        try:
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
                    if self._validate_triplet_structure(triplet):
                        processed_triplets.append(triplet)
                    else:
                        logger.warning(f"Skipping invalid/incomplete triplet structure at index {i}: Score={triplet.get('score', 'N/A')}")
                        logger.debug(f"Invalid Triplet Detail: {triplet}")

            duration = time.time() - start_time
            logger.info(f"Graph search completed in {duration:.2f}s, yielded {len(processed_triplets)} processed triplets.")
            return processed_triplets

        except Exception as e:
            logger.exception(f"Error during _run_retrieval_phase calling brute_force_triplet_search: {e}")
            return []

    # --- Phase 2: LLM Planning ---
    async def _analyze_and_plan(self, original_query: str, current_triplets: List[Dict], datasets: List[str]) -> RevisedRetrievalPlan:
        """
        Analyzes the current triplets and generates a plan using the LLM.
        """
        logger.info(f"Analyzing {len(current_triplets)} triplets for planning...")
        llm_client = get_llm_client()

        triplets_for_llm = current_triplets[:self.max_llm_context_triplets]
        if not triplets_for_llm:
            logger.warning("Analysis phase received no triplets. Generating exit plan.")
            return RevisedRetrievalPlan(output="No relevant information found to analyze.", exit=True, relevant_triplet_indices=[])

        # Get dynamic schema types from the current context triplets
        dynamic_types = self._get_dynamic_types_from_triplets(triplets_for_llm)
        available_node_types = sorted(list(dynamic_types.get("node_types", [])))
        available_edge_types = sorted(list(dynamic_types.get("edge_types", [])))
        logger.debug(f"Context Node Types for LLM: {available_node_types}")
        logger.debug(f"Context Edge Types for LLM: {available_edge_types}")

        # Format triplets for the LLM prompt
        formatted_triplets_for_prompt = self._format_triplets_for_llm(triplets_for_llm)

        prompt_context = {
            "original_query": original_query,
            "current_triplets_json": json.dumps(formatted_triplets_for_prompt, indent=2),
            "triplet_input_count": len(triplets_for_llm),
            "total_triplet_count": len(current_triplets),
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
            plan = await llm_client.acreate_structured_output(
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

        triplets_for_summary_prompt = final_triplets[:self.max_llm_context_triplets]
        formatted_triplets = self._format_triplets_for_llm(triplets_for_summary_prompt)

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
            llm_summary = await llm_client.acreate(
                user_prompt=user_prompt,
                system_prompt=system_prompt,
            )
            logger.info("Final summary generated successfully.")

            cleaned_triplets = self._clean_triplets_for_output(final_triplets[:self.max_final_context_triplets])

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
        """
        logger.debug(f"Preparing context. Previous: {len(previous_triplets)}, New: {len(new_triplets)}, Indices: {relevant_indices}")

        selected_triplets = []
        if previous_triplets and relevant_indices:
            max_idx = len(previous_triplets) - 1
            selected_triplets = [previous_triplets[i] for i in relevant_indices if 0 <= i <= max_idx]
            logger.debug(f"Selected {len(selected_triplets)} triplets from previous context based on indices.")

        combined_triplets = selected_triplets + new_triplets
        logger.debug(f"Combined triplets count before deduplication: {len(combined_triplets)}")

        deduplicated_triplets_dict = OrderedDict()
        for triplet in combined_triplets:
            try:
                source_id = triplet.get("source_node", {}).get("id")
                target_id = triplet.get("target_node", {}).get("id")
                edge_type = triplet.get("edge", {}).get("attributes", {}).get(self.edge_type_prop)

                if not all([source_id, target_id, edge_type]):
                    logger.warning(f"Skipping triplet during deduplication due to missing ID/Type. Triplet Score: {triplet.get('score')}")
                    continue

                key_str = f"{source_id}:{edge_type}:{target_id}"
                key = hashlib.sha256(key_str.encode()).hexdigest()

                existing = deduplicated_triplets_dict.get(key)
                current_score = triplet.get("score", 0)

                if not existing or current_score > existing.get("score", 0):
                    deduplicated_triplets_dict[key] = triplet
            except Exception as e:
                logger.warning(f"Error creating key for triplet during deduplication: {e}. Triplet: {triplet}")

        deduplicated_triplets = list(deduplicated_triplets_dict.values())
        logger.debug(f"Deduplicated triplets count: {len(deduplicated_triplets)}")

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

                source_id = source_node.get(self.node_id_prop)
                source_type = source_attrs.get(self.node_type_prop)
                source_name = source_attrs.get("name")
                source_text = source_attrs.get(self.node_text_prop)
                edge_type = edge_attrs.get(self.edge_type_prop)
                target_id = target_node.get(self.node_id_prop)
                target_type = target_attrs.get(self.node_type_prop)
                target_name = target_attrs.get("name")
                target_text = target_attrs.get(self.node_text_prop)

                if not all([source_id, edge_type, target_id]):
                    logger.warning(f"Skipping triplet formatting due to missing core IDs/type at index {i}")
                    continue

                formatted_triplet_data = {
                    "index": i,
                    "score": round(triplet.get("score", 0), 3),
                    "source": {
                        "id": source_id,
                        "type": source_type,
                        "name": source_name,
                        "text_snippet": self._extract_relevant_snippet(source_text, 5),
                    },
                    "edge": { "type": edge_type, },
                    "target": {
                        "id": target_id,
                        "type": target_type,
                        "name": target_name,
                        "text_snippet": self._extract_relevant_snippet(target_text, 5),
                    }
                }
                # Clean None values from inner dicts
                formatted_triplet_data["source"] = {k: v for k, v in formatted_triplet_data["source"].items() if v is not None}
                formatted_triplet_data["edge"] = {k: v for k, v in formatted_triplet_data["edge"].items() if v is not None}
                formatted_triplet_data["target"] = {k: v for k, v in formatted_triplet_data["target"].items() if v is not None}

                formatted.append(formatted_triplet_data)
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

                source_id = source_node.get(self.node_id_prop)
                target_id = target_node.get(self.node_id_prop)
                edge_type = edge_attrs.get(self.edge_type_prop)

                if not all([source_id, target_id, edge_type]):
                    logger.warning(f"Skipping triplet cleaning due to missing core IDs/type. Score: {triplet.get('score')}")
                    continue

                source_path, source_name = self._parse_node_id(source_id)
                target_path, target_name = self._parse_node_id(target_id)

                cleaned_triplet_data = {
                    "score": round(triplet.get("score", 0), 3),
                    "source_node": {
                        "id": source_id,
                        "type": source_attrs.get(self.node_type_prop),
                        "name": source_name or source_attrs.get("name"),
                        "file_path": source_path,
                        "text_snippet": self._extract_relevant_snippet(source_attrs.get(self.node_text_prop,""), 10),
                        "timestamp": source_attrs.get(self.node_timestamp_prop),
                        "dataset_path": source_attrs.get(self.node_dataset_path_prop),
                        "start_line": source_attrs.get("start_line"),
                        "end_line": source_attrs.get("end_line"),
                    },
                    "edge": {
                        "type": edge_type,
                        "timestamp": edge_attrs.get(self.edge_timestamp_prop),
                        "dataset_path": edge_attrs.get(self.edge_dataset_path_prop), # Include edge dataset path
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
                cleaned_triplet_data["source_node"] = {k: v for k, v in cleaned_triplet_data["source_node"].items() if v is not None}
                cleaned_triplet_data["edge"] = {k: v for k, v in cleaned_triplet_data["edge"].items() if v is not None}
                cleaned_triplet_data["target_node"] = {k: v for k, v in cleaned_triplet_data["target_node"].items() if v is not None}

                cleaned.append(cleaned_triplet_data)

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
            if self.node_id_prop not in source_node or self.node_id_prop not in target_node: return False
            if "attributes" not in source_node or "attributes" not in target_node: return False
            if not isinstance(source_node["attributes"], dict) or not isinstance(target_node["attributes"], dict): return False
            if "attributes" not in edge or not isinstance(edge["attributes"], dict): return False

            # Check for essential attributes used later
            # Allow text to be potentially None/empty but check presence if needed downstream
            # if self.node_text_prop not in source_node["attributes"]: return False
            # if self.node_text_prop not in target_node["attributes"]: return False
            if self.edge_type_prop not in edge["attributes"]:
                logger.debug(f"Validation fail: Missing '{self.edge_type_prop}' in edge attributes between {source_node.get(self.node_id_prop)} and {target_node.get(self.node_id_prop)}")
                return False

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
            return None

        collections = set()
        for d in datasets:
            d_clean = d.strip('/')
            parts = d_clean.split('/')
            # Example mapping logic (adapt as needed)
            if len(parts) == 3: # tenant/role/dataset_name
                tenant, role, dataset_name = parts
                # Add most specific first, then broader scopes
                collections.add(f"{tenant}_{role}_{dataset_name}")
                if tenant and dataset_name: collections.add(f"{tenant}_{dataset_name}")
                if tenant: collections.add(tenant)
            elif len(parts) == 2: # tenant/dataset_name
                tenant, dataset_name = parts
                collections.add(f"{tenant}_{dataset_name}")
                if tenant: collections.add(tenant)
            elif len(parts) == 1: # tenant or dataset_name
                collections.add(parts[0])
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
        if not full_text or not isinstance(full_text, str): return None
        lines = full_text.splitlines()
        if not lines: return ""
        snippet_lines = lines[:max_lines]
        snippet = "\n".join(snippet_lines)
        if len(lines) > max_lines:
            if not snippet.rstrip().endswith("..."): snippet += "\n..."
        return snippet

    # --- Canonical ID Parsing Helper ---
    def _parse_node_id(self, node_id: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        """ Parses 'path/to/file:entityName' into (path, name). """
        if not node_id or not isinstance(node_id, str) or ":" not in node_id: return None, None
        try:
            path, name = node_id.rsplit(":", 1)
            return path if path else None, name if name else None
        except Exception: return None, None

    # --- Placeholders (Remove if brute_force_search is sufficient) ---
    async def _get_node_details(self, node_id: str, graph_engine: GraphEngine) -> Optional[Dict]:
        logger.warning(f"_get_node_details called for {node_id}. Should not be needed if brute_force_search projects correctly.")
        return None

    async def _get_edge_details(self, triplet_info: Dict, graph_engine: GraphEngine) -> Optional[Dict]:
        logger.warning(f"_get_edge_details called. Should not be needed if brute_force_search projects correctly.")
        return None
