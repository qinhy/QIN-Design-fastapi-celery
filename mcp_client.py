# def client():
#     sse_url = "http://localhost:8000/mcp"
#     headers = {"Authorization": "Bearer mytoken"}
#     client_inferred = Client(sse_url)
#     transport_explicit = SSETransport(url=sse_url, headers=headers)
#     client_explicit = Client(transport_explicit)
#     return client_inferred

import asyncio
import json
from fastmcp import Client
from fastmcp.client.transports import SSETransport

SSE_URL = "http://localhost:8000/mcp"
HEADERS = {}

async def get_tools() -> list:
    """Fetch and return the list of available tools."""
    transport = SSETransport(url=SSE_URL, headers=HEADERS)
    async with Client(transport) as client:
        tools = await client.list_tools()
        return [tool.model_dump() for tool in tools]


async def call_tool(tool_name: str, tool_args: dict) -> dict:
    """Call a tool and return the response as a dictionary."""
    transport = SSETransport(url=SSE_URL, headers=HEADERS)
    async with Client(transport) as client:
        result = await client.call_tool(tool_name, tool_args)
        text_response = next((r.text for r in result if hasattr(r, 'text')), None)
        return json.loads(text_response) if text_response else {}


async def wait_for_completion(task_id: str, timeout: int = 10) -> dict:
    """Poll task status until it's complete or timeout is reached."""
    for _ in range(timeout):
        await asyncio.sleep(1)
        status_response = await call_tool('api_task_meta_tasks_meta__task_id__get', {"task_id": task_id})
        if status_response.get("status") == "SUCCESS":
            return json.loads(status_response["result"])
    return {"error": "Timeout or failure",
             "last_response": status_response}

async def main():
    tools = await get_tools()
    if not tools:
        print("No tools available.")
        return

    # Use the last tool in the list (as in your original code)
    selected_tool = tools[-1]
    tool_name = selected_tool['name']
    print(f"Using tool: {tool_name}")

    # Call the selected tool with sample args
    initial_response = await call_tool(tool_name, {"n": 10})
    task_id = initial_response.get("task_id")

    if not task_id:
        print("Failed to retrieve task_id.")
        return

    # Wait for the result
    result = await wait_for_completion(task_id)
    del result['logger']
    del result['version']
    print("Result:", result)

async def openai_call_tools(res):
    """Extract and invoke tool calls from the assistant's response."""
    if 'calls' not in res: return []

    results = []
    for call in res['calls']:
        tool_data = call.get(call['type'])
        tool_call_id = call['id']
        if not tool_data: continue
        tool_name = tool_data['name']
        tool_args = json.loads(tool_data['arguments'])
        results.append({'role': 'tool','name': tool_name,
            'tool_call_id':tool_call_id})
        try:
            initial_response = await call_tool(tool_name, tool_args)
            if "task_id" in initial_response:
                task_id = initial_response.get("task_id")            
                # Wait for the result
                result = await wait_for_completion(task_id)
                result = result['ret']
            else:
                result = initial_response

            results[-1]['content'] = json.dumps(result)
        except Exception as e:
            results[-1]['content'] = f"Error calling tool: {str(e)}"
    return results

def one_query(llm, ask:str='How many "r" in "raspberrypi"?'):
    
    # Initialize structured messages
    messages = [{"role": "user", "content": ask}]
    # First assistant response (might suggest a tool)
    res = llm(messages)
    # Handle tool calls
    if "calls" not in res: return res
    # Insert assistant message with tool_calls
    messages.append({
        "role": "assistant",
            # might be empty or partial
        "content": res.get("content", ""),
        "tool_calls": res["calls"]
    })
    # Run the tool(s)
    tool_results = asyncio.run(openai_call_tools(res))
    # For each tool call, insert a 'tool' message
    for i, tr in enumerate(tool_results):
        messages.append({
            "role": "tool",
            "tool_call_id": res["calls"][i]["id"],  # MUST match
            "name": tr["name"],"content": tr["content"]
        })
    # Now ask assistant for final response
    messages.append({
        "role": "user",
        "content": "Please give me the final answer."
    })
    return llm(messages)

# if __name__ == "__main__":
#     asyncio.run(main())
