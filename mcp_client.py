import os
import asyncio
import aiohttp
import requests
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
        print(f"🔧 Using tool: {tool_name}")
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
    return {"error": f"id:{task_id} Timeout or failure",
             "last_response": status_response}

async def test_tool():
    tools = await get_tools()
    if not tools:
        print("❌ No tools available.")
        return

    selected_tool = tools[-1]
    tool_name = selected_tool['name']
    print(f"🔧 Selected tool: {tool_name}")

    # Call the selected tool with sample args
    initial_response = await call_tool(tool_name, {"n": 10})
    task_id = initial_response.get("task_id")

    if not task_id:
        print("❌ Failed to retrieve task_id.")
        return
    # Wait for the result
    result = await wait_for_completion(task_id)
    del result['logger']
    del result['version']
    print("✅ Result:")
    print(json.dumps(result, indent=2))

async def openai_call_tools(res):
    """Extract and invoke tool calls from the assistant's response."""
    if 'tool_calls' not in res: return []

    results = []
    for call in res['tool_calls']:
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
                if 'ret' in result:                    
                    del result['logger']
                    del result['version']
                    # result = result['ret']
                elif 'error' in result:
                    raise Exception(result['error'])
            else:
                result = initial_response

            results[-1]['content'] = json.dumps(result)
        except Exception as e:
            results[-1]['content'] = f"Error calling tool (id:{task_id}): {str(e)}"
    return results

def mcp_to_openai_tool(tools) -> list:
    if not isinstance(tools, list):
        tools = [tools]        
    openai_tools = []
    for tool in tools:
        tool = json.loads(json.dumps(tool))
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool['name'],
                "description": tool['description'],
                "parameters": tool['inputSchema'],
            },
        }
        openai_tools.append(openai_tool)        
    return openai_tools

async def llm(messages, tools=[]):
    API_KEY = os.getenv("OPENAI_API_KEY")
    API_URL = "https://api.openai.com/v1/chat/completions"
    HEADERS = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    if type(messages) == str:
        messages = [{"role": "user", "content": messages}]
    body = {
        "model": "gpt-4.1", "messages": messages,
        "tools": tools, "tool_choice": "auto"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(API_URL,
                    headers=HEADERS, json=body) as response:
            response.raise_for_status()
            result = await response.json()
            message = result["choices"][0]["message"]
            # Return full message including potential tool calls
            if "tool_calls" in message:
                return {
                    "content": message.get("content", ""),
                    "tool_calls": message["tool_calls"],
                }
            return message["content"]

async def one_query(ask:str='How many "r" in "raspberry"?',
                    llm=llm,tools=[]):
    # Initialize structured messages
    messages = [{"role": "user", "content": ask}]
    # First assistant response (might suggest a tool)
    res = await llm(messages,tools)
    # Handle tool calls
    if "tool_calls" not in res: return res
    # Insert assistant message with tool_calls
    messages.append({
        "role": "assistant",
        # might be empty or partial
        "content": res.get("content", ""),
        "tool_calls": res["tool_calls"]
    })
    # Run the tool(s)
    tool_results = await openai_call_tools(res)
    print("\n📊 Tool results:")
    for result in tool_results:
        print(f"  🔹 Tool: {result['name']}")
        try:
            content_obj = json.loads(result['content'])
            print(f"  🔹 Content: {json.dumps(content_obj, indent=2)}")
        except:
            print(f"  🔹 Content: {result['content']}")
    # For each tool call, insert a 'tool' message
    for i, tr in enumerate(tool_results):
        messages.append({
            "role": "tool",
            "tool_call_id": res["tool_calls"][i]["id"],  # MUST match
            "name": tr["name"],"content": tr["content"]
        })
    # Now ask assistant for final response
    messages.append({
        "role": "user",
        "content": "Please give me the final answer."
    })
    return await llm(messages)

if __name__ == "__main__":
    print("🔍 Fetching available tools...")
    mcp_ts = asyncio.run(get_tools())
    op_ts = mcp_to_openai_tool(mcp_ts)
    print(f"✅ Found {len(op_ts)} tools\n")
    
    print("🧪 Testing tool functionality...")
    asyncio.run(test_tool())
    print("\n")
    
    print("#### 🤖 Asking LLM about available tools...")
    response = asyncio.run(llm('Tell me your available tools.',tools=op_ts))
    print(f"🔹 Response:\n{response}\n")    
    # Here are the available tools I can use for you:
    # 1. Fibonacci Calculator: Compute Fibonacci numbers in "fast" or "slow" mode.
    # 2. Prime Number Checker: Check if a number is prime, with "smart" or "basic" modes.
    # 3. Palindrome Checker: Determine if a string is a palindrome, using "smart" or "basic" checks.
    # 4. ChatGPT Service: Interact with OpenAI's GPT models (chat, Q&A, etc.).
    # 5. File Downloader: Download files from a given URL (with optional Redis upload).
    # 6. Binary Representation: Get the binary representation of integers (custom bit length optional).
    # 7. Collatz Sequence: Compute the Collatz sequence for a starting integer.
    # 8. Smart Model Converter: Generate Python code to convert between model schemas.
    # 9. Upload to FTP: Upload files to an FTP server.
    # 10. HTTP Request Task: Send GET or POST HTTP requests to URLs.
    # 11. Pipelines Management: Create, configure, list, refresh, and delete task pipelines.
    # 12. Task Management: List, get metadata, stop, or delete running tasks.
    # 13. Workers Management: List available workers.
    # 14. Perform Actions: List available actions and execute them with precise scheduling.
    # If you want details about a specific tool or wish to use one, please let me know!
    
    print("#### 🧮 Testing tool usage with Fibonacci calculation...")
    result = asyncio.run(one_query('Calculate Fibocci number of 43.',tools=op_ts))
    print(f"🔹 Final result:\n{result}")

    print("#### 🧮 Testing tool usage with Palindrome check...")
    result = asyncio.run(one_query('Is "racecar" a palindrome?',tools=op_ts))
    print(f"🔹 Final result:\n{result}")

    print("#### 🧮 Testing tool usage with Prime number check...")
    result = asyncio.run(one_query('Is 17 a prime number?',tools=op_ts))
    print(f"🔹 Final result:\n{result}")

                
