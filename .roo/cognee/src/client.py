import asyncio
import aiohttp
import os

sse_host = os.getenv("COGNEE_SSE_HOST", "localhost")
sse_port = os.getenv("COGNEE_SSE_PORT", "8000")

async def sse_client(url: str):
    """
    Connects to the SSE endpoint at the given URL and prints out each event.
    """
    print(f"Connecting to SSE endpoint at: {url}")
    try:
        async with aiohttp.ClientSession() as session:
            # Send a GET request which should return a stream of SSE data.
            async with session.get(url) as response:
                if response.status != 200:
                    print(f"Error: Received HTTP {response.status}")
                    return

                print("SSE connection established. Listening for events...\n")

                # Reading the response stream line by line.
                async for line in response.content:
                    if line:
                        # SSE events typically prefix data lines with "data:".
                        decoded_line = line.decode("utf-8").strip()
                        if decoded_line.startswith("data:"):
                            # Remove the "data:" prefix and print the payload.
                            event_data = decoded_line[len("data:"):].strip()
                            print("Received event:", event_data)
                        else:
                            # You may receive blank lines or retry data.
                            print("Received:", decoded_line)
    except Exception as e:
        print(f"Exception while connecting to SSE endpoint: {e}")

async def main():
    # Assuming that the SSE server is exposed on the port defined in the devcontainer environment.
    # For example, if COGNEE_SSE_HOST is 0.0.0.0 and COGNEE_SSE_PORT is 8000, then from within Docker:
    sse_url = f"http://cognee-mcp:{sse_port}/sse"  # Adjust if your SSE endpoint path is different (e.g. http://localhost:8000/sse)
    await sse_client(sse_url)

if __name__ == "__main__":
    asyncio.run(main())
