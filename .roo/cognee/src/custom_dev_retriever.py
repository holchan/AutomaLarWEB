# custom_dev_retriever.py
from typing import Any, Dict, List, Optional, Union
import json
import re
import time
from uuid import UUID
import asyncio

# Ensure these base classes and functions exist in your Cognee installation path
try:
    from cognee.modules.retrieval.base_retriever import BaseRetriever
    from cognee.infrastructure.databases.vector import get_vector_engine
    from cognee.infrastructure.databases.graph import get_graph_engine, GraphEngine # Import GraphEngine type hint
    from cognee.infrastructure.llm.get_llm_client import get_llm_client
    from cognee.infrastructure.llm.prompts.render_prompt import render_prompt
    from cognee.shared.logging_utils import get_logger
except ImportError as e:
    print(f"CRITICAL Error importing Cognee components: {e}")
    print("Please ensure Cognee is installed correctly and accessible in the Python environment.")
    raise

logger = get_logger(__name__)

# --- Context Cache ---
class ContextCache:
    """Simple in-memory cache for retrieval results with TTL."""
    def __init__(self, max_size=50, ttl_seconds=600):
        self.cache = {}
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
        # Return a deep copy to prevent modification of cached object by reference
        try:
            return json.loads(json.dumps(self.cache[key]))
        except TypeError: # Handle potential non-serializable data if error occurs
             logger.warning(f"Could not deep copy cached item for key {key}. Returning direct reference.")
             return self.cache[key]


    def set(self, key, value):
        if len(self.cache) >= self.max_size and key not in self.cache:
            try:
                lru_key = min(self.access_times.items(), key=lambda item: item[1])[0]
                logger.debug(f"Cache full. Removing LRU key: {lru_key}")
                self.remove(lru_key)
            except ValueError: pass # Cache might be empty
        logger.debug(f"Setting cache for key: {key}")
        # Store a deep copy to prevent modification by reference
        try:
            self.cache[key] = json.loads(json.dumps(value))
        except TypeError:
            logger.warning(f"Could not deep copy value for cache key {key}. Storing direct reference.")
            self.cache[key] = value # Fallback to direct reference
        self.access_times[key] = time.time()

    def remove(self, key):
        if key in self.cache: del self.cache[key]
        if key in self.access_times: del self.access_times[key]
        logger.debug(f"Removed cache key: {key}")

# --- Custom Retriever (Metadata-First, Minimal Graph, Optional Traversal) ---
class DevCodeRetriever(BaseRetriever):
    """
    Developer-focused retriever using a multi-stage pipeline. Prioritizes reliable
    metadata from vector search. Uses the graph database for targeted content lookups
    and optional, LLM-planned relationship exploration.
    Requires configuration of vector collections and schema property names.
    """

    def __init__(
        self,
        # --- Prompt template paths ---
        system_prompt_path: str = "dev_code_retrieval_system.txt",
        user_prompt_path: str = "dev_code_retrieval_user.txt",
        analysis_system_prompt_path: str = "dev_code_analysis_prompt.txt",
        analysis_user_prompt_path: str = "dev_code_analysis_user_prompt.txt",

        # --- Schema & Configuration (VERIFY AND UPDATE THESE) ---
        vector_collections: List[str] = ["CodeSnippets"],
        id_prop: str = "id",
        path_prop: str = "file_path",
        dataset_prop: str = "dataset",
        content_prop: str = "content",
        start_line_prop: str = "start_line",
        end_line_prop: str = "end_line",
        name_prop: str = "name", # Optional: Name of function/class if available in metadata/graph

        node_id_prop_in_graph: str = "id",
        node_path_prop_in_graph: str = "path",
        node_content_prop_in_graph: str = "content",
        node_dataset_prop_in_graph: str = "dataset",
        node_type_prop_in_graph: str = "node_type", # Assumed graph property storing 'FUNCTION', 'CLASS' etc.
        project_id_prop_in_graph: Optional[str] = "project_id",

        file_node_label: str = "FILE", # Assumed graph label for file nodes

        contains_rel_type: str = "CONTAINS",
        calls_rel_type: str = "CALLS",
        imports_rel_type: str = "IMPORTS",
        inherits_rel_type: str = "INHERITS_FROM",
        implements_rel_type: str = "IMPLEMENTS",
        defines_rel_type: str = "DEFINES",
        references_rel_type: str = "REFERENCES",

        static_node_types: List[str] = ["FILE", "MODULE", "CLASS", "FUNCTION", "VARIABLE"],
        static_edge_types: List[str] = ["DEFINES", "CALLS", "INHERITS", "IMPORTS", "REFERENCES"],
        dynamic_types_top_n: int = 10,

        # --- Retrieval limits ---
        max_vector_results: int = 25,
        max_final_results: int = 10,
        max_out_of_scope_results: int = 5,
        graph_traversal_neighbor_limit: int = 10,

        # --- Project ID (Optional) ---
        project_id: Optional[str] = None,
    ):
        # Store prompt paths
        self.system_prompt_path = system_prompt_path
        self.user_prompt_path = user_prompt_path
        self.analysis_system_prompt_path = analysis_system_prompt_path
        self.analysis_user_prompt_path = analysis_user_prompt_path

        # Store retrieval limits
        self.max_vector_results = max_vector_results
        self.max_final_results = max_final_results
        self.max_out_of_scope_results = max_out_of_scope_results
        self.graph_traversal_neighbor_limit = graph_traversal_neighbor_limit

        # Store schema configuration
        self.vector_collections = vector_collections
        self.id_prop = id_prop
        self.path_prop = path_prop
        self.dataset_prop = dataset_prop
        self.content_prop = content_prop
        self.start_line_prop = start_line_prop
        self.end_line_prop = end_line_prop
        self.name_prop = name_prop

        self.file_node_label = file_node_label
        self.node_id_prop_in_graph = node_id_prop_in_graph
        self.node_path_prop_in_graph = node_path_prop_in_graph
        self.node_content_prop_in_graph = node_content_prop_in_graph
        self.node_dataset_prop_in_graph = node_dataset_prop_in_graph
        self.node_type_prop_in_graph = node_type_prop_in_graph
        self.project_id = project_id
        self.project_id_prop = project_id_prop_in_graph

        # Store relationship types mapping and static types
        self.relationship_types = {
            "CONTAINS": contains_rel_type, "CALLS": calls_rel_type, "IMPORTS": imports_rel_type,
            "INHERITS": inherits_rel_type, "IMPLEMENTS": implements_rel_type,
            "DEFINES": defines_rel_type, "REFERENCES": references_rel_type
        }
        self.relationship_types = {k: v for k, v in self.relationship_types.items() if v} # Filter None
        self.static_node_types = static_node_types
        self.static_edge_types = static_edge_types
        self.dynamic_types_top_n = dynamic_types_top_n

        self.context_cache = ContextCache()
        logger.info("DevCodeRetriever initialized (Metadata-First, Graph Traversal Enabled).")
        # Log critical assumptions
        logger.info(f" Assumptions - Vector Collections: {self.vector_collections}")
        logger.info(f" Assumptions - Metadata Props: id={self.id_prop}, path={self.path_prop}, dataset={self.dataset_prop}, content={self.content_prop}, start={self.start_line_prop}, end={self.end_line_prop}, name={self.name_prop}")
        logger.info(f" Assumptions - Graph Props: id={self.node_id_prop_in_graph}, path={self.node_path_prop_in_graph}, content={self.node_content_prop_in_graph}, dataset={self.node_dataset_prop_in_graph}, type={self.node_type_prop_in_graph}, project_id={self.project_id_prop}")
        logger.info(f" Assumptions - Graph File Label: {self.file_node_label}")
        logger.info(f" Assumptions - Configured Graph Relationships: {list(self.relationship_types.values())}")
        logger.info(f" Assumptions - Static Node Types: {self.static_node_types}")
        logger.info(f" Assumptions - Static Edge Types: {self.static_edge_types}")
        if self.project_id_prop and not self.project_id:
            logger.warning(f"Retriever configured to use graph property '{self.project_id_prop}' but no project_id provided.")


    # --------------------------------------------------------------------------
    # Main Orchestration Method
    # --------------------------------------------------------------------------
    async def get_completion(
        self, query: str, context: Optional[Dict[str, Any]] = None, datasets: List[str] = None
    ) -> Dict[str, Any]:
        """Orchestrates the multi-stage retrieval pipeline."""
        trace = []
        start_time = time.time()
        logger.info(f"Starting get_completion for query: '{query}'")
        final_response = {}

        try:
            # STAGE 1: Initial Context Retrieval (Vector Search + Metadata Extraction)
            stage_start_time = time.time()
            trace.append({"stage": "initial_retrieval", "status": "started"})
            if context is None:
                cache_key = f"{query}:{','.join(sorted(datasets or []))}:{self.project_id or ''}"
                cached_context = self.context_cache.get(cache_key)
                if cached_context:
                    context = cached_context
                    trace[-1].update({"status": "completed", "source": "cache", "duration": time.time() - stage_start_time})
                else:
                    context = await self.get_context(query, datasets)
                    self.context_cache.set(cache_key, context)
                    trace[-1].update({"status": "completed", "source": "new", "duration": time.time() - stage_start_time})
            else:
                 context.setdefault("relevant_files", [])
                 context.setdefault("out_of_scope_results", [])
                 trace[-1].update({"status": "completed", "source": "provided", "duration": time.time() - stage_start_time})

            if not context.get("relevant_files"):
                logger.warning(f"No relevant files found for query: {query}")
                final_response = {"summary": f"No relevant results found for query: {query}", "relevant_files": [], "out_of_scope_results": context.get("out_of_scope_results", [])}
                return {**final_response, "trace": trace}

            # STAGE 2: Analysis Planning (Based on retrieved chunks/metadata)
            stage_start_time = time.time()
            trace.append({"stage": "analysis_planning", "status": "started"})
            analysis_plan = await self._analyze_and_plan(query, context)
            trace[-1].update({
                "status": "completed", "duration": time.time() - stage_start_time,
                "plan_details": {
                    "analysis_summary": analysis_plan.get("analysis", "")[:100] + "...",
                    "fetch_content_count": len(analysis_plan.get("additional_files_to_fetch_full_content", [])),
                    "additional_queries_count": len(analysis_plan.get("additional_search_queries", [])),
                    "relationships_count": len(analysis_plan.get("graph_relationships_to_explore", []))
                }
            })

            # STAGE 3: Enhanced Retrieval (Executes plan: files, queries, traversals)
            stage_start_time = time.time()
            trace.append({"stage": "enhanced_retrieval", "status": "started"})
            enhanced_context = await self._execute_retrieval_plan(
                analysis_plan, context, datasets, trace
            )
            trace[-1].update({
                "status": "completed", "duration": time.time() - stage_start_time,
                "total_relevant_files": len(enhanced_context.get("relevant_files", []))
            })

            # STAGE 4: Comprehensive Response Generation
            stage_start_time = time.time()
            trace.append({"stage": "response_generation", "status": "started"})
            final_response = await self._generate_comprehensive_response(
                query, enhanced_context
            )
            trace[-1].update({"status": "completed", "duration": time.time() - stage_start_time})

            end_time = time.time()
            logger.info(f"get_completion finished in {end_time - start_time:.2f} seconds.")
            return {**final_response, "trace": trace}

        except Exception as e:
            logger.exception(f"Critical error during get_completion for query '{query}': {str(e)}")
            final_response = {
                "summary": f"An error occurred while processing your query: {str(e)}",
                "relevant_files": context.get("relevant_files", []) if context else [],
                "out_of_scope_results": context.get("out_of_scope_results", []) if context else [],
            }
            error_trace_entry = {"stage": "error", "message": str(e)}
            if trace and trace[-1].get("stage") != "error": trace.append(error_trace_entry)
            elif not trace: trace = [error_trace_entry]
            return {**final_response, "trace": trace}


    # --------------------------------------------------------------------------
    # Stage 1: Initial Context Retrieval (Vector Search + Metadata Extraction)
    # --------------------------------------------------------------------------
    async def get_context(self, query: str, datasets: List[str] = None) -> Dict[str, Any]:
        """Performs initial vector search and extracts reliable metadata."""
        logger.info(f"Performing initial context retrieval for '{query}' in datasets: {datasets}")
        start_time = time.time()

        context = {"query": query, "datasets": datasets or [], "relevant_files": [], "out_of_scope_results": []}

        vector_engine = get_vector_engine()
        all_vector_results = []
        search_tasks = [
             vector_engine.search(collection, query, limit=self.max_vector_results, with_vector=False)
             for collection in self.vector_collections
        ]
        results_per_collection = await asyncio.gather(*search_tasks, return_exceptions=True)

        for i, result_list in enumerate(results_per_collection):
            collection_name = self.vector_collections[i]
            if isinstance(result_list, Exception): logger.error(f"Error searching {collection_name}: {result_list}")
            elif result_list: all_vector_results.extend(result_list)

        # Process Search Results (Extract reliable metadata)
        processed_files = {}
        processed_out_of_scope = {}
        processing_tasks = [ self._process_search_result(result, datasets, query) for result in all_vector_results ]
        processed_results = await asyncio.gather(*processing_tasks, return_exceptions=True)

        for proc_result in processed_results:
            if isinstance(proc_result, Exception) or proc_result is None: continue
            item_key = proc_result.get("vector_id") or proc_result.get("file_path")
            if not item_key: continue
            target_dict = processed_files if proc_result["is_in_scope"] else processed_out_of_scope
            if item_key not in target_dict or proc_result["relevance_score"] > target_dict[item_key].get("relevance_score", 0):
                 target_dict[item_key] = proc_result

        # Finalize context structure - Sort and limit
        context["relevant_files"] = self._deduplicate_and_sort_results(list(processed_files.values()), self.max_final_results)
        context["out_of_scope_results"] = self._deduplicate_and_sort_results(list(processed_out_of_scope.values()), self.max_out_of_scope_results)

        duration = time.time() - start_time
        logger.info(f"Initial context retrieval found {len(context['relevant_files'])} relevant files, {len(context['out_of_scope_results'])} out-of-scope in {duration:.2f}s.")
        return context

    async def _process_search_result(self, result, datasets, query) -> Optional[Dict]:
        """Helper to process a single vector search result and extract reliable metadata."""
        try:
            payload = result.payload or {}
            metadata = payload.get("metadata", {})

            file_path = metadata.get(self.path_prop) or payload.get(self.path_prop, "Unknown")
            node_id = metadata.get(self.id_prop) or payload.get(self.id_prop)
            dataset_name = metadata.get(self.dataset_prop) or payload.get(self.dataset_prop)
            content_snippet = payload.get(self.content_prop, "")
            start_line = metadata.get(self.start_line_prop) or payload.get(self.start_line_prop)
            end_line = metadata.get(self.end_line_prop) or payload.get(self.end_line_prop)

            if file_path == "Unknown" or not node_id: return None
            if not dataset_name: dataset_name = self._infer_dataset_from_path(file_path)

            is_in_scope = not datasets or (dataset_name and dataset_name in datasets)

            file_info = {
                "dataset": dataset_name or "Unknown",
                "file_path": file_path,
                "line_range": self._parse_and_validate_line_range(start_line, end_line, content_snippet),
                "snippet": self._get_relevant_snippet(content_snippet, query) if is_in_scope else "",
                "relevance_score": result.score,
                "vector_id": node_id,
                "is_in_scope": is_in_scope,
                "_might_need_full_content": is_in_scope and (not content_snippet or len(content_snippet.splitlines()) < 5)
            }
            return file_info
        except Exception as e:
            logger.exception(f"Error processing vector result {getattr(result, 'id', 'N/A')}: {str(e)}")
            return None

    async def _get_full_file_content_from_graph(self, node_id: str, graph_engine: GraphEngine) -> Optional[str]:
        """Gets full content from the graph using the node ID."""
        logger.debug(f"Attempting graph lookup for full content using node_id: {node_id}")
        if not node_id: return None
        try:
            # Assumes the node identified by node_id_prop_in_graph HAS the content
            # This query assumes the ID uniquely identifies the node we want content from
            cypher = f"""
            MATCH (n {{{self.node_id_prop_in_graph}: $node_id}})
            WHERE n.{self.node_content_prop_in_graph} IS NOT NULL
            RETURN n.{self.node_content_prop_in_graph} AS content
            LIMIT 1
            """
            params = {"node_id": node_id}

            result = await graph_engine.graph_db.execute_query(cypher, params)

            if result and result[0] and result[0].data():
                content = result[0].data()[0].get('content')
                if content:
                    logger.debug(f"Found content for node {node_id} (length: {len(content)}) via graph.")
                    return content
            logger.warning(f"Could not find node or content for {node_id} in graph.")
            return None
        except Exception as e:
            logger.exception(f"Error getting content from graph for node {node_id}: {e}")
            return None

    # --------------------------------------------------------------------------
    # Stage 2: Analysis Planning
    # --------------------------------------------------------------------------
    async def _analyze_and_plan(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyzes initial metadata/snippets and generates a retrieval plan."""
        logger.info(f"Creating analysis plan for query: '{query}'")
        llm_client = get_llm_client()
        graph_engine = await get_graph_engine()

        # --- Get Hybrid Type Vocabulary ---
        dynamic_types = await self._get_dynamic_type_vocabulary(context.get("datasets", []), graph_engine)
        available_node_types = sorted(list(set(self.static_node_types + dynamic_types["node_types"])))
        available_edge_types = sorted(list(set(self.static_edge_types + dynamic_types["edge_types"])))
        logger.debug(f"Using Node Types for Planning: {available_node_types}")
        logger.debug(f"Using Edge Types for Planning: {available_edge_types}")

        # Prepare summaries for the prompt context
        relevant_files_summary = [{
            "file_path": f.get("file_path"), "dataset": f.get("dataset"),
            "score": round(f.get("relevance_score", 0), 2), "id": f.get("vector_id")
        } for f in context.get("relevant_files", [])[:7]]

        out_of_scope_summary = [{
            "file_path": f.get("file_path"), "dataset": f.get("dataset"),
            "score": round(f.get("relevance_score", 0), 2)
        } for f in context.get("out_of_scope_results", [])[:3]]

        user_prompt_context = {
            "query": query,
            "relevant_files_summary": json.dumps(relevant_files_summary, indent=2),
            "out_of_scope_summary": json.dumps(out_of_scope_summary, indent=2),
            "out_of_scope_count": len(context.get("out_of_scope_results", [])),
            "available_node_types": ", ".join(available_node_types),
            "available_edge_types": ", ".join(available_edge_types)
        }

        try:
            system_prompt = await render_prompt(self.analysis_system_prompt_path, user_prompt_context)
            user_prompt = await render_prompt(self.analysis_user_prompt_path, user_prompt_context)
        except Exception as e:
            logger.error(f"Error rendering analysis prompts: {e}")
            system_prompt = "You are a code analysis planner."
            user_prompt = f"Analyze query '{query}' & plan retrieval."

        # Define the expected structure of the plan including graph traversal
        plan_schema = {
            "type": "object", "properties": {
                "analysis": {"type": "string", "description": "Brief assessment of initial results and knowledge gaps."},
                "additional_files_to_fetch_full_content": {"type": "array", "items": {"type": "object", "properties": {"file_path": {"type": "string"}, "vector_id": {"type": "string"}, "reason": {"type": "string"}}, "required": ["file_path", "vector_id", "reason"]}, "description": "Files needing full content retrieval."},
                "additional_search_queries": {"type": "array", "items": {"type": "string"}, "description": "New search queries for related concepts."},
                "graph_relationships_to_explore": {"type": "array", "items": {"type": "object", "properties": {
                    "vector_id": {"type": "string", "description": f"The '{self.id_prop}' of the node to start exploration from"},
                    "source_file": {"type": "string", "description": "The file path of the source node"},
                    # Use the combined list for the enum, filter out None if rel_type is mandatory
                    "relationship_type": {"type": ["string", "null"], "enum": available_edge_types + [None], "description": "Relationship type (e.g., CALLS, IMPORTS), or null/omit for any."},
                    "direction": {"type": "string", "enum": ["INCOMING", "OUTGOING", "BOTH"], "default": "BOTH", "description": "Direction of relationship."},
                    "max_hops": {"type": "integer", "default": 1, "description": "Maximum steps to traverse."},
                    "reason": {"type": "string", "description": "Why this traversal is needed."}},
                    "required": ["vector_id", "source_file", "direction", "reason"]},
                    "description": "Specific code relationships to explore starting from a known node ID."}
            }, "required": ["analysis"]
        }

        try:
            plan_response = await llm_client.create_structured_output(
                user_prompt, system_prompt, plan_schema, temperature=0.1
            )
            plan_response.setdefault("additional_files_to_fetch_full_content", [])
            plan_response.setdefault("additional_search_queries", [])
            plan_response.setdefault("graph_relationships_to_explore", [])
            logger.info(f"Analysis plan generated.")
            logger.debug(f"Plan details: {plan_response}")
            return plan_response
        except Exception as e:
            logger.exception(f"LLM Error generating analysis plan: {str(e)}")
            return {"analysis": f"Failed to generate plan: {e}", "additional_files_to_fetch_full_content": [], "additional_search_queries": [], "graph_relationships_to_explore": []}


    # --------------------------------------------------------------------------
    # Stage 3: Enhanced Retrieval (Files, Queries, Relationships)
    # --------------------------------------------------------------------------
    async def _execute_retrieval_plan(
        self,
        plan: Dict[str, Any],
        context: Dict[str, Any],
        datasets: List[str],
        trace: List[Dict]
    ) -> Dict[str, Any]:
        """Executes the retrieval plan (fetches full content, runs new queries, explores graph)."""
        logger.info("Executing retrieval plan...")
        start_time = time.time()
        enhanced_context = {
             "query": context["query"], "datasets": context["datasets"],
             "relevant_files": list(context.get("relevant_files", [])),
             "out_of_scope_results": list(context.get("out_of_scope_results", [])),
             "analysis_notes": plan.get("analysis", "")
        }
        current_relevant_ids = {rf.get("vector_id") for rf in enhanced_context["relevant_files"] if rf.get("vector_id")}

        graph_engine = await get_graph_engine()
        vector_engine = get_vector_engine()
        retrieved_content_count = 0
        retrieved_query_count = 0
        explored_relationships_count = 0

        # --- 1. Fetch full content for specified files ---
        files_to_fetch = plan.get("additional_files_to_fetch_full_content", [])
        if files_to_fetch:
            sub_stage_start = time.time()
            trace.append({"sub_stage": "full_content_retrieval", "status": "started", "files_requested": len(files_to_fetch)})
            fetch_tasks = [self._get_full_file_content_from_graph(file_req.get("vector_id"), graph_engine) for file_req in files_to_fetch if file_req.get("vector_id")]
            fetched_contents = await asyncio.gather(*fetch_tasks, return_exceptions=True)
            content_updated_count = 0
            for i, content in enumerate(fetched_contents):
                if isinstance(content, str) and content:
                    vector_id = files_to_fetch[i].get("vector_id")
                    for file_info in enhanced_context["relevant_files"]:
                        if file_info.get("vector_id") == vector_id:
                            logger.debug(f"Updating snippet with full content for {file_info['file_path']} (ID: {vector_id})")
                            file_info["snippet"] = content
                            file_info["line_range"] = self._parse_and_validate_line_range(None, None, content)
                            file_info["_fetched_full_content"] = True
                            content_updated_count += 1
                            break
                elif isinstance(content, Exception): logger.error(f"Error fetching full content for {files_to_fetch[i].get('vector_id')}: {content}")
            retrieved_content_count = content_updated_count
            trace[-1].update({"status": "completed", "content_updated_count": content_updated_count, "duration": time.time() - sub_stage_start})

        # --- 2. Execute additional search queries ---
        additional_queries = list(set(plan.get("additional_search_queries", [])))
        if additional_queries:
            sub_stage_start = time.time()
            trace.append({"sub_stage": "additional_queries", "status": "started", "queries": additional_queries})
            query_tasks = [self._perform_basic_search(add_query, datasets, limit=5) for add_query in additional_queries]
            query_results_lists = await asyncio.gather(*query_tasks, return_exceptions=True)
            detail_fetch_tasks = []
            processed_ids_in_query = set()
            files_added_this_stage = 0
            for i, basic_results_list in enumerate(query_results_lists):
                 query_text = additional_queries[i]
                 if isinstance(basic_results_list, Exception): logger.error(f"Error executing query '{query_text}': {basic_results_list}"); continue
                 for result in basic_results_list:
                      node_id = result.get("id")
                      if node_id and node_id not in processed_ids_in_query and node_id not in current_relevant_ids:
                           detail_fetch_tasks.append(self._get_details_for_id(node_id, graph_engine))
                           processed_ids_in_query.add(node_id)
            detailed_results = await asyncio.gather(*detail_fetch_tasks, return_exceptions=True)
            for file_info in detailed_results:
                 if isinstance(file_info, dict) and file_info:
                      if file_info["vector_id"] not in current_relevant_ids:
                           enhanced_context["relevant_files"].append(file_info)
                           current_relevant_ids.add(file_info["vector_id"])
                           files_added_this_stage += 1
                 elif isinstance(file_info, Exception): logger.error(f"Error fetching details via additional query: {file_info}")
            retrieved_query_count = files_added_this_stage
            trace[-1].update({"status": "completed", "files_added": files_added_this_stage, "duration": time.time() - sub_stage_start})

        # --- 3. Explore graph relationships ---
        relationships_to_explore = plan.get("graph_relationships_to_explore", [])
        if relationships_to_explore:
            sub_stage_start = time.time()
            trace.append({"sub_stage": "relationship_exploration", "status": "started", "relationships_planned": len(relationships_to_explore)})
            relation_tasks = [self._perform_graph_traversal(graph_engine, rel) for rel in relationships_to_explore]
            exploration_results_lists = await asyncio.gather(*relation_tasks, return_exceptions=True)
            nodes_added_count = 0
            for result_list in exploration_results_lists:
                if isinstance(result_list, list):
                    for file_info in result_list:
                         if file_info["vector_id"] not in current_relevant_ids:
                              enhanced_context["relevant_files"].append(file_info)
                              current_relevant_ids.add(file_info["vector_id"])
                              nodes_added_count += 1
                elif isinstance(result_list, Exception): logger.error(f"Error during relationship exploration task: {result_list}")
            explored_relationships_count = nodes_added_count
            trace[-1].update({"status": "completed", "nodes_added": nodes_added_count, "duration": time.time() - sub_stage_start})

        # Final deduplication and sorting before response generation
        enhanced_context["relevant_files"] = self._deduplicate_and_sort_results(
            enhanced_context["relevant_files"], self.max_final_results + 10 # Keep slightly more context temporarily
        )

        duration = time.time() - start_time
        logger.info(f"Enhanced retrieval completed in {duration:.2f}s. Updated {retrieved_content_count}, Added from Q: {retrieved_query_count}, Added from Graph: {explored_relationships_count}.")
        return enhanced_context

    async def _perform_graph_traversal(self, graph_engine: GraphEngine, request: Dict) -> List[Dict]:
        """Performs a graph traversal based on the request from the planning stage."""
        node_id = request.get("vector_id")
        rel_type = request.get("relationship_type") # Actual relationship name string
        direction = request.get("direction", "BOTH").upper()
        max_hops = request.get("max_hops", 1)
        reason = request.get("reason", "No reason provided")

        if not node_id:
            logger.warning("Traversal request missing vector_id")
            return []

        logger.debug(f"Performing graph traversal from node '{node_id}', Relationship: '{rel_type or 'ANY'}', Direction: {direction}, Hops: {max_hops}. Reason: {reason}")

        # Build Cypher relationship pattern carefully
        rel_label_cypher = f":`{rel_type}`" if rel_type and isinstance(rel_type, str) and rel_type.strip() else ""
        if direction == "OUTGOING":
            rel_pattern = f"-[r{rel_label_cypher}]->"
        elif direction == "INCOMING":
            rel_pattern = f"<-[r{rel_label_cypher}]-"
        else: # BOTH
            rel_pattern = f"-[r{rel_label_cypher}]-"

        # Ensure max_hops is a positive integer
        try:
            max_hops = int(max_hops)
            if max_hops <= 0: max_hops = 1 # Default to 1 hop if invalid
        except (ValueError, TypeError):
            max_hops = 1

        hops_pattern = f"*1..{max_hops}"

        # Build Cypher query using configured property names
        # We fetch the neighbor node itself to get all its properties
        cypher = f"""
        MATCH (start_node {{{self.node_id_prop_in_graph}: $start_node_id}})
        MATCH path = (start_node){rel_pattern}{hops_pattern}(neighbor)
        WHERE neighbor.{self.node_id_prop_in_graph} <> $start_node_id """ # Avoid self-loops

        # Add project_id filter if applicable
        params = {"start_node_id": node_id}
        if self.project_id_prop and self.project_id:
             # Assuming neighbor nodes also have project_id property
             cypher += f" AND neighbor.{self.project_id_prop} = $project_id"
             params[self.project_id_prop] = self.project_id

        cypher += f"\nRETURN DISTINCT neighbor LIMIT {self.graph_traversal_neighbor_limit}" # Add limit

        try:
            raw_results = await graph_engine.graph_db.execute_query(cypher, params)
            neighbors_data = []
            if raw_results and isinstance(raw_results, list) and raw_results[0]:
                 for record in raw_results[0].data():
                      if 'neighbor' in record:
                           node_obj = record['neighbor']
                           # Convert graph node object/dict to our standard dict format
                           # Handle potential differences in graph DB driver return types
                           if hasattr(node_obj, 'properties'): # Neo4j driver style
                                properties = dict(node_obj.properties)
                           elif isinstance(node_obj, dict): # Generic dict
                                properties = node_obj
                           else:
                                logger.warning(f"Unexpected neighbor node type: {type(node_obj)}")
                                properties = {}
                           neighbors_data.append(properties)
                      elif isinstance(record, dict): # Handle cases where record itself is the node dict
                           neighbors_data.append(record)

            if not neighbors_data:
                 logger.debug(f"No neighbors found for traversal request: {request}")
                 return []

            # Process graph results into the standard file_info format
            processed_neighbors = await self._process_graph_results(neighbors_data, f"traversal from {node_id}")
            for n in processed_neighbors:
                n["relevance_score"] = 0.80 # Assign a score indicating it's from traversal
                n["source"] = "graph_traversal"
                n["_traversal_reason"] = reason # Add reason for traceability
            logger.debug(f"Graph traversal found {len(processed_neighbors)} neighbors for node {node_id}.")
            return processed_neighbors

        except Exception as e:
            logger.exception(f"Error during graph traversal query execution for request {request}: {e}")
            return []

    async def _process_graph_results(self, graph_nodes_data: List[Dict], source_description: str) -> List[Dict]:
        """Standardizes raw graph node data into the file_info dictionary format."""
        processed_results = []
        graph_engine = await get_graph_engine() # Needed for potential content fetch fallback

        # Process concurrently if fetching content is slow
        processing_tasks = [
            self._standardize_graph_node(node_data, source_description, graph_engine)
            for node_data in graph_nodes_data
        ]
        results = await asyncio.gather(*processing_tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, dict) and result:
                processed_results.append(result)
            elif isinstance(result, Exception):
                logger.error(f"Error standardizing graph node from '{source_description}': {result}")

        return processed_results

    async def _standardize_graph_node(self, node_data: Dict, source_description: str, graph_engine: GraphEngine) -> Optional[Dict]:
        """Converts a single raw graph node dict to the standard file_info format."""
        try:
            node_id = node_data.get(self.node_id_prop_in_graph)
            file_path = node_data.get(self.node_path_prop_in_graph)
            dataset = node_data.get(self.node_dataset_prop_in_graph)
            content = node_data.get(self.node_content_prop_in_graph, "")
            node_type = node_data.get(self.node_type_prop_in_graph)
            start_line = node_data.get(self.start_line_prop)
            end_line = node_data.get(self.end_line_prop)

            if not node_id or not file_path:
                logger.warning(f"Skipping graph result from '{source_description}' due to missing ID or path: {node_data}")
                return None

            # Fetch full content if graph only stores snippets or lacks content prop
            if not content or len(content.splitlines()) < 5:
                 full_content = await self._get_full_file_content_from_graph(node_id, graph_engine)
                 if full_content: content = full_content

            if not content:
                 logger.warning(f"Could not retrieve content for graph node {node_id} from '{source_description}'. Skipping.")
                 return None

            # Keep other potentially useful graph properties, excluding content
            other_props = {k:v for k,v in node_data.items() if k not in [
                self.node_content_prop_in_graph,
                # Optionally exclude other large or redundant fields
            ]}

            file_info = {
                "dataset": dataset or self._infer_dataset_from_path(file_path),
                "file_path": file_path,
                "line_range": self._parse_and_validate_line_range(start_line, end_line, content),
                "snippet": content, # Use the fetched content
                "relevance_score": 0.80, # Default score for graph results
                "vector_id": node_id,
                "is_in_scope": True, # Assume in scope initially
                "_fetched_full_content": True, # Content came from graph
                "_graph_node_properties": other_props # Store other props like node_type
            }
            return file_info
        except Exception as e:
            logger.exception(f"Error processing graph result node {node_data.get(self.node_id_prop_in_graph)} from '{source_description}': {e}")
            return None


    async def _get_details_for_id(self, node_id: str, graph_engine: GraphEngine) -> Optional[Dict]:
        """Gets file path, dataset, content, and lines for a given node ID from the graph."""
        logger.debug(f"Getting details for node ID from graph: {node_id}")
        if not node_id: return None
        try:
            # --- Use Configured Schema ---
            cypher = f"""
            MATCH (n {{{self.node_id_prop_in_graph}: $node_id}})
            RETURN n.{self.node_path_prop_in_graph} as path,
                   n.{self.node_dataset_prop_in_graph} as dataset,
                   n.{self.node_content_prop_in_graph} as content,
                   n.{self.start_line_prop} as start_line,
                   n.{self.end_line_prop} as end_line,
                   n.{self.node_type_prop_in_graph} as node_type,
                   n // Return the whole node to capture all properties
            LIMIT 1
            """
            params = {self.node_id_prop_in_graph: node_id}
            # --- End Configured Schema ---

            result = await graph_engine.graph_db.execute_query(cypher, params)
            if result and result[0].data():
                 row = result[0].data()[0]
                 # Extract main properties directly
                 file_path = row.get("path")
                 content = row.get("content")
                 dataset = row.get("dataset")
                 start_line = row.get("start_line")
                 end_line = row.get("end_line")
                 node_type = row.get("node_type") # Get node type

                 # Get all other properties from the node object if returned
                 other_props = {}
                 if 'n' in row:
                      node_obj = row['n']
                      if hasattr(node_obj, 'properties'):
                           other_props = dict(node_obj.properties)
                      elif isinstance(node_obj, dict):
                           other_props = node_obj
                      # Remove already extracted props from other_props
                      for key in [self.node_id_prop_in_graph, self.node_path_prop_in_graph,
                                  self.node_dataset_prop_in_graph, self.node_content_prop_in_graph,
                                  self.start_line_prop, self.end_line_prop, self.node_type_prop_in_graph]:
                           other_props.pop(key, None)


                 if file_path and content:
                     line_range = self._parse_and_validate_line_range(start_line, end_line, content)
                     file_info = {
                          "dataset": dataset or self._infer_dataset_from_path(file_path),
                          "file_path": file_path,
                          "line_range": line_range,
                          "snippet": content,
                          "relevance_score": 0.85,
                          "vector_id": node_id,
                          "_fetched_full_content": True,
                          "_graph_node_properties": other_props # Store remaining properties
                     }
                     # Add node type if found
                     if node_type:
                          file_info["_graph_node_properties"][self.node_type_prop_in_graph] = node_type
                     return file_info
                 else:
                      logger.warning(f"Node {node_id} found in graph but missing path or content.")
        except Exception as e:
             logger.exception(f"Graph lookup failed for ID {node_id}: {e}")
        logger.warning(f"Could not find details for node ID in graph: {node_id}")
        return None


    # --------------------------------------------------------------------------
    # Stage 4: Comprehensive Response Generation
    # --------------------------------------------------------------------------
    async def _generate_comprehensive_response(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Generates the final, structured response using the enhanced context."""
        logger.info("Generating comprehensive response...")
        start_time = time.time()
        llm_client = get_llm_client()
        graph_engine = await get_graph_engine() # Needed for dynamic types

        limited_relevant_files = sorted(
            context.get("relevant_files", []),
            key=lambda x: x.get("relevance_score", 0),
            reverse=True
        )[:self.max_final_results]

        # --- Get Hybrid Type Vocabulary for Synthesis ---
        involved_datasets = list(set(f.get("dataset") for f in limited_relevant_files if f.get("dataset")))
        dynamic_types = await self._get_dynamic_type_vocabulary(involved_datasets, graph_engine)
        available_node_types = sorted(list(set(self.static_node_types + dynamic_types["node_types"])))
        available_edge_types = sorted(list(set(self.static_edge_types + dynamic_types["edge_types"])))

        # Include node types in the results passed to the prompt if available
        results_for_prompt = []
        for file_info in limited_relevant_files:
             info_copy = file_info.copy()
             graph_props = info_copy.pop("_graph_node_properties", {}) # Get graph props if stored
             node_type = graph_props.get(self.node_type_prop_in_graph)
             if node_type: info_copy["node_type"] = node_type # Add type if found
             # Remove internal flags before sending to LLM
             info_copy.pop("_might_need_full_content", None)
             info_copy.pop("_fetched_full_content", None)
             info_copy.pop("_raw_payload", None)
             info_copy.pop("_traversal_reason", None)
             info_copy.pop("is_in_scope", None)
             info_copy.pop("source", None)
             info_copy.pop("relationship_source_id", None)
             info_copy.pop("relationship_type", None)

             results_for_prompt.append(info_copy)

        relationship_summary = self._summarize_relationships(limited_relevant_files)

        prompt_context = {
            "query": query,
            "datasets": ", ".join(sorted(involved_datasets)),
            "results": results_for_prompt, # Use cleaned results
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
            logger.error(f"Error rendering final response prompts: {e}")
            system_prompt = "You are a helpful code assistant."
            user_prompt = f"Summarize findings for query: {query}"

        # Define the structured output schema (including relationships/patterns)
        summary_schema = {
            "type": "object", "properties": {
                "overview": {"type": "string", "description": "High-level architectural overview"},
                "key_components": {"type": "string", "description": "Analysis of important files/functions/relationships"},
                "implementation_details": {"type": "string", "description": "Deep dive into algorithms/techniques visible in snippets"},
                "technical_considerations": {"type": "string", "description": "Analysis of performance, security, etc., *if evident in snippets*"},
                "code_relationships": {"type": "string", "description": f"How components interact based on graph traversals (e.g., using types like {', '.join(available_edge_types)}) and snippets"},
                "pattern_identification": {"type": "string", "description": f"Design patterns identified based on structure (e.g., involving types like {', '.join(available_node_types)}) and snippets"},
                "navigation_guidance": {"type": "string", "description": "Advice on navigating the *provided snippets and relationships*"},
                "follow_up_suggestions": {"type": "array", "items": {"type": "string"}, "description": "Suggested follow-up questions based on analysis"}
            }, "required": ["overview", "key_components"]
        }

        try:
            summary_response = await llm_client.create_structured_output(
                user_prompt, system_prompt, summary_schema, temperature=0.1,
            )

            # Format the structured response into markdown
            formatted_summary = f"# Code Analysis: {query}\n\n"
            sections = [
                ("Overview", "overview"), ("Key Components", "key_components"),
                ("Implementation Details", "implementation_details"),
                ("Code Relationships", "code_relationships"),
                ("Design Patterns", "pattern_identification"),
                ("Technical Considerations", "technical_considerations"),
                ("Navigation Guidance", "navigation_guidance"),
            ]
            for title, key in sections:
                content = summary_response.get(key)
                if content and isinstance(content, str) and content.strip():
                    formatted_summary += f"## {title}\n{content.strip()}\n\n"

            suggestions = summary_response.get("follow_up_suggestions")
            if suggestions and isinstance(suggestions, list) and suggestions:
                 formatted_summary += "## Follow-up Questions\n"
                 for i, suggestion in enumerate(suggestions):
                     if suggestion and isinstance(suggestion, str) and suggestion.strip():
                          formatted_summary += f"{i+1}. {suggestion.strip()}\n"

            duration = time.time() - start_time
            logger.info(f"Comprehensive response generated successfully in {duration:.2f}s.")
            # Clean results before returning (remove internal flags)
            final_relevant_files = []
            for res in limited_relevant_files:
                 res_copy = res.copy()
                 res_copy.pop("_might_need_full_content", None)
                 res_copy.pop("_fetched_full_content", None)
                 res_copy.pop("_raw_payload", None)
                 res_copy.pop("_traversal_reason", None)
                 res_copy.pop("is_in_scope", None)
                 res_copy.pop("source", None)
                 res_copy.pop("relationship_source_id", None)
                 res_copy.pop("relationship_type", None)
                 res_copy.pop("_graph_node_properties", None)
                 final_relevant_files.append(res_copy)

            return {
                "summary": formatted_summary.strip(),
                "relevant_files": final_relevant_files, # Return cleaned results
                "out_of_scope_results": context.get("out_of_scope_results", [])
            }
        except Exception as e:
            logger.exception(f"LLM Error generating comprehensive response: {str(e)}")
            duration = time.time() - start_time
            logger.info(f"Response generation failed after {duration:.2f}s.")
            # Fallback summary
            fallback_summary = f"Found {len(limited_relevant_files)} relevant code snippets for query: '{query}'.\n"
            fallback_summary += "Detailed analysis could not be generated due to an internal error.\n"
            fallback_summary += "Key files identified:\n"
            for f in limited_relevant_files[:3]:
                fallback_summary += f"- {f.get('file_path')} (Dataset: {f.get('dataset')})\n"
            # Clean results even for fallback
            final_relevant_files = []
            for res in limited_relevant_files:
                 res_copy = res.copy(); res_copy.pop("_might_need_full_content", None); res_copy.pop("_fetched_full_content", None); res_copy.pop("_raw_payload", None); res_copy.pop("_traversal_reason", None); res_copy.pop("is_in_scope", None); res_copy.pop("source", None); res_copy.pop("relationship_source_id", None); res_copy.pop("relationship_type", None); res_copy.pop("_graph_node_properties", None); final_relevant_files.append(res_copy)
            return {
                "summary": fallback_summary,
                "relevant_files": final_relevant_files,
                "out_of_scope_results": context.get("out_of_scope_results", [])
            }


    # --------------------------------------------------------------------------
    # Helper Methods (Refined)
    # --------------------------------------------------------------------------
    def _deduplicate_and_sort_results(self, results: List[Dict], max_count: int) -> List[Dict]:
        """Removes duplicates based on vector_id and sorts by relevance score."""
        if not results: return []
        unique_results_dict = {}
        for file_info in results:
            item_id = file_info.get("vector_id")
            if not item_id: continue
            current_score = file_info.get("relevance_score", 0)
            if item_id not in unique_results_dict or current_score > unique_results_dict[item_id].get("relevance_score", 0):
                unique_results_dict[item_id] = file_info
        sorted_unique = sorted(unique_results_dict.values(), key=lambda x: x.get("relevance_score", 0), reverse=True)
        return sorted_unique[:max_count]

    def _extract_dataset_from_metadata(self, payload: Dict, file_path: str = None) -> Optional[str]:
        """Extracts dataset name using configured property name, falling back to path inference."""
        if not payload: payload = {}
        metadata = payload.get("metadata", {})
        dataset = metadata.get(self.dataset_prop) or payload.get(self.dataset_prop)
        if isinstance(dataset, str) and dataset.strip(): return dataset.strip()
        return self._infer_dataset_from_path(file_path)

    def _infer_dataset_from_path(self, file_path: str) -> Optional[str]:
        """Infers dataset from the top-level directory of a file path."""
        if file_path and isinstance(file_path, str):
             # Handle both Unix and Windows paths safely
             path_parts = file_path.replace("\\", "/").strip('/').split('/')
             if path_parts and path_parts[0]: return path_parts[0]
        return None

    def _parse_and_validate_line_range(self, start_line: Any, end_line: Any, code_content: str = "") -> Dict[str, Optional[int]]:
        """Parses start/end lines from metadata, validates, and estimates end if needed."""
        s_line, e_line = None, None
        try: s_line = int(start_line) if start_line is not None else None
        except (ValueError, TypeError): pass
        try: e_line = int(end_line) if end_line is not None else None
        except (ValueError, TypeError): pass

        if s_line is not None and e_line is not None and s_line > e_line:
             logger.warning(f"Invalid line range in metadata: start ({s_line}) > end ({e_line}). Discarding range.")
             s_line, e_line = None, None

        if s_line is not None and e_line is None and code_content:
             num_lines_in_snippet = code_content.count('\n') + 1
             e_line = s_line + num_lines_in_snippet - 1

        return {"start": s_line, "end": e_line}

    def _estimate_line_range(self, code_content: str) -> Dict[str, Optional[int]]:
         """Fallback estimate if start/end metadata is totally missing."""
         if not code_content or not isinstance(code_content, str):
              return {"start": None, "end": None}
         num_lines = code_content.count('\n') + 1
         return {"start": None, "end": num_lines}

    def _get_relevant_snippet(self, code_content: str, query: str, max_lines: int = 30) -> str:
        """Extracts the most relevant portion of the code based on the query."""
        if not code_content or not isinstance(code_content, str): return ""
        lines = code_content.splitlines()
        if len(lines) <= max_lines: return code_content

        query_terms = set(term for term in query.lower().split() if len(term) > 2)
        if not query_terms: return "\n".join(lines[:max_lines])

        line_scores = [(i, sum(1 for term in query_terms if term in line.lower())) for i, line in enumerate(lines)]

        best_score, best_start_line = -1, 0
        current_window_score = sum(score for _, score in line_scores[:max_lines])
        if current_window_score >= 0: best_score, best_start_line = current_window_score, 0

        for i in range(max_lines, len(lines)):
            current_window_score += line_scores[i][1] - line_scores[i - max_lines][1]
            if current_window_score > best_score: best_score, best_start_line = current_window_score, i - max_lines + 1

        if best_score <= 0 and all(s == 0 for _, s in line_scores): return "\n".join(lines[:max_lines])

        start_line = best_start_line
        end_line = min(len(lines), start_line + max_lines)

        context_needed = max_lines - (end_line - start_line)
        if context_needed > 0:
            start_line = max(0, start_line - context_needed)
            end_line = min(len(lines), start_line + max_lines)

        snippet = "\n".join(lines[start_line:end_line])
        if start_line > 0: snippet = "...\n" + snippet
        if end_line < len(lines): snippet = snippet + "\n..."
        return snippet

    async def _perform_basic_search(self, query: str, datasets: List[str], limit: int = 5) -> List[Dict]:
        """Performs a basic vector search, returning results with reliable metadata payload."""
        logger.debug(f"Performing basic search for: '{query}' in datasets: {datasets}")
        vector_engine = get_vector_engine()
        results_with_payload = [] # Change name for clarity
        search_tasks = [
            vector_engine.search(collection, query, limit=limit * 2) # Fetch more for filtering
            for collection in self.vector_collections
        ]
        results_per_collection = await asyncio.gather(*search_tasks, return_exceptions=True)

        processed_ids = set()

        for res_list in results_per_collection:
            if isinstance(res_list, list):
                for res in res_list:
                    payload = res.payload or {}
                    metadata = payload.get("metadata", {})
                    node_id = metadata.get(self.id_prop) or payload.get(self.id_prop)
                    file_path = metadata.get(self.path_prop) or payload.get(self.path_prop)
                    dataset_name = metadata.get(self.dataset_prop) or payload.get(self.dataset_prop)

                    if not node_id or node_id in processed_ids: continue
                    if not dataset_name: dataset_name = self._infer_dataset_from_path(file_path)

                    # Filter by dataset if specified
                    if not datasets or (dataset_name and dataset_name in datasets):
                        # Return dict containing id, score, and the *full payload*
                        results_with_payload.append({
                            "id": node_id,
                            "score": res.score,
                            "payload": payload # Pass the payload for potential use
                        })
                        processed_ids.add(node_id)

        results_with_payload.sort(key=lambda x: x["score"], reverse=True)
        logger.debug(f"Basic search found {len(results_with_payload[:limit])} results for '{query}'")
        return results_with_payload[:limit]

    def _summarize_relationships(self, relevant_files: List[Dict]) -> str:
         """Creates a simple text summary of relationships found via traversal."""
         summary_lines = []
         # Check for the internal flags added during traversal/processing
         for file_info in relevant_files:
             if file_info.get("source") == "graph_traversal":
                 source_id = file_info.get("relationship_source_id", "Unknown source")
                 rel_type = file_info.get("relationship_type", "UNKNOWN_REL")
                 target_path = file_info.get("file_path", "Unknown target")
                 reason = file_info.get("_traversal_reason", "")
                 summary_line = f"- Found related file `{target_path}` via graph traversal (Type: {rel_type}, From Node ID: {source_id[:8]}...)"
                 if reason: summary_line += f" Reason: {reason}"
                 summary_lines.append(summary_line)

         if not summary_lines:
             return "No specific code relationships were explored or added in this retrieval."
         # Limit summary length if needed
         max_summary_lines = 5
         summary = "Relationships explored via graph traversal:\n" + "\n".join(summary_lines[:max_summary_lines])
         if len(summary_lines) > max_summary_lines:
             summary += f"\n... (and {len(summary_lines) - max_summary_lines} more relationships explored)"
         return summary
