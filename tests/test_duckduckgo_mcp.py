#!/usr/bin/env python3
"""Test DuckDuckGo MCP server integration"""

import asyncio
import json
import subprocess
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_duckduckgo_mcp():
    """Test DuckDuckGo MCP server"""

    logger.info("🚀 Starting DuckDuckGo MCP server...")

    # Start the DuckDuckGo MCP server
    process = subprocess.Popen(
        ['python', '-m', 'mcp_duckduckgo.main'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.PIPE,
        text=False,
        bufsize=0
    )

    # Give server time to start
    await asyncio.sleep(2)

    try:
        # Send initialize request
        request_id = 1
        init_request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {"listChanged": True},
                    "sampling": {}
                },
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }

        request_json = json.dumps(init_request) + "\n"
        logger.debug(f"Sending initialize: {request_json.strip()}")
        process.stdin.write(request_json.encode())
        process.stdin.flush()

        await asyncio.sleep(0.2)
        init_response = process.stdout.readline().decode().strip()
        logger.info(f"Initialize response: {init_response}")

        # List tools
        request_id += 1
        list_tools_request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/list",
            "params": {}
        }

        request_json = json.dumps(list_tools_request) + "\n"
        logger.debug(f"Sending tools/list: {request_json.strip()}")
        process.stdin.write(request_json.encode())
        process.stdin.flush()

        await asyncio.sleep(0.2)
        tools_response = process.stdout.readline().decode().strip()
        logger.info(f"Tools list response: {tools_response}")

        # Parse tools
        tools_data = json.loads(tools_response)
        if "result" in tools_data and "tools" in tools_data["result"]:
            tools = tools_data["result"]["tools"]
            logger.info(f"✅ Available tools: {[t.get('name') for t in tools]}")

        # Test web search
        request_id += 1
        search_request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": "web_search",
                "arguments": {
                    "query": "Python programming",
                    "max_results": 3
                }
            }
        }

        request_json = json.dumps(search_request) + "\n"
        logger.debug(f"Sending web_search: {request_json.strip()}")
        process.stdin.write(request_json.encode())
        process.stdin.flush()

        await asyncio.sleep(2)
        search_response = process.stdout.readline().decode().strip()
        logger.info(f"Search response length: {len(search_response)}")

        search_data = json.loads(search_response)
        if "result" in search_data:
            logger.info(f"✅ Search successful!")
            logger.info(f"Result preview: {str(search_data['result'])[:200]}...")
        else:
            logger.error(f"❌ Search failed: {search_data}")

    finally:
        process.terminate()
        await asyncio.sleep(1)
        if process.poll() is None:
            process.kill()
        logger.info("✅ Test complete")

if __name__ == "__main__":
    asyncio.run(test_duckduckgo_mcp())
