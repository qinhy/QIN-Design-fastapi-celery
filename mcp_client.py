import os
import asyncio
import aiohttp
import requests
import json

BASE_URL = "http://localhost:8000"

async def http_get(url,param={}) -> list:
    """Fetch and return the list of available tools."""
    if param:
        param = [f'{k}={v}' for k,v in param.items()]
        param = '&'.join(param)
        url = f'{url}?{param}'
        
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            result = await response.json()
            return result
            
async def get_tools(format:str='mcp') -> list:
    """Fetch and return the list of available tools."""
    url = f'{BASE_URL}/action/list'
    return await http_get(url,{'format':format})

async def get_task_meta(task_id:str) -> dict:
    url = f'{BASE_URL}/tasks/meta/{task_id}'
    return await http_get(url)

async def call_tool(tool_name: str, tool_args: dict) -> dict:
    """Call a tool and return the response as a dictionary."""
    url = f'{BASE_URL}/action/{tool_name}'
    async with aiohttp.ClientSession() as session:  
        print(f"🔧 Using tool: {tool_name} : {tool_args}")
        async with session.post(url,json=tool_args) as response:
            response.raise_for_status()
            result = await response.json()
            return result
        
async def wait_for_completion(task_id: str, timeout: int = 10) -> dict:
    """Poll task status until it's complete or timeout is reached."""
    for _ in range(timeout):
        await asyncio.sleep(1)
        status_response = await get_task_meta(task_id)
        if status_response.get("status") == "SUCCESS":
            return json.loads(status_response["result"])
    return {"error": f"id:{task_id} Timeout or failure",
             "last_response": status_response}

async def call_and_wait(tool_name: str, tool_args: dict, timeout: int = 10):
    # Call the selected tool with sample args
    initial_response = await call_tool(tool_name, tool_args)
    task_id = initial_response.get("task_id")

    if not task_id:
        print("❌ Failed to retrieve task_id.")
        return
    # Wait for the result
    result = await wait_for_completion(task_id)
    del result['logger']
    del result['version']
    return result

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
            result = await call_and_wait(tool_name, tool_args)            
            if 'error' in result:
                raise Exception(result['error'])
            results[-1]['content'] = json.dumps(result)
        except Exception as e:
            results[-1]['content'] = f"Error calling tool (id:{task_id}): {str(e)}"
    return results

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
        "model": "gpt-4.1-nano", "messages": messages,
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
    op_ts = asyncio.run(get_tools('openai'))
    print(f"✅ Found {len(op_ts)} tools\n")
    
    print("🧪 Testing tool functionality...")
    result = asyncio.run(call_and_wait('Fibonacci', {"args":{"n": 10}}))    
    print("✅ Result:")
    print(json.dumps(result, indent=2))

    print("\n")
    print("#### 🤖 Asking LLM about available tools...")
    response = asyncio.run(llm('Tell me your available tools.',tools=op_ts))
    print(f"🔹 Response:\n{response}\n")    
    # Here are the core tools available for use:

    # 1. Fibonacci Calculator: Computes Fibonacci numbers (supports fast and slow modes).
    # 2. Prime Number Checker: Checks if a number is prime (basic/brute-force or smart/optimized).
    # 3. Palindrome Checker: Checks if a string is a palindrome (basic or smart modes, considering case/spaces).
    # 4. Binary Representation: Converts integers to binary (optionally with bit length).
    # 5. Collatz Sequence Generator: Generates the Collatz sequence from a given number.
    # 6. Downloader: Downloads files from URLs, can also upload to Redis.
    # 7. HTTP Request Task: Makes HTTP GET/POST requests to specific URLs.
    # 8. OpenAI ChatGPT Service: Interacts with OpenAI models for text, code, or multimodal generation.
    # 9. Smart Model Converter: Converts between different class models (for software/service architecture).
    # 10. FTP Uploader: Uploads files to FTP/SFTP servers, supports active/passive mode and base64 input.

    # I can also use several of these at once if needed. If you want details about what a tool can do or how to use it, just ask!

    print("#### 🧮 Testing tool usage with Fibonacci calculation...")
    result = asyncio.run(one_query('Calculate Fibocci number of 43.',tools=op_ts))
    print(f"🔹 Final result:\n{result}")

    print("#### 🧮 Testing tool usage with Palindrome check...")
    result = asyncio.run(one_query('Is "racecar" a palindrome?',tools=op_ts))
    print(f"🔹 Final result:\n{result}")

    print("#### 🧮 Testing tool usage with Prime number check...")
    result = asyncio.run(one_query('Is 17 a prime number?',tools=op_ts))
    print(f"🔹 Final result:\n{result}")

                
