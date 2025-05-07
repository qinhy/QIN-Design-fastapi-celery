import asyncio
from fastmcp import Client
from fastmcp.client.transports import SSETransport

sse_url = "http://localhost:8000/mcp"

client_inferred = Client(sse_url)

headers = {"Authorization": "Bearer mytoken"}
transport_explicit = SSETransport(url=sse_url, headers=headers)
client_explicit = Client(transport_explicit)

async def use_sse_client(client):
    async with client:
        tools = await client.list_tools()
        # print(f"Connected via SSE, found tools: {tools}")
        return tools
# asyncio.run(use_sse_client(client_explicit))

ts = asyncio.run(use_sse_client(client_inferred))
print([t.name for t in ts])