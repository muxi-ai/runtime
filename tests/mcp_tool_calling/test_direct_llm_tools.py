#!/usr/bin/env python3
"""Test OneLLM directly with tools"""

import asyncio
from onellm import ChatCompletion, set_api_key
import os

async def main():
    # Set API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not set")
        return
        
    set_api_key(api_key, "openai")
    
    # Define tools in OpenAI format
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
        {"role": "system", "content": "You are a helpful assistant with file creation tools."},
        {"role": "user", "content": "Create a file at /tmp/test_onellm.txt with content 'Hello OneLLM!'"}
    ]
    
    print("Calling OneLLM with tools...")
    print(f"Tools: {tools}")
    
    try:
        # Call with tools parameter
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
            print(f"\nMessage: {message}")
            
            # Check for tool calls
            if isinstance(message, dict) and "tool_calls" in message:
                print(f"\nTool calls found: {message['tool_calls']}")
            else:
                print("\nNo tool calls found in message")
                
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())