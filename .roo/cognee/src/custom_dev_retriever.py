# custom_dev_retriever.py
from typing import Any, Dict, List, Optional, Union
import json
import re
import time
from uuid import UUID
import asyncio
from collections import OrderedDict

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

# --- Context Cache (For overall retrieval results) ---
class ContextCache:
    """Simple in-memory cache for get_context results with TTL."""
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
        try:
            # Return a deep copy to prevent modification of cached object by reference
            return json.loads(json.dumps(self.cache[key]))
        except TypeError: # Handle potential non-serializable data if error occurs
             logger.warning(f"Could not deep copy cached item for key {key}. Returning direct reference.")
             return self.cache[key] # Fallback to direct reference

    def set(self, key, value):
        if len(self.cache) >= self.max_size and key not in self.cache:
            try:
                # Simple FIFO removal if access times aren't tracked perfectly for LRU
                lru_key = next(iter(self.cache))
                logger.debug(f"Cache full. Removing oldest key: {lru_key}")
                self.remove(lru_key)
            except StopIteration: pass # Cache might be empty
        logger.debug(f"Setting cache for key: {key}")
        try:
            # Store a deep copy to prevent modification by reference
            self.cache[key] = json.loads(json.dumps(value))
        except TypeError:
            logger.warning(f"Could not deep copy value for cache key {key}. Storing direct reference.")
            self.cache[key] = value # Fallback to direct reference
        self.access_times[key] = time.time() # Track access for TTL

    def remove(self, key):
        if key in self.cache: del self.cache[key]
        if key in self.access_times: del self.access_times[key]
        logger.debug(f"Removed cache key: {key}")

# --- Custom Retriever (Metadata-First, Graph Traversal Enabled) ---
class DevCodeRetriever(BaseRetriever):
    """
    Developer-focused retriever using a multi-stage pipeline. Prioritizes reliable
    metadata from vector search. Uses the graph database for targeted content lookups
    and optional, LLM-planned relationship exploration. Assumes canonical node/edge
    properties and dataset path format ('tenant/role/dataset'). Relies on externally
    provided static type information.

    ASSUMPTION: This retriever requires a Cognee configuration using a
    Cypher-compatible graph database (e.g., Neo4j, Memgraph, FalkorDB) that
    returns results in a Neo4j-driver-like format when using `execute_query`.
    Vector filtering capabilities depend on the configured vector database adapter.
    """

    def __init__(
        self,
        # --- Prompt template paths ---
        system_prompt_path: str = "dev_code_retrieval_system.txt",
        user_prompt_path: str = "dev_code_retrieval_user.txt",
        analysis_system_prompt_path: str = "dev_code_analysis_prompt.txt",
        analysis_user_prompt_path: str = "dev_code_analysis_user_prompt.txt",

        # --- Schema & Configuration (Reflects Canonical Properties) ---
        vector_collections: List[str] = ["TextChunks"], # Default collection name

        # Canonical Node Properties (used for vector metadata and graph nodes)
        node_id_prop: str = "id",             # Unique ID (ensure consistency vector<->graph)
        node_name_prop: str = "name",           # Name of function/class/variable etc.
        node_file_path_prop: str = "path",        # File path relative to project/dataset root
        node_chunk_prop: str = "content",       # The actual code/text chunk content
        node_dataset_path_prop: str = "dataset_path", # Hierarchical path: "tenant/role/dataset"
        node_type_prop: str = "node_type",      # e.g., "FUNCTION", "CLASS", "CHUNK"
        node_timestamp_prop: str = "timestamp",   # Float epoch timestamp (e.g., time.time())
        node_start_line_prop: str = "start_line", # Starting line in the original file
        node_end_line_prop: str = "end_line",     # Ending line in the original file
        node_scope_prop: str = "in_scope",      # Boolean, relevance to current scope/query (optional)

        # Canonical Edge Properties (primarily for interpreting graph results)
        edge_type_prop: str = "edge_type",      # e.g., "CALLS", "IMPORTS", relationship type label
        # Note: edge_id, source_id, target_id, path, timestamp, dataset_path are assumed to exist
        # in graph query results based on the schema.

        # --- Retrieval limits ---
        max_vector_results: int = 25,
        max_final_results: int = 10,
        max_out_of_scope_results: int = 5,
        graph_traversal_neighbor_limit: int = 10,
        dynamic_node_types_top_n: int = 15, # Limit for dynamically fetched node types
        dynamic_edge_types_top_n: int = 10, # Limit for dynamically fetched edge types

        # --- Type Vocabulary Cache Configuration ---
        type_cache_max_size: int = 100, # Max datasets/combinations to cache types for
        type_cache_ttl_seconds: int = 3600, # Cache dynamic types for 1 hour

        # --- External Type Information (Assumed to be loaded elsewhere) ---
        # static_types_map_path: Optional[str] = "config/static_types_map.json", # Path to load static types from
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
        self.dynamic_node_types_top_n = dynamic_node_types_top_n
        self.dynamic_edge_types_top_n = dynamic_edge_types_top_n

        # Store schema configuration
        self.vector_collections = vector_collections
        self.node_id_prop = node_id_prop
        self.node_name_prop = node_name_prop
        self.node_file_path_prop = node_file_path_prop
        self.node_chunk_prop = node_chunk_prop
        self.node_dataset_path_prop = node_dataset_path_prop
        self.node_type_prop = node_type_prop
        self.node_timestamp_prop = node_timestamp_prop
        self.node_start_line_prop = node_start_line_prop
        self.node_end_line_prop = node_end_line_prop
        self.node_scope_prop = node_scope_prop # Optional property

        self.edge_type_prop = edge_type_prop # Configurable edge type property name

        # Initialize Caches
        self.context_cache = ContextCache()
        self.type_vocabulary_cache = OrderedDict() # Use OrderedDict for simple LRU
        self.type_cache_max_size = type_cache_max_size
        self.type_cache_ttl_seconds = type_cache_ttl_seconds

        # Placeholder for loaded static types (implement loading logic)
        # self.static_types_map = self._load_static_types(static_types_map_path)
        self.static_types_map = {} # Needs implementation

        logger.info("DevCodeRetriever initialized (Metadata-First, Graph Traversal Enabled).")
        logger.info(f" Assumptions - Vector Collections: {self.vector_collections}")
        logger.info(f" Assumptions - Canonical Node Props: id={self.node_id_prop}, name={self.node_name_prop}, path={self.node_file_path_prop}, chunk={self.node_chunk_prop}, dataset={self.node_dataset_path_prop}, type={self.node_type_prop}, ts={self.node_timestamp_prop}, start={self.node_start_line_prop}, end={self.node_end_line_prop}")
        logger.info(f" Assumptions - Configured Edge Type Prop: {self.edge_type_prop}")
        logger.info(f" Assumptions - Type Vocabulary Cache: max_size={self.type_cache_max_size}, ttl={self.type_cache_ttl_seconds}s")
        logger.info(f" Assumptions - Static types expected from external source (path configured but loading needs implementation).")
        logger.info(f" IMPORTANT DB ASSUMPTION: Requires Cypher-compatible graph DB with Neo4j-like result format.")


    # Placeholder for loading static types (replace with actual implementation)
    # def _load_static_types(self, map_path: Optional[str]) -> Dict:
    #     if not map_path:
    #         logger.warning("No path provided for static types map.")
    #         return {}
    #     try:
    #         with open(map_path, 'r') as f:
    #             data = json.load(f)
    #             logger.info(f"Loaded static types map from {map_path}")
    #             return data
    #     except FileNotFoundError:
    #         logger.error(f"Static types map file not found at {map_path}")
    #         return {}
    #     except json.JSONDecodeError:
    #         logger.error(f"Error decoding JSON from static types map file: {map_path}")
    #         return {}
    #     except Exception as e:
    #         logger.exception(f"Failed to load static types map from {map_path}: {e}")
    #         return {}

    # --------------------------------------------------------------------------
    # Main Orchestration Method
    # --------------------------------------------------------------------------
    async def get_completion(
        self, query: str, context: Optional[Dict[str, Any]] = None, datasets: List[str] = None
    ) -> Dict[str, Any]:
        """
        Orchestrates the multi-stage retrieval pipeline.
        Args:
            query: The user's query string.
            context: Optional pre-existing context dictionary.
            datasets: List of dataset paths (e.g., ["tenantA/projectX/dataset1", "tenantB/projectY/dataset2"])
                      to scope the retrieval. Crucial for filtering and type loading.
        """
        trace = []
        start_time = time.time()
        logger.info(f"Starting get_completion for query: '{query}' in datasets: {datasets}")
        final_response = {}

        if not datasets:
            # Dataset scoping is critical for filtering and type fetching. Error out or use a default.
            logger.error("No datasets provided to get_completion. Cannot proceed without dataset scope.")
            return {"summary": "Error: Retrieval requires specific dataset paths.", "relevant_files": [], "out_of_scope_results": [], "trace": [{"stage": "error", "message": "Missing dataset scope"}]}

        try:
            # STAGE 1: Initial Context Retrieval (Vector Search + Metadata Extraction)
            stage_start_time = time.time()
            trace.append({"stage": "initial_retrieval", "status": "started"})
            if context is None:
                # Include datasets in cache key
                cache_key = f"context:{query}:{','.join(sorted(datasets))}"
                cached_context = self.context_cache.get(cache_key)
                if cached_context:
                    context = cached_context
                    context['datasets'] = datasets # Ensure datasets are correctly populated
                    trace[-1].update({"status": "completed", "source": "cache", "duration": time.time() - stage_start_time})
                else:
                    context = await self.get_context(query, datasets)
                    if context: # Only cache if context was successfully retrieved
                        self.context_cache.set(cache_key, context)
                    trace[-1].update({"status": "completed", "source": "new", "duration": time.time() - stage_start_time})
            else:
                 context.setdefault("relevant_files", [])
                 context.setdefault("out_of_scope_results", [])
                 context['datasets'] = datasets # Ensure datasets are set from input
                 trace[-1].update({"status": "completed", "source": "provided", "duration": time.time() - stage_start_time})

            # Check if context retrieval failed or yielded no results
            if not context or not context.get("relevant_files"):
                logger.warning(f"No relevant files found for query: {query} within datasets: {datasets}")
                final_response = {"summary": f"No relevant results found for query: {query}", "relevant_files": [], "out_of_scope_results": context.get("out_of_scope_results", []) if context else []}
                return {**final_response, "trace": trace}

            # STAGE 2: Analysis Planning (Based on retrieved chunks/metadata)
            stage_start_time = time.time()
            trace.append({"stage": "analysis_planning", "status": "started"})
            analysis_plan = await self._analyze_and_plan(query, context, datasets)
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
                query, enhanced_context, datasets
            )
            trace[-1].update({"status": "completed", "duration": time.time() - stage_start_time})

            end_time = time.time()
            logger.info(f"get_completion finished in {end_time - start_time:.2f} seconds.")
            return {**final_response, "trace": trace}

        except Exception as e:
            logger.exception(f"Critical error during get_completion for query '{query}': {str(e)}")
            relevant_files = context.get("relevant_files", []) if context else []
            out_of_scope = context.get("out_of_scope_results", []) if context else []
            final_response = {
                "summary": f"An error occurred while processing your query: {str(e)}",
                "relevant_files": relevant_files,
                "out_of_scope_results": out_of_scope,
            }
            error_trace_entry = {"stage": "error", "message": str(e)}
            if trace and trace[-1].get("stage") != "error": trace.append(error_trace_entry)
            elif not trace: trace = [error_trace_entry]
            return {**final_response, "trace": trace}


    # --------------------------------------------------------------------------
    # Stage 1: Initial Context Retrieval (Vector Search + Metadata Extraction)
    # --------------------------------------------------------------------------
    async def get_context(self, query: str, datasets: List[str]) -> Optional[Dict[str, Any]]:
        """
        Performs initial vector search and extracts reliable metadata, filtered by dataset paths.
        Args:
            query: The user's query string.
            datasets: List of dataset paths (e.g., ["tenant/role/dataset1"]) to filter results. Must not be empty.
        Returns:
            Context dictionary or None if a critical error occurs.
        """
        if not datasets:
            logger.error("get_context called without datasets. Cannot perform scoped retrieval.")
            return None

        logger.info(f"Performing initial context retrieval for '{query}' in datasets: {datasets}")
        start_time = time.time()

        context = {"query": query, "datasets": datasets, "relevant_files": [], "out_of_scope_results": []}
        vector_engine = get_vector_engine()
        all_vector_results = []
        vector_filter = self._create_vector_filter(datasets)

        search_tasks = []
        use_local_filtering = False
        for collection in self.vector_collections:
            try:
                 search_tasks.append(
                     vector_engine.search(collection, query, limit=self.max_vector_results, filter=vector_filter)
                 )
            except NotImplementedError:
                 logger.warning(f"Vector engine does not support filtering during search for collection '{collection}'. Fetching more results and filtering locally.")
                 use_local_filtering = True
                 search_tasks.append(
                     # Fetch more if filtering locally, scale by dataset count as rough estimate
                     vector_engine.search(collection, query, limit=self.max_vector_results * len(datasets) * 2)
                 )
            except Exception as e:
                 logger.error(f"Error preparing search for collection {collection}: {e}")
                 # Optionally continue with other collections or return None

        if not search_tasks:
             logger.error("No valid search tasks could be prepared.")
             return None

        results_per_collection = await asyncio.gather(*search_tasks, return_exceptions=True)

        for i, result_list in enumerate(results_per_collection):
            collection_name = self.vector_collections[i]
            if isinstance(result_list, Exception):
                logger.error(f"Error searching vector collection '{collection_name}': {result_list}")
            elif result_list:
                all_vector_results.extend(result_list)

        # Process Search Results (Extract reliable metadata & filter by dataset if needed)
        processed_files = {}
        processed_out_of_scope = {}
        processing_tasks = [ self._process_search_result(result, query) for result in all_vector_results ]
        processed_results = await asyncio.gather(*processing_tasks, return_exceptions=True)

        for proc_result in processed_results:
            if isinstance(proc_result, Exception) or proc_result is None: continue

            result_dataset = proc_result.get(self.node_dataset_path_prop)

            # Filter by dataset path if filtering wasn't done in DB query OR if dataset is missing (error case)
            if use_local_filtering or not result_dataset:
                if not result_dataset:
                    # This case should ideally not happen if ingestion is strict, but handle defensively.
                    logger.error(f"Processed result missing dataset path: {proc_result.get(self.node_id_prop)}. Discarding.")
                    continue
                elif result_dataset not in datasets:
                     # Store as out-of-scope only if not filtered by DB initially
                     item_key = proc_result.get(self.node_id_prop) or proc_result.get(self.node_file_path_prop)
                     if not item_key: continue
                     if item_key not in processed_out_of_scope or proc_result["relevance_score"] > processed_out_of_scope[item_key].get("relevance_score", 0):
                         proc_result["is_in_scope"] = False # Explicitly mark
                         processed_out_of_scope[item_key] = proc_result
                     continue # Skip adding to relevant_files

            # If it passed the dataset check (implicitly or explicitly)
            item_key = proc_result.get(self.node_id_prop) or proc_result.get(self.node_file_path_prop)
            if not item_key: continue

            # Add to relevant files, prioritizing higher score
            if item_key not in processed_files or proc_result["relevance_score"] > processed_files[item_key].get("relevance_score", 0):
                 proc_result["is_in_scope"] = True # Explicitly mark
                 processed_files[item_key] = proc_result

        # Finalize context structure - Sort and limit
        context["relevant_files"] = self._deduplicate_and_sort_results(list(processed_files.values()), self.max_final_results)
        context["out_of_scope_results"] = self._deduplicate_and_sort_results(list(processed_out_of_scope.values()), self.max_out_of_scope_results)

        duration = time.time() - start_time
        logger.info(f"Initial context retrieval found {len(context['relevant_files'])} relevant files (in scope), {len(context['out_of_scope_results'])} out-of-scope/dataset in {duration:.2f}s.")
        return context

    def _create_vector_filter(self, datasets: List[str]) -> Optional[Any]:
        """
        Creates a filter dictionary for vector search based on dataset paths.
        NOTE: The return type and structure depend HEAVILY on the vector DB adapter used by Cognee.
        This example is for Qdrant. Adapt for Weaviate, Pinecone, Milvus, etc.
        Returns None if filtering is not supported or datasets is empty.
        """
        if not datasets:
            return None

        # --- Example for Qdrant ---
        try:
            # Attempt to import Qdrant models dynamically to avoid hard dependency
            from qdrant_client.http import models as rest

            # Qdrant expects the metadata field path. Adjust if your payload structure differs.
            # Assumes dataset_path is directly under 'metadata'.
            metadata_key = f"metadata.{self.node_dataset_path_prop}"

            # Use 'should' for OR condition (must match at least one dataset)
            return rest.Filter(
                should=[
                    rest.FieldCondition(
                        key=metadata_key,
                        match=rest.MatchValue(value=path)
                    )
                    for path in datasets
                ]
            )
        except ImportError:
            logger.warning("Qdrant client not found. Cannot create specific Qdrant vector filter.")
            raise NotImplementedError("Vector filtering not implemented for the current backend (Qdrant missing).")
        except Exception as e:
            logger.error(f"Failed to create Qdrant vector filter for datasets {datasets}: {e}")
            # Raise NotImplementedError to trigger local filtering
            raise NotImplementedError(f"Filter creation failed: {e}")

        # --- Add similar blocks for other vector databases if needed ---
        # Example for Weaviate (conceptual - syntax might differ):
        # try:
        #     # from weaviate.gql.filter import Where # etc.
        #     return {
        #         "operator": "Or",
        #         "operands": [
        #             {"path": [self.node_dataset_path_prop], "operator": "Equal", "valueString": path}
        #             for path in datasets
        #         ]
        #     }
        # except ImportError:
        #     pass # Fall through or raise

        # Default if no specific implementation matches or works
        # raise NotImplementedError("Vector filtering not implemented for the current backend.")


    async def _process_search_result(self, result, query) -> Optional[Dict]:
        """
        Helper to process a single vector search result using canonical property names.
        Requires `node_dataset_path_prop` to be present in the payload/metadata.
        """
        try:
            payload = result.payload or {}
            # Metadata might be nested or flat depending on ingestion
            metadata = payload.get("metadata", {})

            # Use canonical property names, checking both metadata and payload root
            node_id = metadata.get(self.node_id_prop) or payload.get(self.node_id_prop)
            file_path = metadata.get(self.node_file_path_prop) or payload.get(self.node_file_path_prop)
            dataset_path = metadata.get(self.node_dataset_path_prop) or payload.get(self.node_dataset_path_prop)
            text_chunk = payload.get(self.node_chunk_prop, "") # Use canonical name
            start_line = metadata.get(self.node_start_line_prop) or payload.get(self.node_start_line_prop)
            end_line = metadata.get(self.node_end_line_prop) or payload.get(self.node_end_line_prop)
            node_name = metadata.get(self.node_name_prop) or payload.get(self.node_name_prop)
            timestamp = metadata.get(self.node_timestamp_prop) or payload.get(self.node_timestamp_prop)
            node_type = metadata.get(self.node_type_prop) or payload.get(self.node_type_prop)

            # Essential fields check - CRITICAL: dataset_path MUST exist
            if not node_id:
                logger.error(f"Skipping vector result due to missing ID. Payload: {payload}")
                return None
            if not file_path:
                logger.warning(f"Vector result {node_id} missing file path. Proceeding, but context may be limited.")
                file_path = "Unknown"
            if not dataset_path:
                # This indicates an ingestion error if our assumption holds. Error out.
                logger.error(f"CRITICAL: Vector result {node_id} (path: {file_path}) missing mandatory '{self.node_dataset_path_prop}'. Skipping.")
                return None

            # Determine if snippet needs full content fetch later
            needs_full_content = not text_chunk or len(text_chunk.splitlines()) < 5

            # Extract relevant part of the chunk for immediate display/use
            relevant_chunk_part = self._extract_relevant_chunk(text_chunk, query)

            file_info = {
                # Use canonical names for the output dict keys
                self.node_dataset_path_prop: dataset_path,
                self.node_file_path_prop: file_path,
                "line_range": self._parse_and_validate_line_range(start_line, end_line, text_chunk),
                "relevant_chunk": relevant_chunk_part, # The extracted relevant part
                self.node_chunk_prop: text_chunk, # The full chunk text
                "relevance_score": result.score,
                "vector_id": result.id, # Keep original vector ID if needed
                self.node_id_prop: node_id, # Canonical node id
                self.node_name_prop: node_name,
                self.node_timestamp_prop: timestamp,
                self.node_type_prop: node_type,
                "is_in_scope": True, # Default to True, filtering happens in get_context
                "_might_need_full_content": needs_full_content and text_chunk # Only flag if original chunk exists but is short
            }
            # Clean up None values before returning
            return {k: v for k, v in file_info.items() if v is not None}

        except Exception as e:
            logger.exception(f"Error processing vector result {getattr(result, 'id', 'N/A')}: {str(e)}")
            return None

    async def _get_full_file_content_from_graph(self, node_id: str, graph_engine: GraphEngine) -> Optional[str]:
        """Gets full chunk content from the graph using the node ID and canonical property name."""
        logger.debug(f"Attempting graph lookup for full content using node_id: {node_id}")
        if not node_id: return None
        try:
            # Use canonical property names
            cypher = f"""
            MATCH (n {{{self.node_id_prop}: $node_id}})
            WHERE n.`{self.node_chunk_prop}` IS NOT NULL
            RETURN n.`{self.node_chunk_prop}` AS chunk_content
            LIMIT 1
            """
            params = {"node_id": node_id}

            result = await graph_engine.graph_db.execute_query(cypher, params)

            # Adapt parsing based on expected Neo4j-like driver result format
            if result and result[0] and result[0].data():
                record_data = result[0].data()[0] # Get the first record's data dictionary
                content = record_data.get('chunk_content')
                if content:
                    logger.debug(f"Found chunk content for node {node_id} (length: {len(content)}) via graph.")
                    return content
            logger.warning(f"Could not find node or chunk content for {node_id} in graph.")
            return None
        except Exception as e:
            logger.exception(f"Error getting chunk content from graph for node {node_id}: {e}")
            return None

    # --------------------------------------------------------------------------
    # Stage 2: Analysis Planning
    # --------------------------------------------------------------------------
    async def _analyze_and_plan(self, query: str, context: Dict[str, Any], datasets: List[str]) -> Dict[str, Any]:
        """Analyzes initial metadata/chunks and generates a retrieval plan."""
        logger.info(f"Creating analysis plan for query: '{query}' scoped to datasets: {datasets}")
        llm_client = get_llm_client()
        graph_engine = await get_graph_engine()

        # --- Get Combined Type Vocabulary (Dynamic + Static, Scoped by Datasets) ---
        dynamic_types = await self._get_dynamic_type_vocabulary(datasets, graph_engine) # Cached
        static_nodes, static_edges = self._get_static_types_for_datasets(datasets)

        available_node_types = sorted(list(set(dynamic_types.get("node_types", []) + static_nodes)))
        available_edge_types = sorted(list(set(dynamic_types.get("edge_types", []) + static_edges)))

        logger.debug(f"Using Combined Node Types for Planning: {available_node_types}")
        logger.debug(f"Using Combined Edge Types for Planning: {available_edge_types}")

        # Prepare summaries for the prompt context using canonical props
        relevant_files_summary = [{
            "file_path": f.get(self.node_file_path_prop),
            "dataset": f.get(self.node_dataset_path_prop),
            "score": round(f.get("relevance_score", 0), 2),
            "id": f.get(self.node_id_prop),
            "type": f.get(self.node_type_prop),
            "name": f.get(self.node_name_prop),
        } for f in context.get("relevant_files", [])[:7]] # Limit for brevity

        out_of_scope_summary = [{
            "file_path": f.get(self.node_file_path_prop),
            "dataset": f.get(self.node_dataset_path_prop),
            "score": round(f.get("relevance_score", 0), 2)
        } for f in context.get("out_of_scope_results", [])[:3]] # Limit for brevity

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
            system_prompt = "You are an intelligent code analysis planner..." # Fallback
            user_prompt = f"Analyze query '{query}' & plan retrieval based on findings & available types..." # Fallback

        # Define the expected structure of the plan using canonical ID prop
        plan_schema = {
            "type": "object", "properties": {
                "analysis": {"type": "string", "description": "Brief assessment of initial results and knowledge gaps."},
                "additional_files_to_fetch_full_content": {"type": "array", "items": {"type": "object", "properties": {
                    "file_path": {"type": "string"},
                    self.node_id_prop: {"type": "string", "description": "The unique ID of the node needing full content."},
                    "reason": {"type": "string"}
                }, "required": ["file_path", self.node_id_prop, "reason"]}, "description": "Nodes needing full chunk content retrieval."},
                "additional_search_queries": {"type": "array", "items": {"type": "string"}, "description": "New vector search queries for related concepts."},
                "graph_relationships_to_explore": {"type": "array", "items": {"type": "object", "properties": {
                    self.node_id_prop: {"type": "string", "description": f"The '{self.node_id_prop}' of the node to start exploration from"},
                    "source_file": {"type": "string", "description": "The file path of the source node"},
                    "relationship_type": {"type": ["string", "null"], "enum": available_edge_types + [None], "description": f"Relationship type (e.g., {', '.join(available_edge_types[:3])}...), using the '{self.edge_type_prop}' property, or null/omit for any."},
                    "direction": {"type": "string", "enum": ["INCOMING", "OUTGOING", "BOTH"], "default": "BOTH", "description": "Direction of relationship."},
                    "max_hops": {"type": "integer", "default": 1, "description": "Maximum steps to traverse."},
                    "reason": {"type": "string", "description": "Why this traversal is needed."}},
                    "required": [self.node_id_prop, "source_file", "direction", "reason"]},
                    "description": f"Specific code relationships to explore starting from a known node '{self.node_id_prop}'."}
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
        datasets: List[str], # Pass datasets for scoping searches/traversals
        trace: List[Dict]
    ) -> Dict[str, Any]:
        """Executes the retrieval plan (fetches full content, runs new queries, explores graph)."""
        logger.info("Executing retrieval plan...")
        start_time = time.time()
        # Deep copy relevant parts of context
        enhanced_context = {
             "query": context["query"],
             "datasets": list(context.get("datasets", [])),
             "relevant_files": [f.copy() for f in context.get("relevant_files", [])],
             "out_of_scope_results": [f.copy() for f in context.get("out_of_scope_results", [])],
             "analysis_notes": plan.get("analysis", "")
        }
        current_relevant_ids = {rf.get(self.node_id_prop) for rf in enhanced_context["relevant_files"] if rf.get(self.node_id_prop)}

        graph_engine = await get_graph_engine()
        # vector_engine = get_vector_engine() # Not needed directly here if using helpers
        retrieved_content_count = 0
        retrieved_query_count = 0
        explored_relationships_count = 0

        # --- 1. Fetch full chunk content for specified nodes ---
        nodes_to_fetch = plan.get("additional_files_to_fetch_full_content", [])
        if nodes_to_fetch:
            sub_stage_start = time.time()
            trace.append({"sub_stage": "full_content_retrieval", "status": "started", "nodes_requested": len(nodes_to_fetch)})
            fetch_tasks = [self._get_full_file_content_from_graph(node_req.get(self.node_id_prop), graph_engine) for node_req in nodes_to_fetch if node_req.get(self.node_id_prop)]
            fetched_contents = await asyncio.gather(*fetch_tasks, return_exceptions=True)
            content_updated_count = 0
            for i, content in enumerate(fetched_contents):
                if isinstance(content, str) and content:
                    node_id = nodes_to_fetch[i].get(self.node_id_prop)
                    for file_info in enhanced_context["relevant_files"]:
                        if file_info.get(self.node_id_prop) == node_id:
                            logger.debug(f"Updating chunk content for {file_info[self.node_file_path_prop]} (ID: {node_id})")
                            file_info[self.node_chunk_prop] = content # Update full chunk
                            file_info["relevant_chunk"] = self._extract_relevant_chunk(content, enhanced_context["query"]) # Re-extract relevant part
                            file_info["line_range"] = self._parse_and_validate_line_range(None, None, content) # Recalculate line range
                            file_info["_fetched_full_content"] = True
                            content_updated_count += 1
                            break
                elif isinstance(content, Exception): logger.error(f"Error fetching full content for node {nodes_to_fetch[i].get(self.node_id_prop)}: {content}")
            retrieved_content_count = content_updated_count
            trace[-1].update({"status": "completed", "content_updated_count": content_updated_count, "duration": time.time() - sub_stage_start})

        # --- 2. Execute additional search queries ---
        additional_queries = list(set(plan.get("additional_search_queries", [])))
        if additional_queries:
            sub_stage_start = time.time()
            trace.append({"sub_stage": "additional_queries", "status": "started", "queries": additional_queries})
            # Scope additional searches by the same dataset list
            query_tasks = [self._perform_basic_search(add_query, datasets, limit=5) for add_query in additional_queries]
            query_results_lists = await asyncio.gather(*query_tasks, return_exceptions=True)
            detail_fetch_tasks = []
            processed_ids_in_query = set()
            files_added_this_stage = 0
            for i, basic_results_list in enumerate(query_results_lists):
                 query_text = additional_queries[i]
                 if isinstance(basic_results_list, Exception): logger.error(f"Error executing query '{query_text}': {basic_results_list}"); continue
                 if not basic_results_list: continue
                 for result in basic_results_list:
                      node_id = result.get("id") # _perform_basic_search returns 'id' key
                      if node_id and node_id not in processed_ids_in_query and node_id not in current_relevant_ids:
                           # Fetch full details from graph using the ID
                           detail_fetch_tasks.append(self._get_details_for_id(node_id, graph_engine))
                           processed_ids_in_query.add(node_id)

            # Fetch details concurrently
            if detail_fetch_tasks:
                detailed_results = await asyncio.gather(*detail_fetch_tasks, return_exceptions=True)
                for file_info in detailed_results:
                     if isinstance(file_info, dict) and file_info:
                          node_id = file_info.get(self.node_id_prop)
                          result_dataset = file_info.get(self.node_dataset_path_prop)
                          # Check if already present and if it's in the required dataset scope
                          if node_id not in current_relevant_ids and result_dataset in datasets:
                               file_info["is_in_scope"] = True
                               enhanced_context["relevant_files"].append(file_info)
                               current_relevant_ids.add(node_id)
                               files_added_this_stage += 1
                          elif node_id not in current_relevant_ids:
                                # It's a new node, but not in the required datasets
                                file_info["is_in_scope"] = False
                                enhanced_context["out_of_scope_results"].append(file_info)
                     elif isinstance(file_info, Exception): logger.error(f"Error fetching details via additional query: {file_info}")

            retrieved_query_count = files_added_this_stage
            trace[-1].update({"status": "completed", "files_added": files_added_this_stage, "duration": time.time() - sub_stage_start})

        # --- 3. Explore graph relationships ---
        relationships_to_explore = plan.get("graph_relationships_to_explore", [])
        if relationships_to_explore:
            sub_stage_start = time.time()
            trace.append({"sub_stage": "relationship_exploration", "status": "started", "relationships_planned": len(relationships_to_explore)})
            # Pass datasets to traversal for potential filtering of results (filtering happens post-traversal)
            relation_tasks = [self._perform_graph_traversal(graph_engine, rel) for rel in relationships_to_explore]
            exploration_results_lists = await asyncio.gather(*relation_tasks, return_exceptions=True)
            nodes_added_count = 0
            for result_list in exploration_results_lists:
                if isinstance(result_list, list):
                    for file_info in result_list:
                         node_id = file_info.get(self.node_id_prop)
                         result_dataset = file_info.get(self.node_dataset_path_prop)
                         # Check if already present and if it's in the required dataset scope
                         if node_id not in current_relevant_ids and result_dataset in datasets:
                              file_info["is_in_scope"] = True
                              enhanced_context["relevant_files"].append(file_info)
                              current_relevant_ids.add(node_id)
                              nodes_added_count += 1
                         elif node_id not in current_relevant_ids:
                              # New node, but wrong dataset
                              file_info["is_in_scope"] = False
                              enhanced_context["out_of_scope_results"].append(file_info)
                elif isinstance(result_list, Exception): logger.error(f"Error during relationship exploration task: {result_list}")
            explored_relationships_count = nodes_added_count
            trace[-1].update({"status": "completed", "nodes_added": nodes_added_count, "duration": time.time() - sub_stage_start})

        # Final deduplication and sorting before response generation
        enhanced_context["relevant_files"] = self._deduplicate_and_sort_results(
            enhanced_context["relevant_files"], self.max_final_results
        )
        enhanced_context["out_of_scope_results"] = self._deduplicate_and_sort_results(
            enhanced_context["out_of_scope_results"], self.max_out_of_scope_results
        )

        duration = time.time() - start_time
        logger.info(f"Enhanced retrieval completed in {duration:.2f}s. Updated content: {retrieved_content_count}, Added from Query: {retrieved_query_count}, Added from Graph: {explored_relationships_count}.")
        return enhanced_context

    async def _perform_graph_traversal(self, graph_engine: GraphEngine, request: Dict) -> List[Dict]:
        """Performs a graph traversal based on the request, using canonical props."""
        node_id = request.get(self.node_id_prop)
        rel_type_requested = request.get("relationship_type") # Specific type or None
        direction = request.get("direction", "BOTH").upper()
        max_hops = request.get("max_hops", 1)
        reason = request.get("reason", "No reason provided")

        if not node_id:
            logger.warning("Traversal request missing node ID")
            return []

        logger.debug(f"Performing graph traversal from node '{node_id}', Relationship: '{rel_type_requested or 'ANY'}', Direction: {direction}, Hops: {max_hops}. Reason: {reason}")

        rel_label_cypher = ""
        rel_prop_filter = ""
        if rel_type_requested and isinstance(rel_type_requested, str) and rel_type_requested.strip():
            # Assume edge type is stored as a property on the relationship
            if self.edge_type_prop:
                 rel_prop_filter = f"WHERE r.`{self.edge_type_prop}` = $rel_type"
            else: # Fallback: Assume it's the relationship label itself (less flexible)
                 logger.warning(f"Edge type property '{self.edge_type_prop}' not configured, attempting to match relationship label '{rel_type_requested}'.")
                 rel_label_cypher = f":`{rel_type_requested}`"

        if direction == "OUTGOING": rel_pattern = f"-[r{rel_label_cypher}]->"
        elif direction == "INCOMING": rel_pattern = f"<-[r{rel_label_cypher}]-"
        else: rel_pattern = f"-[r{rel_label_cypher}]-" # BOTH

        try: max_hops = max(1, int(max_hops))
        except (ValueError, TypeError): max_hops = 1
        hops_pattern = f"*1..{max_hops}"

        # Fetch the neighbor node itself and optionally the relationship 'r'
        # Returning 'r' allows capturing the actual edge type traversed if needed
        cypher = f"""
        MATCH (start_node {{{self.node_id_prop}: $start_node_id}})
        MATCH path = (start_node){rel_pattern}{hops_pattern}(neighbor)
        {rel_prop_filter} // Apply property filter if configured and type requested
        WHERE neighbor.`{self.node_id_prop}` <> $start_node_id // Avoid self-loops
        // Return neighbor node and the LAST relationship in the path for context
        WITH neighbor, relationships(path)[-1] AS last_rel
        RETURN DISTINCT neighbor, last_rel
        LIMIT {self.graph_traversal_neighbor_limit}
        """

        params = {"start_node_id": node_id}
        if rel_prop_filter: params["rel_type"] = rel_type_requested

        try:
            raw_results = await graph_engine.graph_db.execute_query(cypher, params)
            neighbors_data = []
            if raw_results and raw_results[0] and raw_results[0].data():
                 for record in raw_results[0].data():
                      if 'neighbor' in record:
                           node_obj = record['neighbor']
                           rel_obj = record.get('last_rel') # Get the relationship object/dict

                           # Extract node properties
                           if hasattr(node_obj, 'properties'): properties = dict(node_obj.properties)
                           elif isinstance(node_obj, dict): properties = node_obj
                           else: properties = {}

                           # Add relationship context to the node data
                           properties['_traversal_source_node_id'] = node_id
                           properties['_traversal_reason'] = reason
                           # Extract actual traversed relationship type if available
                           traversed_rel_type = None
                           if rel_obj:
                               if hasattr(rel_obj, 'properties') and self.edge_type_prop in rel_obj.properties:
                                    traversed_rel_type = rel_obj.properties[self.edge_type_prop]
                               elif isinstance(rel_obj, dict) and self.edge_type_prop in rel_obj:
                                    traversed_rel_type = rel_obj[self.edge_type_prop]
                               elif hasattr(rel_obj, 'type'): # Fallback for relationship label (Neo4j driver specific)
                                    traversed_rel_type = rel_obj.type
                           properties['_traversal_relationship_type'] = traversed_rel_type or "UNKNOWN"

                           neighbors_data.append(properties)

            if not neighbors_data:
                 logger.debug(f"No neighbors found for traversal request: {request}")
                 return []

            # Process graph results into the standard file_info format
            processed_neighbors = await self._process_graph_results(neighbors_data, f"traversal from {node_id}", graph_engine)

            # Assign score and source after standardization
            for n in processed_neighbors:
                n["relevance_score"] = 0.80 # Indicate graph traversal source
                n["source"] = "graph_traversal"

            logger.debug(f"Graph traversal found {len(processed_neighbors)} neighbors for node {node_id}.")
            return processed_neighbors

        except Exception as e:
            logger.exception(f"Error during graph traversal query execution for request {request}: {e}")
            return []

    async def _process_graph_results(self, graph_nodes_data: List[Dict], source_description: str, graph_engine: GraphEngine) -> List[Dict]:
        """Standardizes raw graph node data into the file_info dictionary format."""
        processed_results = []
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

    async def _standardize_graph_node(self, node_data: Dict, source_description: str, graph_engine: Optional[GraphEngine]) -> Optional[Dict]:
        """
        Converts a single raw graph node dict to the standard file_info format.
        Requires `node_dataset_path_prop` to be present.
        Fetches full content via graph_engine if needed and `node_chunk_prop` is missing/short.
        """
        try:
            # Extract using canonical property names
            node_id = node_data.get(self.node_id_prop)
            file_path = node_data.get(self.node_file_path_prop)
            dataset_path = node_data.get(self.node_dataset_path_prop)
            text_chunk = node_data.get(self.node_chunk_prop, "") # Get existing chunk if available
            node_type = node_data.get(self.node_type_prop)
            node_name = node_data.get(self.node_name_prop)
            start_line = node_data.get(self.node_start_line_prop)
            end_line = node_data.get(self.node_end_line_prop)
            timestamp = node_data.get(self.node_timestamp_prop)
            # Capture traversal context if added earlier
            traversal_source_id = node_data.get('_traversal_source_node_id')
            traversal_reason = node_data.get('_traversal_reason')
            traversal_rel_type = node_data.get('_traversal_relationship_type')

            # --- Mandatory Field Checks ---
            if not node_id:
                logger.error(f"Skipping graph result from '{source_description}' due to missing ID. Data: {node_data}")
                return None
            if not file_path:
                logger.warning(f"Graph node {node_id} from '{source_description}' missing file path.")
                file_path = "Unknown"
            if not dataset_path:
                 # This indicates an issue, as dataset_path is mandatory.
                 logger.error(f"CRITICAL: Graph node {node_id} (path: {file_path}) from '{source_description}' missing mandatory '{self.node_dataset_path_prop}'. Skipping.")
                 return None

            # --- Content Fetch Logic ---
            fetched_full_content = False
            # Check if content exists and is sufficiently long, fetch if needed and engine provided
            if graph_engine and (not text_chunk or len(text_chunk.splitlines()) < 5):
                 logger.debug(f"Chunk content for node {node_id} is missing or short. Attempting fetch.")
                 full_content = await self._get_full_file_content_from_graph(node_id, graph_engine)
                 if full_content:
                     text_chunk = full_content # Update with fetched content
                     fetched_full_content = True
                 else:
                     logger.warning(f"Could not retrieve full chunk content for graph node {node_id} from '{source_description}'. Using existing/empty content.")
                     # Decide if content is critical - could return None here if needed

            # Store other potentially useful graph properties, excluding already mapped ones and internal flags
            internal_keys = {
                self.node_id_prop, self.node_name_prop, self.node_file_path_prop,
                self.node_chunk_prop, self.node_dataset_path_prop, self.node_type_prop,
                self.node_timestamp_prop, self.node_start_line_prop, self.node_end_line_prop,
                self.node_scope_prop,
                '_traversal_source_node_id', '_traversal_reason', '_traversal_relationship_type'
            }
            other_props = {k: v for k, v in node_data.items() if k not in internal_keys and not k.startswith('_')}

            # Extract relevant part of the chunk
            relevant_chunk_part = self._extract_relevant_chunk(text_chunk, query="") # Use empty query if original isn't available

            file_info = {
                self.node_dataset_path_prop: dataset_path,
                self.node_file_path_prop: file_path,
                "line_range": self._parse_and_validate_line_range(start_line, end_line, text_chunk),
                "relevant_chunk": relevant_chunk_part, # Extracted relevant part
                self.node_chunk_prop: text_chunk, # Full chunk text
                "relevance_score": 0.80, # Default score for graph results
                "vector_id": node_id, # Use the same ID for consistency across sources
                self.node_id_prop: node_id,
                self.node_name_prop: node_name,
                self.node_type_prop: node_type,
                self.node_timestamp_prop: timestamp,
                "is_in_scope": True, # Default, final filtering happens in _execute_retrieval_plan
                "_fetched_full_content": fetched_full_content,
                "_graph_node_properties": other_props, # Store extra graph props
                "_traversal_source_node_id": traversal_source_id,
                "_traversal_reason": traversal_reason,
                "_traversal_relationship_type": traversal_rel_type,
            }
            # Clean up None values
            return {k: v for k, v in file_info.items() if v is not None}
        except Exception as e:
            logger.exception(f"Error standardizing graph node {node_data.get(self.node_id_prop)} from '{source_description}': {e}")
            return None

    async def _get_details_for_id(self, node_id: str, graph_engine: GraphEngine) -> Optional[Dict]:
        """Gets all canonical properties for a given node ID from the graph."""
        logger.debug(f"Getting details for node ID from graph: {node_id}")
        if not node_id: return None
        try:
            cypher = f"""
            MATCH (n {{{self.node_id_prop}: $node_id}})
            RETURN n // Return the whole node object
            LIMIT 1
            """
            params = {self.node_id_prop: node_id}
            result = await graph_engine.graph_db.execute_query(cypher, params)

            if result and result[0].data():
                 record = result[0].data()[0]
                 if 'n' in record:
                     node_obj = record['n']
                     if hasattr(node_obj, 'properties'): node_data = dict(node_obj.properties)
                     elif isinstance(node_obj, dict): node_data = node_obj
                     else: return None # Cannot process node object

                     # Standardize the retrieved node data, pass engine for potential content fetch
                     standardized_node = await self._standardize_graph_node(node_data, f"details fetch for {node_id}", graph_engine)

                     if standardized_node:
                          # Assign a slightly higher score as it was explicitly requested
                          standardized_node["relevance_score"] = 0.85
                          standardized_node["_fetched_full_content"] = True # Assume full content is present if fetched directly
                          standardized_node["source"] = "graph_direct_fetch"
                          return standardized_node
        except Exception as e:
             logger.exception(f"Graph lookup failed for ID {node_id}: {e}")

        logger.warning(f"Could not find details for node ID in graph: {node_id}")
        return None


    # --------------------------------------------------------------------------
    # Stage 4: Comprehensive Response Generation
    # --------------------------------------------------------------------------
    async def _generate_comprehensive_response(self, query: str, context: Dict[str, Any], datasets: List[str]) -> Dict[str, Any]:
        """Generates the final, structured response using the enhanced context."""
        logger.info("Generating comprehensive response...")
        start_time = time.time()
        llm_client = get_llm_client()
        graph_engine = await get_graph_engine()

        limited_relevant_files = sorted(
            context.get("relevant_files", []),
            key=lambda x: x.get("relevance_score", 0),
            reverse=True
        )[:self.max_final_results]

        # --- Get Combined Type Vocabulary (Dynamic + Static) ---
        involved_datasets = list(set(f.get(self.node_dataset_path_prop) for f in limited_relevant_files if f.get(self.node_dataset_path_prop)))
        if not involved_datasets: involved_datasets = datasets # Fallback if no relevant files had dataset path

        dynamic_types = await self._get_dynamic_type_vocabulary(involved_datasets, graph_engine)
        static_nodes, static_edges = self._get_static_types_for_datasets(involved_datasets)
        available_node_types = sorted(list(set(dynamic_types.get("node_types", []) + static_nodes)))
        available_edge_types = sorted(list(set(dynamic_types.get("edge_types", []) + static_edges)))

        # Prepare results for the prompt, cleaning internal flags
        results_for_prompt = []
        for file_info in limited_relevant_files:
             info_copy = file_info.copy()
             keys_to_remove = [
                 "_might_need_full_content", "_fetched_full_content", "_raw_payload",
                 "_traversal_reason", "_traversal_source_node_id", "_traversal_relationship_type",
                 "is_in_scope", "source", "_graph_node_properties",
                 "vector_id", # Prefer canonical node_id_prop
                 # Decide whether to pass full chunk or just relevant part/summary
                 # self.node_chunk_prop, # Remove full chunk to save tokens?
             ]
             for key in keys_to_remove: info_copy.pop(key, None)

             # Optionally shorten relevant_chunk if too long
             if "relevant_chunk" in info_copy and len(info_copy["relevant_chunk"]) > 1000:
                 info_copy["relevant_chunk"] = info_copy["relevant_chunk"][:1000] + "..."

             results_for_prompt.append(info_copy)

        relationship_summary = self._summarize_relationships(limited_relevant_files)

        prompt_context = {
            "query": query,
            "datasets": ", ".join(sorted(involved_datasets)),
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
            logger.error(f"Error rendering final response prompts: {e}")
            system_prompt = "You are a helpful code assistant..." # Fallback
            user_prompt = f"Summarize findings for query: {query} based on provided context..." # Fallback

        # Define the structured output schema using combined types
        summary_schema = {
            "type": "object", "properties": {
                "overview": {"type": "string", "description": "High-level architectural overview based on provided chunks."},
                "key_components": {"type": "string", "description": f"Analysis of important files/functions/classes (types like {', '.join(available_node_types[:3])}...) and relationships."},
                "implementation_details": {"type": "string", "description": "Deep dive into algorithms or techniques visible in the chunks."},
                "technical_considerations": {"type": "string", "description": "Analysis of performance, security, etc., *only if directly evident in chunks*."},
                "code_relationships": {"type": "string", "description": f"How components interact based on graph traversals (using edge types like {', '.join(available_edge_types[:3])}...) and code chunks."},
                "pattern_identification": {"type": "string", "description": f"Design patterns identified based on structure (involving node types like {', '.join(available_node_types[:3])}...) and code chunks."},
                "navigation_guidance": {"type": "string", "description": "Advice on navigating the *provided chunks and identified relationships*."},
                "follow_up_suggestions": {"type": "array", "items": {"type": "string"}, "description": "Suggested follow-up questions based on the analysis."}
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
                if content and isinstance(content, str) and content.strip() and "N/A" not in content and "not evident" not in content.lower():
                    formatted_summary += f"## {title}\n{content.strip()}\n\n"

            suggestions = summary_response.get("follow_up_suggestions")
            if suggestions and isinstance(suggestions, list) and any(s.strip() for s in suggestions if isinstance(s, str)):
                 formatted_summary += "## Follow-up Questions\n"
                 for i, suggestion in enumerate(suggestions):
                     if suggestion and isinstance(suggestion, str) and suggestion.strip():
                          formatted_summary += f"{i+1}. {suggestion.strip()}\n"

            duration = time.time() - start_time
            logger.info(f"Comprehensive response generated successfully in {duration:.2f}s.")

            # Clean final results before returning
            final_relevant_files = self._clean_results_for_output(limited_relevant_files)
            final_out_of_scope = self._clean_results_for_output(context.get("out_of_scope_results", []))

            return {
                "summary": formatted_summary.strip(),
                "relevant_files": final_relevant_files,
                "out_of_scope_results": final_out_of_scope
            }
        except Exception as e:
            logger.exception(f"LLM Error generating comprehensive response: {str(e)}")
            duration = time.time() - start_time
            logger.info(f"Response generation failed after {duration:.2f}s.")
            # Fallback summary
            fallback_summary = f"Found {len(limited_relevant_files)} relevant code chunks for query: '{query}'.\n"
            fallback_summary += "Detailed analysis could not be generated due to an internal error.\n"
            if limited_relevant_files:
                fallback_summary += "Key files identified:\n"
                for f in limited_relevant_files[:3]:
                    fallback_summary += f"- {f.get(self.node_file_path_prop)} (Dataset: {f.get(self.node_dataset_path_prop)})\n"

            # Clean results even for fallback
            final_relevant_files = self._clean_results_for_output(limited_relevant_files)
            final_out_of_scope = self._clean_results_for_output(context.get("out_of_scope_results", []))

            return {
                "summary": fallback_summary,
                "relevant_files": final_relevant_files,
                "out_of_scope_results": final_out_of_scope
            }

    def _clean_results_for_output(self, results: List[Dict]) -> List[Dict]:
        """Removes internal flags and properties before returning results to the user."""
        cleaned_results = []
        keys_to_remove = [
            "_might_need_full_content", "_fetched_full_content", "_raw_payload",
            "_traversal_reason", "_traversal_source_node_id", "_traversal_relationship_type",
            "is_in_scope", "source", "_graph_node_properties",
            "vector_id", # Prefer canonical node_id_prop
            # Optionally remove full chunk if only relevant_chunk is desired in output
            # self.node_chunk_prop,
        ]
        for res in results:
             res_copy = res.copy()
             for key in keys_to_remove:
                 res_copy.pop(key, None)
             cleaned_results.append(res_copy)
        return cleaned_results

    # --------------------------------------------------------------------------
    # Helper Methods (Refined)
    # --------------------------------------------------------------------------
    def _deduplicate_and_sort_results(self, results: List[Dict], max_count: int) -> List[Dict]:
        """Removes duplicates based on node_id_prop and sorts by relevance score."""
        if not results: return []
        unique_results_dict = {}
        for file_info in results:
            item_id = file_info.get(self.node_id_prop)
            if not item_id:
                logger.warning(f"Result missing '{self.node_id_prop}', cannot reliably deduplicate: {file_info}")
                item_id = file_info.get(self.node_file_path_prop) # Fallback key
                if not item_id: continue

            current_score = file_info.get("relevance_score", 0)
            if item_id not in unique_results_dict or current_score > unique_results_dict[item_id].get("relevance_score", 0):
                unique_results_dict[item_id] = file_info

        sorted_unique = sorted(unique_results_dict.values(), key=lambda x: x.get("relevance_score", 0), reverse=True)
        return sorted_unique[:max_count]

    def _parse_and_validate_line_range(self, start_line: Any, end_line: Any, text_chunk: str = "") -> Dict[str, Optional[int]]:
        """Parses start/end lines, validates, and estimates end if needed."""
        s_line, e_line = None, None
        try: s_line = int(start_line) if start_line is not None else None
        except (ValueError, TypeError): pass
        try: e_line = int(end_line) if end_line is not None else None
        except (ValueError, TypeError): pass

        if s_line is not None and s_line < 0: s_line = None
        if e_line is not None and e_line < 0: e_line = None

        if s_line is not None and e_line is not None and s_line > e_line:
             logger.warning(f"Invalid line range: start ({s_line}) > end ({e_line}). Discarding range.")
             s_line, e_line = None, None

        # Estimate end line based on chunk content if start is known but end isn't
        # Assumes start_line is 1-based from metadata
        if s_line is not None and e_line is None and text_chunk:
             num_lines_in_chunk = text_chunk.count('\n')
             e_line = s_line + num_lines_in_chunk # If s_line=1, chunk has 0 \n -> e_line=1. If 1 \n -> e_line=2.

        return {"start": s_line, "end": e_line}

    def _extract_relevant_chunk(self, full_chunk_text: str, query: str, max_lines: int = 30) -> str:
        """Extracts a relevant portion of the chunk based on query terms."""
        if not full_chunk_text or not isinstance(full_chunk_text, str): return ""
        lines = full_chunk_text.splitlines()
        if len(lines) <= max_lines: return full_chunk_text # Return full chunk if short

        # Simple keyword matching for relevance scoring
        query_terms = set(term.lower() for term in re.findall(r'\b\w{3,}\b', query.lower()))
        if not query_terms and query.strip(): # Handle non-word queries slightly better
             query_terms = set(query.lower().split())
        if not query_terms: return "\n".join(lines[:max_lines]) # Return top if no useful terms

        line_scores = []
        for i, line in enumerate(lines):
            line_lower = line.lower()
            score = sum(1 for term in query_terms if term in line_lower)
            line_scores.append((i, score))

        # Find the window with the highest score sum
        best_score, best_start_line_idx = -1, 0
        # Calculate initial window score safely
        current_window_score = sum(score for _, score in line_scores[:min(max_lines, len(lines))])

        if current_window_score >= 0:
             best_score, best_start_line_idx = current_window_score, 0

        # Slide window
        for i in range(max_lines, len(lines)):
            current_window_score += line_scores[i][1] - line_scores[i - max_lines][1]
            if current_window_score > best_score:
                 best_score, best_start_line_idx = current_window_score, i - max_lines + 1

        # If no terms matched anywhere, return the beginning
        if best_score <= 0 and all(s == 0 for _, s in line_scores):
            return "\n".join(lines[:max_lines])

        start_idx = best_start_line_idx
        end_idx = min(len(lines), start_idx + max_lines)

        # Add ellipsis for context
        extracted_lines = lines[start_idx:end_idx]
        prefix = "...\n" if start_idx > 0 else ""
        suffix = "\n..." if end_idx < len(lines) else ""
        return prefix + "\n".join(extracted_lines) + suffix

    async def _perform_basic_search(self, query: str, datasets: List[str], limit: int = 5) -> List[Dict]:
        """
        Performs basic vector search, filters by dataset, returns simplified results.
        Result dict contains 'id', 'score', 'payload'. Requires dataset_path in payload.
        """
        logger.debug(f"Performing basic search for: '{query}' in datasets: {datasets}")
        vector_engine = get_vector_engine()
        results_with_payload = []
        vector_filter = self._create_vector_filter(datasets)
        processed_ids = set()

        search_tasks = []
        use_local_filtering = False
        fetch_limit = limit * 2 # Fetch more initially

        for collection in self.vector_collections:
             try:
                  search_tasks.append(
                      vector_engine.search(collection, query, limit=fetch_limit, filter=vector_filter)
                  )
             except NotImplementedError:
                  logger.warning(f"Vector engine filter not supported for '{collection}'. Fetching more results and filtering locally.")
                  use_local_filtering = True
                  search_tasks.append(
                      vector_engine.search(collection, query, limit=fetch_limit * len(datasets)) # Fetch even more
                  )
             except Exception as e:
                  logger.error(f"Error preparing basic search for collection {collection}: {e}")

        if not search_tasks: return []

        results_per_collection = await asyncio.gather(*search_tasks, return_exceptions=True)

        for res_list in results_per_collection:
            if isinstance(res_list, list):
                for res in res_list:
                    payload = res.payload or {}
                    metadata = payload.get("metadata", {})
                    node_id = metadata.get(self.node_id_prop) or payload.get(self.node_id_prop)
                    dataset_path = metadata.get(self.node_dataset_path_prop) or payload.get(self.node_dataset_path_prop)

                    if not node_id or node_id in processed_ids: continue

                    # Critical check: dataset_path must exist
                    if not dataset_path:
                         logger.error(f"Basic search result missing dataset path for ID {node_id}. Skipping.")
                         continue

                    # Filter locally if needed
                    if use_local_filtering and dataset_path not in datasets:
                         continue

                    # Passed filters, add to results
                    results_with_payload.append({
                        "id": node_id, # Key for detail fetching consistency
                        "score": res.score,
                        "payload": payload # Pass full payload for potential use
                    })
                    processed_ids.add(node_id)
                    # Optimization: Stop processing early if we have enough candidates after local filtering
                    if use_local_filtering and len(results_with_payload) >= limit * 3: break
            if use_local_filtering and len(results_with_payload) >= limit * 3: break


        results_with_payload.sort(key=lambda x: x["score"], reverse=True)
        logger.debug(f"Basic search found {len(results_with_payload[:limit])} results matching criteria for '{query}'")
        return results_with_payload[:limit]

    def _summarize_relationships(self, relevant_files: List[Dict]) -> str:
         """Creates a simple text summary of relationships found via traversal."""
         summary_lines = []
         for file_info in relevant_files:
             if file_info.get("source") == "graph_traversal":
                 source_node_id = file_info.get("_traversal_source_node_id", "Unknown source")
                 rel_type = file_info.get("_traversal_relationship_type", "UNKNOWN_REL")
                 target_path = file_info.get(self.node_file_path_prop, "Unknown target")
                 target_id = file_info.get(self.node_id_prop, "???")
                 reason = file_info.get("_traversal_reason", "")

                 summary_line = f"- Found related item `{target_path}` (ID: ...{target_id[-8:]})"
                 details = []
                 if rel_type != "UNKNOWN_REL": details.append(f"Rel: {rel_type}")
                 if source_node_id != "Unknown source": details.append(f"From: ...{source_node_id[-8:]}")
                 if reason: details.append(f"Reason: {reason}")
                 if details: summary_line += f" ({', '.join(details)})"

                 summary_lines.append(summary_line)

         if not summary_lines:
             return "No specific code relationships were explicitly explored via graph traversal in this step."

         max_summary_lines = 7
         summary = "Relationships identified via graph traversal:\n" + "\n".join(summary_lines[:max_summary_lines])
         if len(summary_lines) > max_summary_lines:
             summary += f"\n... (and {len(summary_lines) - max_summary_lines} more related items found)"
         return summary

    async def _get_dynamic_type_vocabulary(self, datasets: List[str], graph_engine: GraphEngine) -> Dict[str, List[str]]:
        """
        Fetches distinct node and edge types from the graph, scoped by dataset paths.
        Uses an in-memory LRU cache with TTL.
        """
        if not datasets:
             logger.warning("Cannot fetch dynamic type vocabulary without specified datasets.")
             return {"node_types": [], "edge_types": []}

        # Create a stable cache key from the sorted dataset list
        cache_key = "vocab:" + ",".join(sorted(datasets))

        # Check cache (including TTL)
        if cache_key in self.type_vocabulary_cache:
            cached_data, timestamp = self.type_vocabulary_cache[cache_key]
            if time.time() - timestamp < self.type_cache_ttl_seconds:
                logger.debug(f"Type vocabulary cache hit for datasets: {datasets}")
                self.type_vocabulary_cache.move_to_end(cache_key) # Mark as recently used
                return cached_data
            else:
                logger.debug(f"Type vocabulary cache expired for datasets: {datasets}")
                del self.type_vocabulary_cache[cache_key] # Remove expired entry

        logger.debug(f"Type vocabulary cache miss for datasets: {datasets}. Querying graph.")
        node_types = []
        edge_types = []

        try:
            params = {"datasets": datasets}
            # Query for distinct node types
            node_cypher = f"""
            MATCH (n)
            WHERE n.`{self.node_dataset_path_prop}` IN $datasets
              AND n.`{self.node_type_prop}` IS NOT NULL
            RETURN DISTINCT n.`{self.node_type_prop}` AS nodeType
            LIMIT {self.dynamic_node_types_top_n}
            """
            node_result = await graph_engine.graph_db.execute_query(node_cypher, params)
            if node_result and node_result[0].data():
                 node_types = [record['nodeType'] for record in node_result[0].data() if record.get('nodeType')]

            # Query for distinct edge types (by property or label)
            if self.edge_type_prop: # Edge type is a property
                edge_cypher = f"""
                MATCH (n)-[r]->(m)
                WHERE n.`{self.node_dataset_path_prop}` IN $datasets
                  AND r.`{self.edge_type_prop}` IS NOT NULL
                RETURN DISTINCT r.`{self.edge_type_prop}` AS edgeType
                LIMIT {self.dynamic_edge_types_top_n}
                """
            else: # Edge type is the relationship label
                edge_cypher = f"""
                MATCH (n)-[r]->(m)
                WHERE n.`{self.node_dataset_path_prop}` IN $datasets
                RETURN DISTINCT type(r) AS edgeType
                LIMIT {self.dynamic_edge_types_top_n}
                """
            edge_result = await graph_engine.graph_db.execute_query(edge_cypher, params)
            if edge_result and edge_result[0].data():
                 edge_types = [record['edgeType'] for record in edge_result[0].data() if record.get('edgeType')]

        except Exception as e:
             logger.exception(f"Failed to query dynamic type vocabulary for datasets {datasets}: {e}")
             # Return empty on error, don't cache failure
             return {"node_types": [], "edge_types": []}

        vocabulary = {"node_types": sorted(list(set(node_types))), "edge_types": sorted(list(set(edge_types)))}

        # --- Store in cache ---
        if len(self.type_vocabulary_cache) >= self.type_cache_max_size:
            # Remove the least recently used item (first item in OrderedDict)
            lru_key, _ = self.type_vocabulary_cache.popitem(last=False)
            logger.debug(f"Type vocabulary cache full. Removed LRU entry: {lru_key}")

        self.type_vocabulary_cache[cache_key] = (vocabulary, time.time())
        logger.debug(f"Stored type vocabulary in cache for datasets: {datasets}")

        return vocabulary

    def _get_static_types_for_datasets(self, datasets: List[str]) -> Tuple[List[str], List[str]]:
        """
        Retrieves static node and edge types for the given datasets from the loaded map.
        Needs self.static_types_map to be populated by _load_static_types.
        """
        static_nodes = set()
        static_edges = set()

        if not self.static_types_map:
             logger.warning("Static types map is not loaded. Cannot retrieve static types.")
             return [], []

        for dataset_path in datasets:
            if dataset_path in self.static_types_map:
                types_data = self.static_types_map[dataset_path]
                static_nodes.update(types_data.get("static_node_types", []))
                static_edges.update(types_data.get("static_edge_types", []))
            else:
                logger.debug(f"No static types defined in map for dataset: {dataset_path}")

        return sorted(list(static_nodes)), sorted(list(static_edges))
