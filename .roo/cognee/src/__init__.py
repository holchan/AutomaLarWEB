from .server import run_sse_server as server_main

def main():
    """Main entry point for the package."""
    import asyncio

    asyncio.run(server_main())
