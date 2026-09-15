#!/usr/bin/env python3
"""Test calendar functionality to diagnose issues"""

import asyncio
import json
import sys
import os
sys.path.insert(0, '.')

from main_app import AIAssistant

async def test_calendar():
    # Get Gemini API key if available
    gemini_api_key = os.getenv('GEMINI_API_KEY')

    assistant = AIAssistant(gemini_api_key=gemini_api_key)

    try:
        print("🚀 Starting MCP servers...")
        await assistant.start_mcp_servers()

        if 'calendar' not in assistant.mcp_clients:
            print("❌ Calendar MCP server not available")
            return

        print("\n✅ Calendar MCP server is running\n")

        # List available tools
        tools = await assistant.mcp_clients['calendar'].list_tools()
        print(f"📋 Available calendar tools: {[t.get('name') for t in tools]}\n")

        # Get create_event tool details
        create_event_tool = next((t for t in tools if t.get('name') == 'create_event'), None)
        if create_event_tool:
            print("📅 create_event tool schema:")
            print(json.dumps(create_event_tool.get('inputSchema'), indent=2))

        print("\n" + "="*60)
        print("Testing calendar event creation...")
        print("="*60)

        # Test creating an event
        from datetime import datetime, timedelta
        now = datetime.now()
        start_time = now + timedelta(hours=2)
        end_time = start_time + timedelta(hours=1)

        test_params = {
            'summary': 'Test Meeting from AI Assistant',
            'start': {'dateTime': start_time.isoformat() + 'Z'},
            'end': {'dateTime': end_time.isoformat() + 'Z'},
            'attendees': []
        }

        print(f"\n📝 Test parameters:")
        print(json.dumps(test_params, indent=2))

        print("\n⏳ Calling create_event...")
        result = await assistant.mcp_clients['calendar'].call_tool('create_event', test_params)

        print("\n📬 Result:")
        print(result)
        print("="*60)

        if "Error" in result or "error" in result.lower():
            print("\n❌ Calendar event creation FAILED")
            print("💡 Check the error message above for details")
        else:
            print("\n✅ Calendar event creation appears successful")
            print("💡 Check your Google Calendar to verify")

    except Exception as e:
        print(f"\n❌ Exception occurred: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await assistant.cleanup()

if __name__ == "__main__":
    asyncio.run(test_calendar())
