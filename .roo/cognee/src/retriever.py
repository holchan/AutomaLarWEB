# retriever.py
from typing import Any, Dict, List, Optional, Union, Tuple, Type
import json
import re
import time
from uuid import UUID
import asyncio
from collections import OrderedDict
import os # NEW: For path splitting

# NEW: Pydantic for structured LLM interaction
from pydantic import BaseModel, Field, ValidationError, validator

# Ensure these base classes and functions exist in your Cognee installation path
try:
    from cognee.modules.retrieval.base_retriever import BaseRetriever
    from cognee.infrastructure.databases.vector import get_vector_engine, VectorEngine
    from cognee.infrastructure.databases.graph import get_graph_engine, GraphEngine, GraphDBInterface
    from cognee.infrastructure.llm.get_llm_client import get_llm_client, LLMInterface # Import LLMInterface type
    from cognee.infrastructure.llm.prompts.render_prompt import render_prompt
    from cognee.shared.logging_utils import get_logger
    # Import specific result types if available (adjust based on actual Cognee/Qdrant types)
    from qdrant_client.http.models import ScoredPoint
except ImportError as e:
    print(f"CRITICAL Error importing Cognee components: {e}")
    print("Please ensure Cognee is installed correctly and accessible in the Python environment.")
    raise

logger = get_logger(__name__)

# --- Context Cache ---
# ... (ContextCache class remains the same as previous version) ...
class ContextCache:
    """Simple in-memory cache for get_context results with TTL."""
    def __init__(self, max_size=50, ttl_seconds=600):
        self.cache = OrderedDict() # Use OrderedDict for simple LRU
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
        self.cache.move_to_end(key) # Mark as recently used
        try:
            return json.loads(json.dumps(self.cache[key])) # Return deep copy
        except TypeError:
             logger.warning(f"Could not deep copy cached item for key {key}. Returning direct reference.")
             return self.cache[key]

    def set(self, key, value):
        if len(self.cache) >= self.max_size and key not in self.cache:
            try:
                lru_key, _ = self.cache.popitem(last=False) # Remove least recently used
                logger.debug(f"Cache full. Removing LRU key: {lru_key}")
                self.remove(lru_key) # Also remove from access_times
            except KeyError: pass # Cache might be empty or key already removed
        logger.debug(f"Setting cache for key: {key}")
        try:
            self.cache[key] = json.loads(json.dumps(value)) # Store deep copy
            self.access_times[key] = time.time()
            self.cache.move_to_end(key) # Mark as recently used/added
        except TypeError:
            logger.warning(f"Could not deep copy value for cache key {key}. Storing direct reference.")
            self.cache[key] = value
            self.access_times[key] = time.time()

    def remove(self, key):
        if key in self.cache: del self.cache[key]
        if key in self.access_times: del self.access_times[key]
        logger.debug(f"Removed cache key: {key}")


# --- Pydantic Models for LLM Interaction ---

# Define canonical ID format constant
CANONICAL_ID_SEPARATOR = ":"

class FetchContentRequest(BaseModel):
     node_id: str = Field(..., description=f"The canonical ID (e.g., 'path/file.py{CANONICAL_ID_SEPARATOR}entity') of the node needing full content.")
     reason: str = Field(..., description="Why this node's full content is needed.")
     # file_path: Optional[str] = Field(None, description="File path for context (optional).") # Removed, derived from node_id

class GraphRelationshipSpec(BaseModel):
    node_id: str = Field(..., description=f"The canonical ID of the node to start exploration from (e.g., 'path/file.py{CANONICAL_ID_SEPARATOR}entity').")
    relationship_type: Optional[str] = Field(None, description="Specific relationship type (e.g., CALLS, CONTAINS) or null/omit for any.")
    direction: str = Field("BOTH", enum=["INCOMING", "OUTGOING", "BOTH"], description="Direction of relationship.")
    max_hops: int = Field(1, description="Maximum steps to traverse (usually 1).")
    reason: str = Field(..., description="Why this traversal is needed.")
    # source_file: Optional[str] = Field(None, description="File path of the source node (optional context).") # Removed, derived from node_id

class ToolCallRequest(BaseModel):
    tool_name: str = Field(..., description="Name of the tool/action to execute (e.g., 'fetch_content', 'graph_traversal', 'vector_search').")
    params: Dict[str, Any] = Field(default_factory=dict, description="Parameters required by the tool.")

class RetrievalPlan(BaseModel):
    analysis: str = Field(..., description="Brief assessment of current context and knowledge gaps.")
    needs_retry: bool = Field(False, description="Set true if more internal retrieval/tool calls are needed to satisfy the query based on the analysis.")
    tool_calls: List[ToolCallRequest] = Field(default_factory=list, description="Specific tools to call if needs_retry is true.")
    clarification_needed: Optional[str] = Field(None, description="Question for the user if query is ambiguous. If set, processing stops and waits for user input.")
    suggested_follow_up: Optional[str] = Field(None, description="Summary and suggestion for user if early exit is best (e.g., query too broad). If set, processing stops.")
    # Execution plan used if no retry/clarification/follow-up
    additional_files_to_fetch_full_content: List[FetchContentRequest] = Field(default_factory=list, description="Nodes needing full chunk content retrieval.")
    additional_search_queries: List[str] = Field(default_factory=list, description="New vector search queries.")
    graph_relationships_to_explore: List[GraphRelationshipSpec] = Field(default_factory=list, description="Relationships to explore.")
    # Store fetched types for consistency *within this planning step* - removed from final model state
    # available_node_types: List[str] = Field(default_factory=list, exclude=True) # Exclude from final dict/json
    # available_edge_types: List[str] = Field(default_factory=list, exclude=True)

class FinalSummary(BaseModel):
    overview: str = Field(..., description="High-level architectural overview based on provided chunks.")
    key_components: str = Field(..., description="Analysis of important files/entities identified by their canonical IDs and relationships.")
    implementation_details: Optional[str] = Field(None, description="Deep dive into algorithms or techniques visible in the chunks.")
    code_relationships: Optional[str] = Field(None, description="How components interact based on graph traversals and code chunks.")
    pattern_identification: Optional[str] = Field(None, description="Design patterns identified based on structure and code chunks.")
    technical_considerations: Optional[str] = Field(None, description="Analysis of performance, security, etc., *only if directly evident in chunks*.")
    navigation_guidance: Optional[str] = Field(None, description="Advice on navigating the *provided chunks and identified relationships*.")
    follow_up_suggestions: List[str] = Field(default_factory=list, description="Suggested follow-up questions based on the analysis.")


# --- Custom Retriever (Enhanced: Parallel, Interactive, Graph-Aware, ID-Parsing) --- # MODIFIED
class DevCodeRetriever(BaseRetriever):
    """
    Developer-focused retriever using a multi-stage, potentially interactive pipeline.
    Performs parallel Vector + Graph search for initial context. Uses LLM for analysis,
    planning (incl. graph traversals, tool calls, user clarification), execution, and synthesis.
    Relies on parsing canonical node IDs ('path/to/file:entityName') for path/name info.

    ASSUMPTIONS:
    - Canonical Node ID Format: Nodes MUST have IDs matching 'path/to/file:entityName'.
    - ':' Separator: The colon ':' MUST NOT appear in file paths or entity names.
    - Requires Cypher-compatible graph DB (Neo4j-like results).
    - Relies on canonical properties being consistently populated during ingestion.
    - Vector DB adapter capabilities determine filtering effectiveness.
    - LLM used supports structured output (Pydantic models via Cognee interface).
    """

    def __init__(
        self,
        # --- Prompt template paths ---
        system_prompt_path: str = "dev_code_retrieval_system.txt",
        user_prompt_path: str = "dev_code_retrieval_user.txt",
        analysis_system_prompt_path: str = "dev_code_analysis_prompt.txt",
        analysis_user_prompt_path: str = "dev_code_analysis_user_prompt.txt",

        # --- Schema & Configuration (Canonical Properties) ---
        vector_collections: List[str] = ["TextChunks"],
        vector_search_limit: int = 25,
        graph_search_limit: int = 25,
        # IMPORTANT: Adapt Cypher query. It now needs to potentially parse IDs if filtering by path/name
        # Or rely on searching other properties like summary/description/content.
        # Example searching content and description, filtering by dataset later
        graph_attribute_search_cypher: str = """
            MATCH (n)
            WHERE (
                (n.description IS NOT NULL AND n.description CONTAINS $query_term) OR
                (n.summary IS NOT NULL AND n.summary CONTAINS $query_term) OR
                (n.content IS NOT NULL AND n.content CONTAINS $query_term)
            )
            // Filtering by name requires parsing the ID or a dedicated name property
            // OR n.id ENDS WITH (':'+$query_term) // Less efficient, assumes format
            RETURN n // Return whole node
            LIMIT $limit
        """,

        # Canonical Node Properties (ID format is 'path/to/file:entityName')
        node_id_prop: str = "id",             # Unique ID ('path:entityName')
        # node_name_prop REMOVED
        # node_file_path_prop REMOVED
        node_chunk_prop: str = "content",
        node_dataset_path_prop: str = "dataset_path", # 'tenant/role/dataset'
        node_type_prop: str = "node_type",
        node_timestamp_prop: str = "timestamp",
        node_start_line_prop: str = "start_line",
        node_end_line_prop: str = "end_line",
        node_scope_prop: str = "in_scope", # Optional

        # Canonical Edge Properties
        edge_id_prop: str = "id",
        edge_dataset_path_prop: str = "dataset_path", # If edges store this
        edge_type_prop: str = "edge_type", # Property holding the relationship type label
        edge_timestamp_prop: str = "timestamp",

        # --- Retrieval limits ---
        max_final_results: int = 10,
        max_out_of_scope_results: int = 5,
        graph_traversal_neighbor_limit: int = 10,
        dynamic_node_types_top_n: int = 15,
        dynamic_edge_types_top_n: int = 10,
        max_planning_retries: int = 3,

        # --- Type Vocabulary Cache Configuration ---
        type_cache_max_size: int = 100,
        type_cache_ttl_seconds: int = 3600,
        # static_types_map_path: Optional[str] = None, # Keep placeholder if needed
    ):
        # Store config
        self.system_prompt_path = system_prompt_path
        self.user_prompt_path = user_prompt_path
        self.analysis_system_prompt_path = analysis_system_prompt_path
        self.analysis_user_prompt_path = analysis_user_prompt_path

        self.vector_collections = vector_collections
        self.vector_search_limit = vector_search_limit
        self.graph_search_limit = graph_search_limit
        self.graph_attribute_search_cypher = graph_attribute_search_cypher

        self.max_final_results = max_final_results
        self.max_out_of_scope_results = max_out_of_scope_results
        self.graph_traversal_neighbor_limit = graph_traversal_neighbor_limit
        self.dynamic_node_types_top_n = dynamic_node_types_top_n
        self.dynamic_edge_types_top_n = dynamic_edge_types_top_n
        self.max_planning_retries = max_planning_retries

        # Store Canonical Schema Properties (No name/path props)
        self.node_id_prop = node_id_prop
        self.node_chunk_prop = node_chunk_prop
        self.node_dataset_path_prop = node_dataset_path_prop
        self.node_type_prop = node_type_prop
        self.node_timestamp_prop = node_timestamp_prop
        self.node_start_line_prop = node_start_line_prop
        self.node_end_line_prop = node_end_line_prop
        self.node_scope_prop = node_scope_prop

        self.edge_id_prop = edge_id_prop
        self.edge_dataset_path_prop = edge_dataset_path_prop
        self.edge_type_prop = edge_type_prop
        self.edge_timestamp_prop = edge_timestamp_prop

        # Initialize Caches
        self.context_cache = ContextCache()
        self.type_vocabulary_cache = OrderedDict()
        self.type_cache_max_size = type_cache_max_size
        self.type_cache_ttl_seconds = type_cache_ttl_seconds

        # Placeholder for loaded static types
        self.static_types_map = {} # Needs implementation: self._load_static_types(...)

        logger.info("DevCodeRetriever initialized (Enhanced: Parallel, Interactive, Graph-Aware, ID-Parsing).")
        # MODIFIED: Updated logging
        logger.info(f" Assumptions - Vector Collections: {self.vector_collections}")
        logger.info(f" Assumptions - Canonical Node Props: id={self.node_id_prop} (Format: 'path:entityName'), chunk={self.node_chunk_prop}, dataset={self.node_dataset_path_prop}, type={self.node_type_prop}, ...")
        logger.info(f" Assumptions - Canonical Edge Props: id={self.edge_id_prop}, type={self.edge_type_prop}, dataset={self.edge_dataset_path_prop}, ...")
        logger.info(f" Assumptions - Type Cache: max_size={self.type_cache_max_size}, ttl={self.type_cache_ttl_seconds}s")
        logger.info(f" IMPORTANT: Relying on parsing node ID '{self.node_id_prop}' for path and name.")
        logger.info(f" IMPORTANT DB ASSUMPTION: Requires Cypher-compatible graph DB (Neo4j-like results).")


    # --- NEW: Helper functions for parsing the canonical ID ---
    def _parse_node_id(self, node_id: str) -> Tuple[Optional[str], Optional[str]]:
        """Parses 'path/to/file:entityName' into (path, name). Returns (None, None) on error."""
        if not node_id or CANONICAL_ID_SEPARATOR not in node_id:
            # logger.warning(f"Cannot parse node ID: '{node_id}'. Invalid format.")
            return None, None
        try:
            path, name = node_id.rsplit(CANONICAL_ID_SEPARATOR, 1)
            return path if path else None, name if name else None
        except Exception as e:
            # logger.warning(f"Error parsing node ID '{node_id}': {e}")
            return None, None

    def _get_path_from_id(self, node_id: str) -> Optional[str]:
        """Extracts the path part from the canonical node ID."""
        path, _ = self._parse_node_id(node_id)
        return path

    def _get_name_from_id(self, node_id: str) -> Optional[str]:
        """Extracts the entity name part from the canonical node ID."""
        _, name = self._parse_node_id(node_id)
        return name

    # --- Main Orchestration Method (Includes Interactive Planning Loop) ---
    async def get_completion(
        self, query: str, context: Optional[Dict[str, Any]] = None, datasets: List[str] = None
    ) -> Dict[str, Any]:
        """ Orchestrates the multi-stage retrieval pipeline, including interactive planning. """
        # ... (Orchestration logic remains the same as previous version,
        #      including the planning loop, checks for clarification/follow-up,
        #      tool dispatch, and final response generation.
        #      It now relies on the ID parsing helpers indirectly via other methods.) ...
        trace = []
        start_time = time.time()
        logger.info(f"Starting get_completion for query: '{query}' in datasets: {datasets}")
        final_response = {}

        if not datasets:
            logger.error("No datasets provided to get_completion.")
            return {"summary": "Error: Retrieval requires specific dataset paths.", "status": "error", "relevant_files": [], "out_of_scope_results": [], "trace": [{"stage": "error", "message": "Missing dataset scope"}]}

        try:
            # --- Phase 1: Gather Initial Candidates (Parallel Vector + Graph Attr) ---
            stage_start_time = time.time()
            trace.append({"stage": "initial_retrieval", "status": "started"})
            if context is None:
                cache_key = f"context:{query}:{','.join(sorted(datasets))}:v_parallel_idparse" # Updated key
                cached_context = self.context_cache.get(cache_key)
                if cached_context:
                    context = cached_context
                    logger.info("Retrieved initial context from cache.")
                    context['datasets'] = datasets # Ensure datasets are set
                    trace[-1].update({"status": "completed", "source": "cache", "duration": time.time() - stage_start_time})
                else:
                    logger.info("Performing new initial context retrieval (parallel graph+vector).")
                    context = await self.get_context_parallel(query, datasets)
                    if context: self.context_cache.set(cache_key, context)
                    trace[-1].update({"status": "completed", "source": "new", "duration": time.time() - stage_start_time})
            else:
                 context.setdefault("relevant_files", [])
                 context.setdefault("out_of_scope_results", [])
                 context['datasets'] = datasets # Ensure datasets are set
                 logger.info("Using provided initial context.")
                 trace[-1].update({"status": "completed", "source": "provided", "duration": time.time() - stage_start_time})

            if not context or not context.get("relevant_files"):
                logger.warning(f"No relevant files found for query: {query} within datasets: {datasets}")
                return {"summary": f"No relevant results found for query: {query}", "status": "no_results", "relevant_files": [], "out_of_scope_results": context.get("out_of_scope_results", []) if context else [], "trace": trace}

            # --- Phase 2: Plan & Enhance Loop ---
            enhanced_context = context # Start with initial context
            plan_model = None # To store the last valid plan
            for retry_count in range(self.max_planning_retries):
                stage_start_time = time.time()
                plan_stage_name = f"analysis_planning_attempt_{retry_count + 1}"
                trace.append({"stage": plan_stage_name, "status": "started"})
                logger.info(f"Planning analysis (Attempt {retry_count + 1}/{self.max_planning_retries})")

                # --- Step 2a: Analyze and Plan ---
                plan_model: RetrievalPlan = await self._analyze_and_plan(query, enhanced_context, datasets)
                trace[-1].update({
                    "status": "completed", "duration": time.time() - stage_start_time,
                    "plan_details": plan_model.dict(exclude={'available_node_types', 'available_edge_types'}) # Use Pydantic dict
                })

                # --- Check for User Interaction Flags ---
                if plan_model.clarification_needed:
                    logger.info(f"LLM requires clarification: {plan_model.clarification_needed}")
                    return {"summary": plan_model.clarification_needed, "status": "clarification_required", "relevant_files": self._clean_results_for_output(enhanced_context.get("relevant_files", [])), "out_of_scope_results": self._clean_results_for_output(enhanced_context.get("out_of_scope_results", [])), "trace": trace}
                if plan_model.suggested_follow_up:
                    logger.info(f"LLM suggests early exit with follow-up: {plan_model.suggested_follow_up}")
                    return {"summary": plan_model.suggested_follow_up, "status": "follow_up_suggested", "relevant_files": self._clean_results_for_output(enhanced_context.get("relevant_files", [])), "out_of_scope_results": self._clean_results_for_output(enhanced_context.get("out_of_scope_results", [])), "trace": trace}

                # --- Check for Internal Retry / Tool Calls ---
                if plan_model.needs_retry and plan_model.tool_calls:
                    logger.info(f"Executing {len(plan_model.tool_calls)} specific tool calls based on plan.")
                    tool_stage_start = time.time()
                    tool_stage_name = f"tool_execution_attempt_{retry_count + 1}"
                    trace.append({"stage": tool_stage_name, "status": "started", "calls": len(plan_model.tool_calls)})
                    tool_results = await self._dispatch_tool_calls(plan_model.tool_calls, enhanced_context, datasets)
                    enhanced_context = self._update_context_with_tool_results(enhanced_context, tool_results)
                    trace[-1].update({"status": "completed", "duration": time.time() - tool_stage_start})
                    continue # Continue loop for replanning
                elif plan_model.needs_retry:
                    logger.warning("Plan indicates needs_retry=True but no tool_calls provided. Executing full plan instead.")
                    pass

                # --- If no retry/clarification/follow-up: Execute Full Plan ---
                logger.info("Executing full retrieval plan based on analysis.")
                exec_stage_start = time.time()
                exec_stage_name = f"full_plan_execution_attempt_{retry_count + 1}"
                trace.append({"stage": exec_stage_name, "status": "started"})
                # Execute fetches, queries, traversals defined in the plan
                enhanced_context = await self._execute_retrieval_plan(
                    plan_model.dict(exclude={'available_node_types', 'available_edge_types'}), # Pass dict version of plan
                    enhanced_context, datasets, trace
                )
                # OPTIMIZATION REMOVED: Types are fetched again in final stage
                break # Exit loop, proceed to synthesis

            else: # Loop finished without break (max retries reached)
                logger.warning(f"Max planning retries ({self.max_planning_retries}) reached. Proceeding with current context.")
                # Ensure context is prepared for final stage even if loop exhausted
                if 'plan_model' not in locals() or not plan_model: # If planning failed entirely on first try
                     enhanced_context = context # Use initial context
                     enhanced_context['analysis_notes'] = "Planning failed or exhausted retries."


            # --- Phase 3: Synthesize Final Answer ---
            stage_start_time = time.time()
            trace.append({"stage": "response_generation", "status": "started"})
            final_response = await self._generate_comprehensive_response(
                query, enhanced_context, datasets # Pass datasets to fetch types again
            )
            trace[-1].update({"status": "completed", "duration": time.time() - stage_start_time})

            end_time = time.time()
            logger.info(f"get_completion finished in {end_time - start_time:.2f} seconds.")
            final_response["trace"] = trace
            return final_response

        except Exception as e:
            logger.exception(f"Critical error during get_completion for query '{query}': {str(e)}")
            relevant_files = self._clean_results_for_output(context.get("relevant_files", [])) if context else []
            out_of_scope = self._clean_results_for_output(context.get("out_of_scope_results", [])) if context else []
            final_response = {"summary": f"An error occurred: {str(e)}", "status": "error", "relevant_files": relevant_files, "out_of_scope_results": out_of_scope}
            error_trace_entry = {"stage": "error", "message": str(e)}
            if trace and trace[-1].get("stage") != "error": trace.append(error_trace_entry)
            elif not trace: trace = [error_trace_entry]
            final_response["trace"] = trace
            return final_response


    # --- Stage 1: Initial Context Retrieval (Parallel Vector + Graph Attr) ---
    async def get_context_parallel(self, query: str, datasets: List[str]) -> Optional[Dict[str, Any]]:
        """ Performs parallel Vector + Graph attribute search, merges results. """
        # ... (Logic remains the same as previous version, but calls processing
        #      helpers that now use ID parsing instead of dedicated props) ...
        if not datasets: logger.error("get_context_parallel called without datasets."); return None
        logger.info(f"Performing parallel initial context retrieval for '{query}' in datasets: {datasets}")
        start_time = time.time()
        vector_engine, graph_engine = get_vector_engine(), await get_graph_engine()

        vector_filter = self._create_vector_filter(datasets)
        vector_search_task = asyncio.create_task(self._perform_vector_search(vector_engine, query, self.vector_search_limit, vector_filter))
        graph_search_task = asyncio.create_task(self._perform_graph_attribute_search(graph_engine, query, self.graph_search_limit, datasets))

        vector_results_raw, graph_results_raw = await asyncio.gather(vector_search_task, graph_search_task, return_exceptions=True)

        if isinstance(vector_results_raw, Exception): logger.error(f"Vector search failed: {vector_results_raw}"); vector_results_raw = []
        if isinstance(graph_results_raw, Exception): logger.error(f"Graph attribute search failed: {graph_results_raw}"); graph_results_raw = []
        logger.debug(f"Raw vector results: {len(vector_results_raw)}, Raw graph results: {len(graph_results_raw)}")

        processed_vector_results = await self._process_vector_results(vector_results_raw, query)
        processed_graph_results = await self._process_graph_results(graph_results_raw, query, graph_engine)

        merged_results = self._merge_and_deduplicate_results(processed_vector_results, processed_graph_results)

        relevant_files, out_of_scope_results = [], []
        for result in merged_results:
            result_dataset = result.get(self.node_dataset_path_prop)
            if result_dataset and result_dataset in datasets:
                result["is_in_scope"] = True; relevant_files.append(result)
            elif result_dataset:
                 result["is_in_scope"] = False; out_of_scope_results.append(result)
            else: logger.error(f"Merged result missing dataset path: {result.get(self.node_id_prop)}. Discarding.")

        final_relevant_files = self._deduplicate_and_sort_results(relevant_files, self.max_final_results)
        final_out_of_scope = self._deduplicate_and_sort_results(out_of_scope_results, self.max_out_of_scope_results)

        duration = time.time() - start_time
        logger.info(f"Parallel context retrieval completed in {duration:.2f}s. Found {len(final_relevant_files)} relevant, {len(final_out_of_scope)} out-of-scope.")
        return {"query": query, "datasets": datasets, "relevant_files": final_relevant_files, "out_of_scope_results": final_out_of_scope}


    # --- Helper methods for Stage 1 (Parallel) ---

    async def _perform_vector_search(self, vector_engine: VectorEngine, query: str, limit: int, vector_filter: Optional[Any]) -> List[ScoredPoint]:
        """ Performs vector searches across configured collections with optional filter. """
        # ... (Logic is the same, no changes needed for ID parsing here) ...
        all_results = []
        search_tasks = []
        use_local_filtering = False
        fetch_limit = limit * 2 if vector_filter is None else limit

        for collection in self.vector_collections:
            try:
                search_tasks.append(vector_engine.search(collection, query, limit=fetch_limit, filter=vector_filter))
                if vector_filter is None: use_local_filtering = True # Flag if filter couldn't be applied
            except NotImplementedError:
                 logger.warning(f"Vector filtering not supported for '{collection}'. Fetching more results.")
                 use_local_filtering = True
                 search_tasks.append(vector_engine.search(collection, query, limit=limit * 5)) # Fetch more
            except Exception as e: logger.error(f"Error preparing vector search for {collection}: {e}")
        if not search_tasks: return []
        results_per_collection = await asyncio.gather(*search_tasks, return_exceptions=True)
        for i, res_list in enumerate(results_per_collection):
            if isinstance(res_list, Exception): logger.warning(f"Error searching vector collection {self.vector_collections[i]}: {res_list}")
            elif isinstance(res_list, list): all_results.extend(res_list)
        logger.debug(f"Vector search phase yielded {len(all_results)} raw results (before potential local filtering).")
        # Local filtering based on datasets is now handled in get_context_parallel after merging
        return all_results


    async def _perform_graph_attribute_search(self, graph_engine: GraphEngine, query: str, limit: int, datasets: List[str]) -> List[Any]:
        """ Performs attribute search on the graph using configured Cypher, filtering by datasets. """
        # ... (Logic is the same, Cypher query needs adapting if it relied on name/path props) ...
        # Note: The default query searches content/description/summary, not name/path.
        # If you need name/path search, you'll need to add ID parsing logic to the Cypher or use specific graph functions.
        try:
            params = {"query_term": query, "limit": limit, "datasets": datasets}
            final_cypher = self.graph_attribute_search_cypher
            dataset_filter_clause = f"n.`{self.node_dataset_path_prop}` IN $datasets"
            # Inject dataset filter if not present
            if dataset_filter_clause not in final_cypher:
                 where_pos = final_cypher.upper().find("WHERE")
                 insertion_pos = final_cypher.upper().find("RETURN") # Simplified insertion point
                 if where_pos != -1: final_cypher = final_cypher[:insertion_pos].rstrip() + f" AND {dataset_filter_clause} " + final_cypher[insertion_pos:]
                 elif insertion_pos != -1: final_cypher = final_cypher[:insertion_pos].rstrip() + f" WHERE {dataset_filter_clause} " + final_cypher[insertion_pos:]
                 else: logger.error("Could not add dataset filter to graph Cypher.")

            logger.debug(f"Executing graph attribute search with Cypher: {final_cypher[:150]}... Params: {params}")
            graph_search_results = await graph_engine.graph_db.execute_query(final_cypher, params=params)
            processed_results = []
            if graph_search_results:
                 for record in graph_search_results:
                     if hasattr(record, 'get') and 'n' in record:
                         node_data = record['n']
                         properties = dict(node_data.items()) if hasattr(node_data, 'items') else node_data
                         if hasattr(record, 'get') and 'relevance' in record: properties['score'] = record['relevance']
                         processed_results.append(properties)
                     elif isinstance(record, dict): processed_results.append(record)
                     else: logger.warning(f"Unexpected graph result record format: {type(record)}")
            logger.debug(f"Graph attribute search returned {len(processed_results)} processed results.")
            return processed_results
        except Exception as e:
            logger.error(f"Graph attribute search failed: {e}", exc_info=True)
            return []


    # MODIFIED: Uses ID parsing helpers
    async def _process_vector_results(self, results: List[ScoredPoint], query: str) -> List[Dict]:
        """ Processes raw vector results into canonical dict format, parsing ID for path/name. """
        processed = []
        for res in results:
            try:
                payload = res.payload or {}
                metadata = payload.get("metadata", {})
                node_id = metadata.get(self.node_id_prop) or payload.get(self.node_id_prop)
                if not node_id: continue # Skip if no ID

                file_path, node_name = self._parse_node_id(node_id) # Parse ID

                dataset_path = metadata.get(self.node_dataset_path_prop) or payload.get(self.node_dataset_path_prop)
                text_chunk = payload.get(self.node_chunk_prop, "")
                start_line = metadata.get(self.node_start_line_prop) or payload.get(self.node_start_line_prop)
                end_line = metadata.get(self.node_end_line_prop) or payload.get(self.node_end_line_prop)
                timestamp = metadata.get(self.node_timestamp_prop) or payload.get(self.node_timestamp_prop)
                node_type = metadata.get(self.node_type_prop) or payload.get(self.node_type_prop)
                # project_id = metadata.get(self.project_id_prop_in_graph) # Project ID not typically in vector meta

                if not file_path or not dataset_path: # Check critical parsed/metadata fields
                    logger.error(f"CRITICAL: Vector result {node_id} missing mandatory parsed path or dataset path '{self.node_dataset_path_prop}'. Skipping.")
                    continue

                item_info = {
                    self.node_id_prop: str(node_id),
                    "source": "vector",
                    "relevance_score": res.score,
                    "file_path": file_path, # Parsed from ID
                    "name": node_name,     # Parsed from ID
                    self.node_dataset_path_prop: dataset_path,
                    self.node_chunk_prop: text_chunk,
                    "relevant_chunk": self._extract_relevant_chunk(text_chunk, query),
                    "line_range": self._parse_and_validate_line_range(start_line, end_line, text_chunk),
                    self.node_type_prop: node_type,
                    self.node_timestamp_prop: timestamp,
                    # "project_id": project_id, # Usually filtered via dataset_path
                    "_might_need_full_content": not text_chunk or len(text_chunk.splitlines()) < 5,
                }
                processed.append({k: v for k, v in item_info.items() if v is not None})
            except Exception as e:
                logger.warning(f"Error processing vector result {getattr(res, 'id', 'N/A')}: {e}")
        return processed

    # MODIFIED: Removed direct graph_engine param, relies on _standardize_graph_node for potential fetch
    async def _process_graph_results(self, graph_nodes_data: List[Dict], query: str, graph_engine: GraphEngine) -> List[Dict]:
        """ Processes raw graph node data into canonical dict format. """
        processed_results = []
        # Pass graph_engine to standardize for potential content fetching
        processing_tasks = [
            self._standardize_graph_node(node_data, "initial graph search", graph_engine, query)
            for node_data in graph_nodes_data
        ]
        results = await asyncio.gather(*processing_tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, dict) and result: processed_results.append(result)
            elif isinstance(result, Exception): logger.error(f"Error standardizing graph node from initial search: {result}")
        return processed_results

    # _merge_and_deduplicate_results - Logic remains the same (uses node_id_prop)
    def _merge_and_deduplicate_results(self, vec_results: List[Dict], graph_results: List[Dict]) -> List[Dict]:
        """ Merges results from vector and graph searches based on canonical node_id_prop. """
        # ... (Logic is the same as previous version) ...
        merged = {}
        all_results = vec_results + graph_results
        for result in all_results:
            key = result.get(self.node_id_prop)
            if not key: continue
            existing = merged.get(key)
            current_score = result.get("relevance_score", 0)
            if not existing or current_score > existing.get("relevance_score", 0): merged[key] = result
            elif existing and current_score == existing.get("relevance_score", 0) and result.get("source", "").startswith("graph"):
                 # Prefer graph result on score tie if it might have better metadata/content
                 merged[key] = result
        logger.info(f"Merged {len(vec_results)} vector and {len(graph_results)} graph results into {len(merged)} unique results.")
        return list(merged.values())


    # --- Stage 2: Analysis Planning (Using Pydantic) ---
    # MODIFIED: Uses ID parsing, fetches types internally
    async def _analyze_and_plan(self, query: str, context: Dict[str, Any], datasets: List[str]) -> RetrievalPlan:
        """ Analyzes initial context, fetches types, generates structured plan via LLM+Pydantic. """
        logger.info(f"Creating analysis plan for query: '{query}' scoped to datasets: {datasets}")
        llm_client = get_llm_client()
        graph_engine = await get_graph_engine()

        # --- Get Combined Type Vocabulary (FETCHED HERE) ---
        dynamic_types = await self._get_dynamic_type_vocabulary(datasets, graph_engine)
        static_nodes, static_edges = self._get_static_types_for_datasets(datasets)
        available_node_types = sorted(list(set(dynamic_types.get("node_types", []) + static_nodes)))
        available_edge_types = sorted(list(set(dynamic_types.get("edge_types", []) + static_edges)))
        logger.debug(f"Using Node Types for Planning: {available_node_types}")
        logger.debug(f"Using Edge Types for Planning: {available_edge_types}")

        # Prepare summaries, parsing ID for path/name
        relevant_files_summary = []
        for f in context.get("relevant_files", [])[:7]:
             path, name = self._parse_node_id(f.get(self.node_id_prop, ""))
             relevant_files_summary.append({
                 "file_path": path, # Parsed
                 "name": name,      # Parsed
                 "dataset": f.get(self.node_dataset_path_prop),
                 "score": round(f.get("relevance_score", 0), 2),
                 "id": f.get(self.node_id_prop),
                 "type": f.get(self.node_type_prop),
             })

        out_of_scope_summary = []
        for f in context.get("out_of_scope_results", [])[:3]:
             path, _ = self._parse_node_id(f.get(self.node_id_prop, ""))
             out_of_scope_summary.append({
                 "file_path": path, # Parsed
                 "dataset": f.get(self.node_dataset_path_prop),
                 "score": round(f.get("relevance_score", 0), 2),
                 "id": f.get(self.node_id_prop), # Include ID for reference
             })

        user_prompt_context = {
            "query": query,
            "relevant_files_summary": json.dumps(relevant_files_summary, indent=2),
            "out_of_scope_summary": json.dumps(out_of_scope_summary, indent=2),
            "out_of_scope_count": len(context.get("out_of_scope_results", [])),
            "available_node_types": ", ".join(available_node_types),
            "available_edge_types": ", ".join(available_edge_types),
            "node_id_property_name": self.node_id_prop,
            "node_id_format": f"'path/to/file{CANONICAL_ID_SEPARATOR}entityName'", # Explain format
            "edge_type_property_name": self.edge_type_prop,
        }

        try:
            system_prompt = await render_prompt(self.analysis_system_prompt_path, user_prompt_context)
            user_prompt = await render_prompt(self.analysis_user_prompt_path, user_prompt_context)
        except Exception as e:
            logger.error(f"Error rendering analysis prompts: {e}")
            system_prompt = "You are an intelligent code analysis planner..."
            user_prompt = f"Analyze query '{query}'. Plan using available types. Decide: clarify, suggest follow-up, retry (with tool calls), or execute full plan."

        try:
            # Use Pydantic model for structured output
            plan_model_instance: RetrievalPlan = await llm_client.acreate_structured_output(
                user_prompt, system_prompt, response_model=RetrievalPlan
            )
            # Store fetched types in the plan object before returning
            plan_model_instance.available_node_types = available_node_types
            plan_model_instance.available_edge_types = available_edge_types
            logger.info("Analysis plan generated and validated via Pydantic.")
            logger.debug(f"Plan details: {plan_model_instance.dict()}")
            return plan_model_instance

        except ValidationError as e:
             logger.error(f"LLM output failed Pydantic validation for RetrievalPlan: {e}")
             return RetrievalPlan(analysis=f"LLM output validation failed: {e}", needs_retry=False)
        except Exception as e:
            logger.exception(f"LLM Error generating analysis plan: {str(e)}")
            return RetrievalPlan(analysis=f"LLM call failed: {e}", needs_retry=False)


    # --- Stage 3: Enhanced Retrieval (Execute Plan / Dispatch Tools) ---
    # ... (_dispatch_tool_calls, _update_context_with_tool_results, _execute_retrieval_plan
    #      remain largely the same structurally, but ensure they use ID parsing where needed
    #      and handle the Pydantic plan model correctly) ...

    async def _dispatch_tool_calls(self, tool_calls: List[ToolCallRequest], context: Dict[str, Any], datasets: List[str]) -> List[Any]:
        """ Executes specific tool calls requested by the LLM plan. """
        # ... (Implementation needs careful review to ensure params match Pydantic models
        #      and ID parsing is used if file_path/name are needed from node_id) ...
        results = []
        graph_engine = await get_graph_engine()
        vector_engine = get_vector_engine()

        for call in tool_calls:
            tool_name = call.tool_name
            params = call.params
            logger.info(f"Dispatching tool call: {tool_name} with params: {params}")
            try:
                if tool_name == "fetch_content":
                    node_id = params.get('node_id') # Pydantic ensures this key exists if tool called
                    if node_id:
                        content = await self._get_full_file_content_from_graph(node_id, graph_engine)
                        results.append({"tool": tool_name, "node_id": node_id, "result": content})
                    else: raise ValueError("Missing node_id for fetch_content tool call") # Should be caught by Pydantic

                elif tool_name == "graph_traversal":
                    # Pydantic already validated the structure of params against GraphRelationshipSpec
                    traversal_results = await self._perform_graph_traversal(graph_engine, params)
                    results.append({"tool": tool_name, "request": params, "result": traversal_results})

                elif tool_name == "vector_search":
                    query = params.get("query")
                    limit = params.get("limit", 5)
                    if query:
                        vector_filter = self._create_vector_filter(datasets)
                        search_results_raw = await self._perform_vector_search(vector_engine, query, limit, vector_filter)
                        processed_results = await self._process_vector_results(search_results_raw, query) # Process results
                        results.append({"tool": tool_name, "query": query, "result": processed_results})
                    else: raise ValueError("Missing query for vector_search tool call")

                else:
                    logger.warning(f"Unknown tool requested: {tool_name}")
                    results.append({"tool": tool_name, "error": "Unknown tool"})

            except Exception as e:
                 logger.error(f"Error executing tool call {tool_name}: {e}", exc_info=True)
                 results.append({"tool": tool_name, "error": str(e), "params": params})
        return results


    def _update_context_with_tool_results(self, context: Dict[str, Any], tool_results: List[Any]) -> Dict[str, Any]:
        """ Merges results from tool calls back into the context. """
        # ... (Logic remains similar, ensure consistency with canonical IDs and structure) ...
        logger.debug(f"Updating context with {len(tool_results)} tool results.")
        # Use a copy to avoid modifying original context dict directly in loop
        current_relevant_files = context["relevant_files"]
        current_out_of_scope = context["out_of_scope_results"]
        current_relevant_ids = {f[self.node_id_prop] for f in current_relevant_files}
        current_out_of_scope_ids = {f[self.node_id_prop] for f in current_out_of_scope}
        all_current_ids = current_relevant_ids.union(current_out_of_scope_ids)

        datasets = context["datasets"] # Get current dataset scope

        for res in tool_results:
            if res.get("error"): continue

            tool_name = res.get("tool")
            result_data = res.get("result")

            if tool_name == "fetch_content" and isinstance(result_data, str):
                node_id = res.get("node_id")
                # Update existing entry in relevant_files
                for file_info in current_relevant_files:
                    if file_info.get(self.node_id_prop) == node_id:
                        file_info[self.node_chunk_prop] = result_data
                        file_info["relevant_chunk"] = self._extract_relevant_chunk(result_data, context["query"])
                        file_info["_fetched_full_content"] = True
                        if file_info.get("line_range",{}).get("start") is None:
                             file_info["line_range"] = self._estimate_line_range(result_data)
                        break
                # Could also update out_of_scope if needed, but less likely

            elif (tool_name == "graph_traversal" or tool_name == "vector_search") and isinstance(result_data, list):
                # Add unique nodes found, checking scope
                for node_info in result_data:
                    if isinstance(node_info, dict):
                         node_id = node_info.get(self.node_id_prop)
                         if node_id and node_id not in all_current_ids:
                              result_dataset = node_info.get(self.node_dataset_path_prop)
                              if result_dataset in datasets:
                                   node_info["is_in_scope"] = True
                                   current_relevant_files.append(node_info)
                                   all_current_ids.add(node_id) # Track added ID
                              elif result_dataset: # New, but out of scope
                                   node_info["is_in_scope"] = False
                                   current_out_of_scope.append(node_info)
                                   all_current_ids.add(node_id) # Track added ID

        # Update context lists (no need to re-sort/dedupe here, do it before final response)
        context["relevant_files"] = current_relevant_files
        context["out_of_scope_results"] = current_out_of_scope
        return context


    async def _execute_retrieval_plan(
        self,
        plan_dict: Dict[str, Any], # Plan is now a dictionary derived from Pydantic model
        context: Dict[str, Any],
        datasets: List[str],
        trace: List[Dict]
    ) -> Dict[str, Any]:
        """ Executes the FULL retrieval plan if no tool calls/retry were specified. """
        # ... (Logic remains similar, uses new processing helpers) ...
        logger.info("Executing full retrieval plan (fetch content, queries, traversals)...")
        start_time = time.time()
        enhanced_context = { # Create a fresh dict for results of this stage
            "query": context["query"],
            "datasets": list(datasets),
            "relevant_files": [f.copy() for f in context.get("relevant_files", [])],
            "out_of_scope_results": [f.copy() for f in context.get("out_of_scope_results", [])],
            "analysis_notes": plan_dict.get("analysis", ""),
            # Types fetched during planning are NOT passed here anymore
        }
        current_relevant_ids = {rf.get(self.node_id_prop) for rf in enhanced_context["relevant_files"]}

        graph_engine = await get_graph_engine()
        vector_engine = get_vector_engine()

        fetch_content_indices = {}
        # --- 1. Plan: Fetch full content ---
        nodes_to_fetch_dicts = plan_dict.get("additional_files_to_fetch_full_content", [])
        fetch_content_tasks = []
        if nodes_to_fetch_dicts:
             logger.info(f"Planning to fetch full content for {len(nodes_to_fetch_dicts)} items.")
             for i, node_req_dict in enumerate(nodes_to_fetch_dicts):
                 # node_id = FetchContentRequest(**node_req_dict).node_id # Validate via Pydantic if needed
                 node_id = node_req_dict.get(self.node_id_prop) # Direct access
                 if node_id:
                      fetch_content_tasks.append(self._get_full_file_content_from_graph(node_id, graph_engine))
                      fetch_content_indices[len(fetch_content_tasks)-1] = node_id
                 else: logger.warning(f"Plan requested full content but missing node_id: {node_req_dict}")

        # --- 2. Plan: Execute additional vector search queries ---
        additional_queries = list(set(plan_dict.get("additional_search_queries", [])))
        query_tasks = []
        if additional_queries:
             logger.info(f"Planning {len(additional_queries)} additional vector searches.")
             vector_filter = self._create_vector_filter(datasets)
             query_tasks = [self._perform_vector_search(vector_engine, q, 5, vector_filter) for q in additional_queries]

        # --- 3. Plan: Execute graph traversals ---
        relationships_to_explore_dicts = plan_dict.get("graph_relationships_to_explore", [])
        traversal_tasks = []
        if relationships_to_explore_dicts:
             logger.info(f"Planning {len(relationships_to_explore_dicts)} graph traversals.")
             for rel_req_dict in relationships_to_explore_dicts:
                 # request_model = GraphRelationshipSpec(**rel_req_dict) # Validate if needed
                 traversal_tasks.append(self._perform_graph_traversal(graph_engine, rel_req_dict))

        # --- Execute all planned tasks concurrently ---
        gathered_results = await asyncio.gather(
            asyncio.gather(*fetch_content_tasks, return_exceptions=True),
            asyncio.gather(*query_tasks, return_exceptions=True),
            asyncio.gather(*traversal_tasks, return_exceptions=True),
            return_exceptions=True
        )
        if isinstance(gathered_results, Exception):
            logger.error(f"Critical error gathering plan execution results: {gathered_results}")
            enhanced_context["error"] = f"Failed plan execution: {gathered_results}"
            return enhanced_context # Return context as is

        # --- Process results using helpers ---
        fetched_contents_results = gathered_results[0]
        query_results_lists = gathered_results[1]
        traversal_results_lists = gathered_results[2]

        retrieved_content_count = self._process_fetched_content(fetched_contents_results, fetch_content_indices, enhanced_context)
        retrieved_query_count = await self._process_additional_queries(query_results_lists, enhanced_context, datasets, current_relevant_ids)
        explored_relationships_count = self._process_traversal_results(traversal_results_lists, enhanced_context, datasets, current_relevant_ids)

        # Final deduplication and sorting
        enhanced_context["relevant_files"] = self._deduplicate_and_sort_results(enhanced_context["relevant_files"], self.max_final_results)
        enhanced_context["out_of_scope_results"] = self._deduplicate_and_sort_results(enhanced_context["out_of_scope_results"], self.max_out_of_scope_results)

        duration = time.time() - start_time
        logger.info(f"Full plan execution completed in {duration:.2f}s. Content: {retrieved_content_count}, Query Add: {retrieved_query_count}, Graph Add: {explored_relationships_count}.")
        return enhanced_context


    # --- Stage 4: Comprehensive Response Generation (Using Pydantic) ---
    # MODIFIED: Fetches types internally again
    async def _generate_comprehensive_response(self, query: str, context: Dict[str, Any], datasets: List[str]) -> Dict[str, Any]:
        """ Generates the final, structured response using enhanced context and Pydantic. """
        logger.info("Generating comprehensive response...")
        start_time = time.time()
        llm_client = get_llm_client()
        graph_engine = await get_graph_engine() # Needed for type fetching

        # --- Get Combined Type Vocabulary (FETCHED HERE) ---
        # Use datasets from the context if available, otherwise from args
        current_datasets = context.get("datasets", datasets)
        dynamic_types = await self._get_dynamic_type_vocabulary(current_datasets, graph_engine)
        static_nodes, static_edges = self._get_static_types_for_datasets(current_datasets)
        available_node_types = sorted(list(set(dynamic_types.get("node_types", []) + static_nodes)))
        available_edge_types = sorted(list(set(dynamic_types.get("edge_types", []) + static_edges)))

        # Limit context size
        limited_relevant_files = sorted(context.get("relevant_files", []), key=lambda x: x.get("relevance_score", 0), reverse=True)[:self.max_final_results]

        # Prepare cleaned results and relationship summary
        results_for_prompt = self._clean_results_for_llm(limited_relevant_files)
        relationship_summary = self._summarize_relationships(limited_relevant_files)

        prompt_context = {
            "query": query,
            "datasets": ", ".join(sorted(current_datasets)),
            "results": results_for_prompt,
            "analysis_notes": context.get("analysis_notes", "N/A"),
            "out_of_scope_count": len(context.get("out_of_scope_results", [])),
            "has_out_of_scope": len(context.get("out_of_scope_results", [])) > 0,
            "relationship_summary": relationship_summary,
            "available_node_types": ", ".join(available_node_types),
            "available_edge_types": ", ".join(available_edge_types)
        }

        try:
            system_prompt = await render_prompt(self.system_prompt_path, prompt_context)
            user_prompt = await render_prompt(self.user_prompt_path, prompt_context)
        except Exception as e:
            logger.error(f"Error rendering final prompts: {e}")
            system_prompt = "You are a helpful code assistant..."
            user_prompt = f"Summarize findings for query: {query}..."

        # Use FinalSummary Pydantic model
        try:
            summary_model_instance: FinalSummary = await llm_client.acreate_structured_output(
                user_prompt, system_prompt, response_model=FinalSummary
            )
            summary_response = summary_model_instance.dict()

            # Format into markdown
            formatted_summary = f"# Code Analysis: {query}\n\n"
            sections = [("Overview", "overview"), ("Key Components", "key_components"), ("Implementation Details", "implementation_details"), ("Code Relationships", "code_relationships"), ("Design Patterns", "pattern_identification"), ("Technical Considerations", "technical_considerations"), ("Navigation Guidance", "navigation_guidance")]
            for title, key in sections:
                content = summary_response.get(key)
                if content and isinstance(content, str) and content.strip() and "N/A" not in content.lower() and "not provided" not in content.lower() and "not evident" not in content.lower():
                    formatted_summary += f"## {title}\n{content.strip()}\n\n"
            suggestions = summary_response.get("follow_up_suggestions")
            if suggestions and isinstance(suggestions, list) and any(s.strip() for s in suggestions if isinstance(s, str)):
                 formatted_summary += "## Follow-up Questions\n"
                 for i, s in enumerate(suggestions):
                     if s and isinstance(s, str) and s.strip(): formatted_summary += f"{i+1}. {s.strip()}\n"

            duration = time.time() - start_time
            logger.info(f"Comprehensive response generated successfully in {duration:.2f}s.")
            final_relevant_files = self._clean_results_for_output(limited_relevant_files)
            final_out_of_scope = self._clean_results_for_output(context.get("out_of_scope_results", []))
            return {"summary": formatted_summary.strip(), "status": "success", "relevant_files": final_relevant_files, "out_of_scope_results": final_out_of_scope}

        except ValidationError as e: logger.error(f"LLM output failed Pydantic validation for FinalSummary: {e}"); status, error_msg = "error_llm_validation", f"Validation Error: {e}"
        except Exception as e: logger.exception(f"LLM Error generating response: {str(e)}"); status, error_msg = "error_llm_call", f"LLM Error: {e}"

        # Fallback on error
        duration = time.time() - start_time
        logger.info(f"Response generation failed after {duration:.2f}s.")
        fallback_summary = f"Found {len(limited_relevant_files)} relevant elements for query: '{query}'.\n{error_msg}\n"
        if limited_relevant_files:
            fallback_summary += "Key elements:\n"
            for f in limited_relevant_files[:3]: fallback_summary += f"- {self._get_path_from_id(f.get(self.node_id_prop))} ({f.get(self.node_type_prop, '?')})\n" # Use helper
        final_relevant_files = self._clean_results_for_output(limited_relevant_files)
        final_out_of_scope = self._clean_results_for_output(context.get("out_of_scope_results", []))
        return {"summary": fallback_summary, "status": status, "relevant_files": final_relevant_files, "out_of_scope_results": final_out_of_scope}


    # --- Helper Methods ---

    # _clean_results_for_llm - Uses ID parsing
    def _clean_results_for_llm(self, results: List[Dict]) -> List[Dict]:
        """ Prepares results for sending to LLM, parsing ID, removing internal flags. """
        cleaned_results = []
        keys_to_remove = ["_might_need_full_content", "_fetched_full_content", "_raw_payload", "_traversal_reason", "_traversal_source_node_id", "_traversal_relationship_type", "is_in_scope", "source", "_graph_node_properties", "vector_id", self.node_chunk_prop]
        for res in results:
             res_copy = res.copy()
             node_id = res_copy.get(self.node_id_prop)
             path, name = self._parse_node_id(node_id) # Parse here
             res_copy["file_path"] = path # Add parsed path
             res_copy["name"] = name     # Add parsed name
             for key in keys_to_remove: res_copy.pop(key, None)
             if "relevant_chunk" in res_copy and len(res_copy["relevant_chunk"]) > 1000: res_copy["relevant_chunk"] = res_copy["relevant_chunk"][:1000] + "..."
             cleaned_results.append(res_copy)
        return cleaned_results

    # _clean_results_for_output - Uses ID parsing
    def _clean_results_for_output(self, results: List[Dict]) -> List[Dict]:
        """ Removes internal flags before returning results to user, parsing ID. """
        cleaned_results = []
        keys_to_remove = ["_might_need_full_content", "_fetched_full_content", "_raw_payload", "_traversal_reason", "_traversal_source_node_id", "_traversal_relationship_type", "is_in_scope", "source", "_graph_node_properties", "vector_id", self.node_chunk_prop] # Keep relevant_chunk
        for res in results:
             res_copy = res.copy()
             node_id = res_copy.get(self.node_id_prop)
             path, name = self._parse_node_id(node_id) # Parse here
             res_copy["file_path"] = path # Add parsed path
             res_copy["name"] = name     # Add parsed name
             for key in keys_to_remove: res_copy.pop(key, None)
             cleaned_results.append(res_copy)
        return cleaned_results

    # _deduplicate_and_sort_results - Uses node_id_prop
    def _deduplicate_and_sort_results(self, results: List[Dict], max_count: int) -> List[Dict]:
        """ Removes duplicates based on node_id_prop and sorts by relevance score. """
        # ... (Logic is the same) ...
        if not results: return []
        unique_results_dict = OrderedDict()
        for file_info in results:
            item_id = file_info.get(self.node_id_prop)
            if not item_id: continue # Skip if no ID
            current_score = file_info.get("relevance_score", 0)
            if item_id not in unique_results_dict: unique_results_dict[item_id] = file_info
            else:
                if current_score > unique_results_dict[item_id].get("relevance_score", 0): unique_results_dict[item_id] = file_info
        sorted_unique = sorted(unique_results_dict.values(), key=lambda x: x.get("relevance_score", 0), reverse=True)
        return sorted_unique[:max_count]


    # _parse_and_validate_line_range - No changes needed
    def _parse_and_validate_line_range(self, start_line: Any, end_line: Any, text_chunk: str = "") -> Dict[str, Optional[int]]:
        # ... (Logic is the same) ...
        s_line, e_line = None, None
        try: s_line = int(start_line) if start_line is not None and str(start_line).isdigit() else None
        except (ValueError, TypeError): pass
        try: e_line = int(end_line) if end_line is not None and str(end_line).isdigit() else None
        except (ValueError, TypeError): pass
        if s_line is not None and s_line < 0: s_line = None
        if e_line is not None and e_line < 0: e_line = None
        if s_line is not None and e_line is not None and s_line > e_line: s_line, e_line = None, None
        if s_line is not None and e_line is None and text_chunk:
             num_lines_in_chunk = text_chunk.count('\n')
             e_line = s_line + num_lines_in_chunk
        return {"start": s_line, "end": e_line}

    # _extract_relevant_chunk - No changes needed
    def _extract_relevant_chunk(self, full_chunk_text: str, query: str, max_lines: int = 30) -> str:
        # ... (Logic is the same) ...
        if not full_chunk_text or not isinstance(full_chunk_text, str): return ""
        lines = full_chunk_text.splitlines(); total_lines = len(lines)
        if total_lines == 0: return ""
        if total_lines <= max_lines: return full_chunk_text
        query_terms = set(term.lower() for term in re.findall(r'\b\w{3,}\b', query.lower()))
        if not query_terms and query.strip(): query_terms = set(query.lower().split())
        if not query_terms: return "\n".join(lines[:max_lines]) + ("\n..." if total_lines > max_lines else "")
        line_scores = [sum(1 for term in query_terms if term in line.lower()) for line in lines]
        best_score, best_start_index = -1, 0
        current_window_score = sum(line_scores[:min(max_lines, total_lines)])
        if current_window_score >= 0: best_score, best_start_index = current_window_score, 0
        for i in range(max_lines, total_lines):
            current_window_score += line_scores[i] - line_scores[i - max_lines]
            if current_window_score > best_score: best_score, best_start_index = current_window_score, i - max_lines + 1
        if best_score <= 0: return "\n".join(lines[:max_lines]) + "\n..."
        start_idx, end_idx = best_start_index, min(total_lines, best_start_index + max_lines)
        extracted_lines = lines[start_idx:end_idx]
        prefix = "...\n" if start_idx > 0 else ""
        suffix = "\n..." if end_idx < total_lines else ""
        return prefix + "\n".join(extracted_lines) + suffix


    # _get_dynamic_type_vocabulary - No changes needed (uses canonical props)
    async def _get_dynamic_type_vocabulary(self, datasets: List[str], graph_engine: GraphEngine) -> Dict[str, List[str]]:
        """ Fetches distinct node and edge types from the graph, scoped by dataset paths. """
        # ... (Logic is the same, relies on self.node_dataset_path_prop, self.node_type_prop, self.edge_type_prop) ...
        if not datasets: return {"node_types": [], "edge_types": []}
        cache_key = "vocab:" + ",".join(sorted(datasets))
        if cache_key in self.type_vocabulary_cache:
            cached_data, timestamp = self.type_vocabulary_cache[cache_key]
            if time.time() - timestamp < self.type_cache_ttl_seconds:
                logger.debug(f"Type vocabulary cache hit for datasets: {datasets}")
                self.type_vocabulary_cache.move_to_end(cache_key); return cached_data
            else: logger.debug(f"Type vocabulary cache expired"); del self.type_vocabulary_cache[cache_key]
        logger.debug(f"Type vocabulary cache miss. Querying graph.")
        node_types, edge_types = [], []
        try:
            params = {"datasets": datasets}
            node_cypher = f"MATCH (n) WHERE n.`{self.node_dataset_path_prop}` IN $datasets AND n.`{self.node_type_prop}` IS NOT NULL RETURN DISTINCT n.`{self.node_type_prop}` AS nodeType LIMIT {self.dynamic_node_types_top_n}"
            node_result = await graph_engine.graph_db.execute_query(node_cypher, params)
            if node_result and node_result[0].data(): node_types = [r['nodeType'] for r in node_result[0].data() if r.get('nodeType')]
            if self.edge_type_prop: edge_cypher = f"MATCH (n)-[r]->(m) WHERE n.`{self.node_dataset_path_prop}` IN $datasets AND r.`{self.edge_type_prop}` IS NOT NULL RETURN DISTINCT r.`{self.edge_type_prop}` AS edgeType LIMIT {self.dynamic_edge_types_top_n}"
            else: edge_cypher = f"MATCH (n)-[r]->(m) WHERE n.`{self.node_dataset_path_prop}` IN $datasets RETURN DISTINCT type(r) AS edgeType LIMIT {self.dynamic_edge_types_top_n}"
            edge_result = await graph_engine.graph_db.execute_query(edge_cypher, params)
            if edge_result and edge_result[0].data(): edge_types = [r['edgeType'] for r in edge_result[0].data() if r.get('edgeType')]
        except Exception as e: logger.exception(f"Failed to query dynamic type vocabulary: {e}"); return {"node_types": [], "edge_types": []}
        vocabulary = {"node_types": sorted(list(set(node_types))), "edge_types": sorted(list(set(edge_types)))}
        if len(self.type_vocabulary_cache) >= self.type_cache_max_size:
            lru_key, _ = self.type_vocabulary_cache.popitem(last=False); logger.debug(f"Type cache full. Removed {lru_key}")
        self.type_vocabulary_cache[cache_key] = (vocabulary, time.time())
        logger.debug(f"Stored type vocabulary in cache.")
        return vocabulary


    # _get_static_types_for_datasets - No changes needed
    def _get_static_types_for_datasets(self, datasets: List[str]) -> Tuple[List[str], List[str]]:
        """ Retrieves static node and edge types from the loaded map. """
        # ... (Logic is the same) ...
        static_nodes, static_edges = set(), set()
        if not self.static_types_map: return [], []
        for dpath in datasets:
            if dpath in self.static_types_map:
                types_data = self.static_types_map[dpath]
                static_nodes.update(types_data.get("static_node_types", []))
                static_edges.update(types_data.get("static_edge_types", []))
        return sorted(list(static_nodes)), sorted(list(static_edges))


    # _summarize_relationships - Uses ID parsing
    def _summarize_relationships(self, relevant_files: List[Dict]) -> str:
        """ Creates a simple text summary of relationships found via traversal. """
        summary_lines = []
        for file_info in relevant_files:
             if file_info.get("source") == "graph_traversal":
                 source_node_id = file_info.get("_traversal_source_node_id", "Unknown")
                 rel_type = file_info.get("_traversal_relationship_type", "UNKNOWN_REL")
                 target_id = file_info.get(self.node_id_prop, "???")
                 target_path, target_name = self._parse_node_id(target_id) # Parse target ID
                 reason = file_info.get("_traversal_reason", "")
                 display_name = f"`{target_name}` in `{os.path.basename(target_path)}`" if target_name and target_path else f"`{target_id}`"
                 summary_line = f"- Found related item {display_name} (ID: ...{target_id[-8:]})"
                 details = []
                 if rel_type != "UNKNOWN_REL": details.append(f"Rel: {rel_type}")
                 # if source_node_id != "Unknown": details.append(f"From: ...{source_node_id[-8:]}") # Maybe too noisy
                 # if reason: details.append(f"Reason: {reason}")
                 if details: summary_line += f" ({', '.join(details)})"
                 summary_lines.append(summary_line)
        if not summary_lines: return "No specific code relationships were explicitly explored."
        max_summary_lines = 7
        summary = "Relationships identified via graph traversal:\n" + "\n".join(summary_lines[:max_summary_lines])
        if len(summary_lines) > max_summary_lines: summary += f"\n... (and {len(summary_lines) - max_summary_lines} more)"
        return summary

    # _create_vector_filter - No changes needed (uses dataset prop)
    def _create_vector_filter(self, datasets: List[str]) -> Optional[Any]:
        """ Creates a filter for vector search based on dataset paths. (Qdrant example) """
        # ... (Logic is the same) ...
        if not datasets: return None
        try:
            from qdrant_client.http import models as rest
            metadata_key = f"metadata.{self.node_dataset_path_prop}"
            return rest.Filter(should=[rest.FieldCondition(key=metadata_key, match=rest.MatchValue(value=path)) for path in datasets])
        except ImportError: raise NotImplementedError("Vector filtering requires Qdrant client.")
        except Exception as e: raise NotImplementedError(f"Filter creation failed: {e}")


    # --- Content Fetch, Detail Fetch, Traversal Helpers ---
    # _get_full_file_content_from_graph - Uses canonical node_id_prop, node_chunk_prop
    async def _get_full_file_content_from_graph(self, node_id: str, graph_engine: GraphEngine) -> Optional[str]:
        """ Gets full chunk content from the graph using the node ID. """
        # ... (Logic is the same) ...
        if not node_id: return None; logger.debug(f"Fetching content for node: {node_id}")
        try:
            cypher = f"MATCH (n {{{self.node_id_prop}: $node_id}}) WHERE n.`{self.node_chunk_prop}` IS NOT NULL RETURN n.`{self.node_chunk_prop}` AS chunk_content LIMIT 1"
            params = {"node_id": node_id}
            result = await graph_engine.graph_db.execute_query(cypher, params)
            if result and result[0].data(): content = result[0].data()[0].get('chunk_content'); return str(content) if content else None
        except Exception as e: logger.exception(f"Error getting chunk content for node {node_id}: {e}")
        return None

    # _get_details_for_id - Uses node_id_prop, calls _standardize_graph_node
    async def _get_details_for_id(self, node_id: str, graph_engine: GraphEngine) -> Optional[Dict]:
        """ Gets all canonical properties for a given node ID from the graph. """
        # ... (Logic is the same) ...
        if not node_id: return None; logger.debug(f"Getting details for node: {node_id}")
        try:
            cypher = f"MATCH (n {{{self.node_id_prop}: $node_id}}) RETURN n LIMIT 1"
            params = {self.node_id_prop: node_id}
            result = await graph_engine.graph_db.execute_query(cypher, params)
            if result and result[0].data():
                 record = result[0].data()[0]
                 if 'n' in record:
                     node_obj = record['n']
                     node_data = dict(node_obj.items()) if hasattr(node_obj, 'items') else node_obj if isinstance(node_obj, dict) else None
                     if node_data:
                          standardized_node = await self._standardize_graph_node(node_data, f"details fetch for {node_id}", graph_engine)
                          if standardized_node:
                               standardized_node["relevance_score"] = 0.85; standardized_node["source"] = "graph_direct_fetch"
                               return standardized_node
        except Exception as e: logger.exception(f"Graph detail lookup failed for ID {node_id}: {e}")
        logger.warning(f"Could not find details for node ID in graph: {node_id}")
        return None


    # _perform_graph_traversal - Uses canonical props
    async def _perform_graph_traversal(self, graph_engine: GraphEngine, request: Dict) -> List[Dict]:
        """ Performs a graph traversal based on the request dict. """
        # ... (Logic is the same, uses node_id_prop, edge_type_prop) ...
        node_id = request.get(self.node_id_prop)
        rel_type_requested = request.get("relationship_type")
        direction = request.get("direction", "BOTH").upper()
        max_hops = request.get("max_hops", 1)
        reason = request.get("reason", "No reason provided")
        if not node_id: return []
        logger.debug(f"Performing graph traversal from node '{node_id}', Rel: '{rel_type_requested or 'ANY'}', Dir: {direction}, Hops: {max_hops}.")

        rel_label_cypher, rel_prop_filter = "", ""
        if rel_type_requested and isinstance(rel_type_requested, str) and rel_type_requested.strip():
            if self.edge_type_prop: rel_prop_filter = f"WHERE r.`{self.edge_type_prop}` = $rel_type"
            else: rel_label_cypher = f":`{rel_type_requested}`"
        if direction == "OUTGOING": rel_pattern = f"-[r{rel_label_cypher}]->"
        elif direction == "INCOMING": rel_pattern = f"<-[r{rel_label_cypher}]-"
        else: rel_pattern = f"-[r{rel_label_cypher}]-"
        try: max_hops = max(1, int(max_hops))
        except (ValueError, TypeError): max_hops = 1
        hops_pattern = f"*1..{max_hops}"

        cypher = f""" MATCH (start_node {{{self.node_id_prop}: $start_node_id}}) MATCH path = (start_node){rel_pattern}{hops_pattern}(neighbor) {rel_prop_filter} WHERE neighbor.`{self.node_id_prop}` <> $start_node_id WITH neighbor, relationships(path)[-1] AS last_rel RETURN DISTINCT neighbor, last_rel LIMIT {self.graph_traversal_neighbor_limit} """
        params = {"start_node_id": node_id}
        if rel_prop_filter: params["rel_type"] = rel_type_requested

        try:
            raw_results = await graph_engine.graph_db.execute_query(cypher, params)
            neighbors_data = []
            if raw_results and raw_results[0].data():
                 for record in raw_results[0].data():
                      if 'neighbor' in record:
                           node_obj, rel_obj = record['neighbor'], record.get('last_rel')
                           properties = dict(node_obj.items()) if hasattr(node_obj, 'items') else node_obj if isinstance(node_obj, dict) else {}
                           if not properties: continue
                           properties['_traversal_source_node_id'], properties['_traversal_reason'] = node_id, reason
                           traversed_rel_type = None
                           if rel_obj:
                               if hasattr(rel_obj, 'properties') and self.edge_type_prop in rel_obj.properties: traversed_rel_type = rel_obj.properties[self.edge_type_prop]
                               elif isinstance(rel_obj, dict) and self.edge_type_prop in rel_obj: traversed_rel_type = rel_obj[self.edge_type_prop]
                               elif hasattr(rel_obj, 'type'): traversed_rel_type = rel_obj.type
                           properties['_traversal_relationship_type'] = traversed_rel_type or "UNKNOWN"
                           neighbors_data.append(properties)
            if not neighbors_data: return []
            processed_neighbors = await self._process_graph_results(neighbors_data, f"traversal from {node_id}", graph_engine)
            for n in processed_neighbors: n["relevance_score"], n["source"] = 0.80, "graph_traversal"
            logger.debug(f"Graph traversal found {len(processed_neighbors)} neighbors for node {node_id}.")
            return processed_neighbors
        except Exception as e:
            logger.exception(f"Error during graph traversal query execution for request {request}: {e}")
            return []


    # MODIFIED: Uses ID parsing, passes query for snippet extraction
    async def _standardize_graph_node(self, node_data: Dict, source_description: str, graph_engine: Optional[GraphEngine], query: str = "") -> Optional[Dict]:
        """ Converts raw graph node dict to canonical format, parsing ID, fetching content if needed. """
        try:
            node_id = node_data.get(self.node_id_prop)
            if not node_id: return None # ID is essential

            file_path, node_name = self._parse_node_id(node_id) # Parse ID

            dataset_path = node_data.get(self.node_dataset_path_prop)
            text_chunk = node_data.get(self.node_chunk_prop, "")
            node_type = node_data.get(self.node_type_prop)
            start_line = node_data.get(self.node_start_line_prop)
            end_line = node_data.get(self.node_end_line_prop)
            timestamp = node_data.get(self.node_timestamp_prop)
            project_id = node_data.get(self.project_id_prop_in_graph) # Check graph prop name

            # Mandatory checks
            if not file_path: file_path = "Unknown"
            if not dataset_path:
                 logger.error(f"CRITICAL: Graph node {node_id} missing mandatory '{self.node_dataset_path_prop}'. Skipping.")
                 return None

            fetched_full_content = bool(text_chunk)
            if graph_engine and (not text_chunk or len(text_chunk.splitlines()) < 5):
                 full_content = await self._get_full_file_content_from_graph(node_id, graph_engine)
                 if full_content: text_chunk, fetched_full_content = full_content, True

            internal_keys = { self.node_id_prop, self.node_chunk_prop, self.node_dataset_path_prop, self.node_type_prop, self.node_timestamp_prop, self.node_start_line_prop, self.node_end_line_prop, self.node_scope_prop, self.project_id_prop_in_graph, '_traversal_source_node_id', '_traversal_reason', '_traversal_relationship_type'}
            other_props = {k: v for k, v in node_data.items() if k not in internal_keys and not k.startswith('_')}

            item_info = {
                self.node_id_prop: str(node_id),
                "file_path": file_path, # Parsed
                "name": node_name,     # Parsed
                self.node_chunk_prop: text_chunk,
                "relevant_chunk": self._extract_relevant_chunk(text_chunk, query), # Pass query
                self.node_dataset_path_prop: dataset_path,
                self.node_type_prop: node_type,
                self.node_timestamp_prop: timestamp,
                "line_range": self._parse_and_validate_line_range(start_line, end_line, text_chunk),
                "project_id": project_id,
                "relevance_score": float(node_data.get("score", 0.75)),
                "source": node_data.get("source", "graph"),
                "_fetched_full_content": fetched_full_content,
                "_graph_node_properties": other_props,
                "_traversal_source_node_id": node_data.get('_traversal_source_node_id'),
                "_traversal_reason": node_data.get('_traversal_reason'),
                "_traversal_relationship_type": node_data.get('_traversal_relationship_type'),
            }
            return {k: v for k, v in item_info.items() if v is not None}
        except Exception as e:
            logger.exception(f"Error standardizing graph node {node_data.get(self.node_id_prop)} from '{source_description}': {e}")
            return None
