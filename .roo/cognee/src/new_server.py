# server.py
import sys
import asyncio
import json
from contextlib import redirect_stdout, contextmanager
import mcp.types as types
from mcp.server import Server

# Attempt to import Cognee components safely
try:
    from cognee.modules.search.types import SearchType
    from cognee.shared.logging_utils import get_logger
    logger = get_logger(__name__)
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.warning("Could not import Cognee logger, using standard Python logging.")
    # Define SearchType enum fallback if needed
    from enum import Enum
    class SearchType(Enum):
        DEV_CODE = "DEV_CODE"
        CODE = "CODE"
        GRAPH_COMPLETION = "GRAPH_COMPLETION"
        # Add other types Cognee actually supports

# Import your custom retriever
try:
    from custom_dev_retriever import DevCodeRetriever
except ImportError as e:
    logger.error(f"CRITICAL: Failed to import DevCodeRetriever from custom_dev_retriever.py! Error: {e}")
    DevCodeRetriever = None # Set to None to handle gracefully

# Create MCP server
mcp = Server("dev_assistant")

@contextmanager
def log_mcp_stdout():
    """Redirects stdout to stderr for logging within MCP context."""
    original_stdout = sys.stdout
    try:
        sys.stdout = sys.stderr
        yield
    finally:
        sys.stdout = original_stdout

@mcp.list_tools()
async def list_tools() -> list[types.Tool]:
    search_type_enum = [st.name for st in SearchType] if 'SearchType' in globals() and hasattr(SearchType, '__members__') else ["DEV_CODE", "CODE", "GRAPH_COMPLETION"]
    if "DEV_CODE" not in search_type_enum: search_type_enum.insert(0, "DEV_CODE")
    search_type_enum = sorted(list(set(search_type_enum)))

    return [
        types.Tool(
            name="search",
            description="Searches for code/text information. Use DEV_CODE for deep analysis, others for specific retrieval types.",
            inputSchema={
                "type": "object",
                "properties": {
                    "search_query": { "type": "string", "description": "Natural language query." },
                    "search_type": { "type": "string", "description": "Search method.", "enum": search_type_enum, "default": "DEV_CODE" },
                    "datasets": { "type": "array", "description": "Optional: Specific datasets (e.g., repo names) to search within.", "items": { "type": "string" } },
                    "include_trace": { "type": "boolean", "description": "Include detailed execution trace (for debugging).", "default": False },
                    "project_id": { "type": "string", "description": "Optional: Project ID for graph filtering." }
                },
                "required": ["search_query"],
            },
        ),
    ]

@mcp.call_tool()
async def call_tools(name: str, arguments: dict) -> list[types.TextContent]:
    with log_mcp_stdout():
        logger.info(f"Received tool call: {name}")
        logger.debug(f"Arguments: {arguments}")

        if name == "search":
            results = {}
            try:
                query = arguments["search_query"]
                search_type_str = arguments.get("search_type", "DEV_CODE").upper()
                datasets = arguments.get("datasets", None)
                include_trace = arguments.get("include_trace", False)
                project_id = arguments.get("project_id", None)

                if search_type_str == "DEV_CODE":
                    if DevCodeRetriever is None: raise ImportError("DevCodeRetriever failed to import.")
                    logger.info("Using custom DevCodeRetriever...")
                    # --- Pass project_id to retriever ---
                    # Ensure DevCodeRetriever __init__ accepts project_id
                    retriever = DevCodeRetriever(project_id=project_id)
                    # ------------------------------------
                    results = await retriever.get_completion(query, datasets=datasets)
                else:
                    logger.info(f"Using standard Cognee search type: {search_type_str}...")
                    try:
                        import cognee
                        cognee_search_type = SearchType[search_type_str]
                        search_results_raw = await cognee.search(
                            query_type=cognee_search_type, query_text=query, datasets=datasets
                        )
                        # Wrap standard results consistently
                        results = {"summary": f"Standard Cognee Search Results ({search_type_str})", "results": search_results_raw}
                    except KeyError:
                        raise ValueError(f"Invalid Cognee search_type: {search_type_str}. Available: {[st.name for st in SearchType]}")
                    except ImportError:
                        raise ImportError("Cognee library not found for standard search.")
                    except Exception as e:
                        logger.exception(f"Error during standard Cognee search: {e}")
                        raise RuntimeError(f"Error during standard Cognee search: {e}")

                # Remove trace if not requested
                if not include_trace and "trace" in results: del results["trace"]

                logger.info(f"Tool call '{name}' completed successfully.")
                # Use default=str for safety with complex/non-serializable objects
                return [types.TextContent(type="text", text=json.dumps(results, default=str))]

            except Exception as e:
                logger.exception(f"Error processing tool call '{name}': {e}")
                error_payload = {"error": f"Error processing '{name}': {type(e).__name__} - {str(e)}"}
                # Include trace in error response if available and requested
                if include_trace and 'trace' in locals() and trace: error_payload["trace"] = trace
                return [types.TextContent(type="text", text=json.dumps(error_payload))]

        else:
            logger.warning(f"Unknown tool name requested: {name}")
            return [types.TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

async def main():
    if 'logger' not in globals() or logger is None :
         import logging
         global logger
         logger = logging.getLogger(__name__)
         logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
         logger.info("Logger initialized in main.")
    try:
        from mcp.server.stdio import stdio_server
        logger.info("Starting MCP server via stdio...")
        async with stdio_server() as (read_stream, write_stream):
            await mcp.run(read_stream=read_stream, write_stream=write_stream)
        logger.info("MCP server stopped.")
    except ImportError: logger.error("Failed to import mcp.server.stdio. Ensure MCP library is installed.")
    except Exception as e: logger.exception("MCP server failed to start or run.")

if __name__ == "__main__":
    if 'logger' not in globals() or logger is None:
         import logging
         logger = logging.getLogger(__name__)
         logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
         logger.info("Logger initialized in __main__.")
    asyncio.run(main())
