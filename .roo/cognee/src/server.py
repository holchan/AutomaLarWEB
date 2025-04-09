import asyncio
import json
import os
import sys
import cognee
from cognee.shared.logging_utils import get_logger, get_log_file_location
import importlib.util
from contextlib import redirect_stdout

import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from cognee.api.v1.cognify.code_graph_pipeline import run_code_graph_pipeline
from cognee.modules.search.types import SearchType
from cognee.shared.data_models import KnowledgeGraph
from cognee.modules.storage.utils import JSONEncoder

# Set up the MCP server instance
mcp = Server("cognee")
logger = get_logger()


@mcp.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="cognify",
            description="Cognifies text into knowledge graph",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to cognify",
                    },
                    "graph_model_file": {
                        "type": "string",
                        "description": "The path to the graph model file",
                    },
                    "graph_model_name": {
                        "type": "string",
                        "description": "The name of the graph model",
                    },
                },
                "required": ["text"],
            },
        ),
        types.Tool(
            name="codify",
            description="Transforms codebase into knowledge graph",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                },
                "required": ["repo_path"],
            },
        ),
        types.Tool(
            name="search",
            description="Searches for information in knowledge graph",
            inputSchema={
                "type": "object",
                "properties": {
                    "search_query": {
                        "type": "string",
                        "description": "The query to search for",
                    },
                    "search_type": {
                        "type": "string",
                        "description": "The type of search to perform (e.g., INSIGHTS, CODE)",
                    },
                },
                "required": ["search_query"],
            },
        ),
        types.Tool(
            name="prune",
            description="Prunes knowledge graph",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@mcp.call_tool()
async def call_tools(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        # Redirect stdout to stderr so that MCP communication stays clean.
        with redirect_stdout(sys.stderr):
            log_file = get_log_file_location()

            if name == "cognify":
                asyncio.create_task(
                    cognify(
                        text=arguments["text"],
                        graph_model_file=arguments.get("graph_model_file"),
                        graph_model_name=arguments.get("graph_model_name"),
                    )
                )
                text = (
                    "Background process launched due to MCP timeout limitations.\n"
                    "Average completion time is around 4 minutes.\n"
                    f"For current cognify status you can check the log file at: {log_file}"
                )
                return [types.TextContent(type="text", text=text)]

            if name == "codify":
                asyncio.create_task(codify(arguments.get("repo_path")))
                text = (
                    "Background process launched due to MCP timeout limitations.\n"
                    "Average completion time is around 4 minutes.\n"
                    f"For current codify status you can check the log file at: {log_file}"
                )
                return [types.TextContent(type="text", text=text)]

            elif name == "search":
                search_results = await search(arguments["search_query"], arguments["search_type"])
                return [types.TextContent(type="text", text=search_results)]

            elif name == "prune":
                await prune()
                return [types.TextContent(type="text", text="Pruned")]

    except Exception as e:
        logger.error(f"Error calling tool '{name}': {str(e)}")
        return [types.TextContent(type="text", text=f"Error calling tool '{name}': {str(e)}")]


async def cognify(text: str, graph_model_file: str = None, graph_model_name: str = None) -> str:
    """Build knowledge graph from the input text."""
    with redirect_stdout(sys.stderr):
        logger.info("Cognify process starting.")
        if graph_model_file and graph_model_name:
            graph_model = load_class(graph_model_file, graph_model_name)
        else:
            graph_model = KnowledgeGraph

        await cognee.add(text)

        try:
            await cognee.cognify(graph_model=graph_model)
            logger.info("Cognify process finished.")
        except Exception as e:
            logger.error("Cognify process failed.")
            raise ValueError(f"Failed to cognify: {str(e)}")


async def codify(repo_path: str):
    """Transform the codebase into a knowledge graph."""
    with redirect_stdout(sys.stderr):
        logger.info("Codify process starting.")
        results = []
        async for result in run_code_graph_pipeline(repo_path, False):
            results.append(result)
            logger.info(result)
        if all(results):
            logger.info("Codify process finished successfully.")
        else:
            logger.info("Codify process failed.")


async def search(search_query: str, search_type: str) -> str:
    """Search the knowledge graph."""
    with redirect_stdout(sys.stderr):
        search_results = await cognee.search(
            query_type=SearchType[search_type.upper()], query_text=search_query
        )
        if search_type.upper() == "CODE":
            return json.dumps(search_results, cls=JSONEncoder)
        elif search_type.upper() in ("GRAPH_COMPLETION", "RAG_COMPLETION"):
            return search_results[0]
        else:
            results = retrieved_edges_to_string(search_results)
            return results


async def prune():
    """Reset the knowledge graph."""
    await cognee.prune.prune_data()
    await cognee.prune.prune_system(metadata=True)


def node_to_string(node):
    node_data = ", ".join(
        [f'{key}: "{value}"' for key, value in node.items() if key in ["id", "name"]]
    )
    return f"Node({node_data})"


def retrieved_edges_to_string(search_results):
    edge_strings = []
    for triplet in search_results:
        node1, edge, node2 = triplet
        relationship_type = edge["relationship_name"]
        edge_str = f"{node_to_string(node1)} {relationship_type} {node_to_string(node2)}"
        edge_strings.append(edge_str)
    return "\n".join(edge_strings)


def load_class(model_file, model_name):
    model_file = os.path.abspath(model_file)
    spec = importlib.util.spec_from_file_location("graph_model", model_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, model_name)


# --- Revised SSE Setup ---
def run_sse_server():
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount
    import uvicorn

    # Create an instance of SseServerTransport.
    # (The argument is the URL path where message posts will be handled.)
    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        # The connect_sse() method returns a tuple
        # (read_stream, write_stream) that are passed to the MCP server.
        async with sse.connect_sse(
            request.scope, request.receive, request._send  # type: ignore
        ) as streams:
            await mcp.run(
                read_stream=streams[0],
                write_stream=streams[1],
                initialization_options=InitializationOptions(
                    server_name="cognee",
                    server_version="0.1.0",
                    capabilities=mcp.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
                raise_exceptions=True,
            )

    # Build a Starlette app that exposes two endpoints:
    #  - One for initiating the SSE connection
    #  - One for handling POST messages
    starlette_app = Starlette(
        debug=True,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )

    host = os.getenv("COGNEE_SSE_HOST", "0.0.0.0")
    port = int(os.getenv("COGNEE_SSE_PORT", "8000"))
    logger.info(f"Cognee MCP SSE server starting on {host}:{port}...")
    uvicorn.run(starlette_app, host=host, port=port)


if __name__ == "__main__":
    # Run the SSE server instead of calling a non-existent sse_server context manager.
    run_sse_server()
