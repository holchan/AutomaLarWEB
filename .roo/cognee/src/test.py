import asyncio
import aiohttp
import re
import requests
import json

# This function continuously listens for SSE events and puts them in a queue.
async def sse_client_listener(sse_url: str, msg_queue: asyncio.Queue):
    async with aiohttp.ClientSession() as session:
        async with session.get(sse_url) as response:
            if response.status != 200:
                raise Exception(f"Error: HTTP {response.status}")
            # Process the SSE stream line by line.
            async for line in response.content:
                decoded_line = line.decode("utf-8").strip()
                if decoded_line:
                    print(f"[SSE] {decoded_line}")
                if decoded_line.startswith("data:"):
                    # Remove the "data:" prefix and put the payload in the queue.
                    payload = decoded_line[len("data:"):].strip()
                    await msg_queue.put(payload)

# This function loops through SSE messages until a valid session id is found.
async def get_valid_session_id(msg_queue: asyncio.Queue) -> str:
    while True:
        payload = await msg_queue.get()
        # The server sends a URL with a query param "session_id".
        match = re.search(r'session_id=([^&\s]+)', payload)
        if match:
            return match.group(1)

def send_initialize(session_id: str) -> None:
    """
    Sends an initialization request. This is a proper RPC request with an id.
    """
    url = f"http://cognee-mcp:8000/messages/?session_id={session_id}"
    init_payload = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2.0",  # Required field
            "clientInfo": {
                "name": "YourClient",
                "version": "1.0.0"
            },
            "capabilities": {}  # Add your client capabilities if needed
        },
        "id": 0
    }
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, headers=headers, data=json.dumps(init_payload))
    print("Initialize Status Code:", response.status_code)
    print("Initialize Response:", response.text)
    if response.status_code not in (200, 202):
        raise Exception("Initialization failed.")

def send_initialized_notification(session_id: str) -> None:
    """
    Sends an explicit 'initialized' notification.
    Note that notifications should not have an 'id' field.
    """
    url = f"http://cognee-mcp:8000/messages/?session_id={session_id}"
    payload = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",  # Correct literal string expected by the server
        "params": {
            # If additional parameters are required, add them here.
        }
        # No "id" field since this is a notification.
    }
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    print("Initialized Notification Status Code:", response.status_code)
    print("Initialized Notification Response:", response.text)

def send_tool_call(session_id: str) -> None:
    """
    Sends a tool call to execute a specific tool
    (in this case, the 'codify' tool).
    """
    url = f"http://cognee-mcp:8000/messages/?session_id={session_id}"
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "codify",
            "arguments": {"repo_path": "https://github.com/topoteretes/cognee"}
        },
        # tool calls are requests, so we include an id.
        "id": 1
    }
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    print("Tool Call Status Code:", response.status_code)
    print("Tool Call Response:", response.text)

async def main():
    # The SSE endpoint URL. Adjust path if your server exposes it on a different route.
    sse_url = "http://cognee-mcp:8000/sse"
    print(f"Connecting to SSE endpoint at: {sse_url}")

    # Create a queue to collect SSE messages.
    msg_queue = asyncio.Queue()

    # Start the SSE listener as a background task.
    sse_task = asyncio.create_task(sse_client_listener(sse_url, msg_queue))

    # Retrieve a valid session id from one of the SSE messages.
    session_id = await get_valid_session_id(msg_queue)
    print("Obtained valid session id:", session_id)

    # Send the initialization request.
    send_initialize(session_id)

    # Wait briefly for the server to process initialization.
    await asyncio.sleep(2)  # Adjust as needed based on expected delays

    # Send an explicit initialized notification if desired.
    send_initialized_notification(session_id)

    # Invoke the tool call once initialization is assumed complete.
    send_tool_call(session_id)

    # Keep the SSE connection open so we can view responses.
    await asyncio.sleep(5)

    # Cancel the SSE listener task once done.
    sse_task.cancel()
    try:
        await sse_task
    except asyncio.CancelledError:
        print("SSE listener cancelled.")

if __name__ == "__main__":
    asyncio.run(main())
