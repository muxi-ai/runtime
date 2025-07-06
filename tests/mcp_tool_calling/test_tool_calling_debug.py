#!/usr/bin/env python3
"""Debug tool calling with MCP"""

import asyncio
import sys
from pathlib import Path
from onellm import ChatCompletion

sys.path.insert(0, ".")

from src.muxi.runtime.formation.formation import Formation  # noqa: E402


async def test_direct_llm():
    """Test calling LLM directly with tools."""
    # Simple tool definition
    tools = [{
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Create a file with specified content",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The file path"
                    },
                    "content": {
                        "type": "string", 
                        "description": "The file content"
                    }
                },
                "required": ["path", "content"]
            }
        }
    }]
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant with access to file creation tools."},
        {"role": "user", "content": "Create a file at /tmp/test.txt with content 'Hello World'"}
    ]
    
    print("Testing direct LLM call with tools...")
    print(f"Tools: {tools}")
    
    try:
        response = await ChatCompletion.acreate(
            model="openai/gpt-4o-mini",
            messages=messages,
            tools=tools,
            temperature=0.7
        )
        
        print(f"\nResponse type: {type(response)}")
        print(f"Response: {response}")
        
        if hasattr(response, "choices") and response.choices:
            message = response.choices[0].message
            print(f"\nMessage type: {type(message)}")
            print(f"Message content: {getattr(message, 'content', 'No content')}")
            print(f"Has tool_calls: {hasattr(message, 'tool_calls')}")
            if hasattr(message, "tool_calls"):
                print(f"Tool calls: {message.tool_calls}")
                
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


async def test_formation_agent():
    """Test agent with MCP tools."""
    formation_path = Path("test-formations/formation-mcp")
    
    # Load formation
    formation = Formation()
    formation.load(str(formation_path))
    overlord = formation.start_overlord()
    
    # Wait for overlord to be ready
    await overlord.ensure_started()
    
    print("\n\nTesting through formation agent...")
    response = await overlord.chat(
        user_id="test_user",
        message="Create a file at /tmp/test_from_agent.txt with content 'Hello from Agent'",
        use_async=False,
        stream=False,
    )
    
    print(f"Response: {response}")
    
    # Stop overlord
    formation.stop_overlord(10.0)


async def main():
    # Test direct LLM first
    await test_direct_llm()
    
    # Then test through agent
    await test_formation_agent()


if __name__ == "__main__":
    asyncio.run(main())