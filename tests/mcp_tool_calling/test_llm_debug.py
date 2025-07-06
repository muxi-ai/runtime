#!/usr/bin/env python3
"""Debug LLM service with tools"""

import asyncio
import sys

sys.path.insert(0, ".")

from src.muxi.runtime.services.llm import LLM


async def main():
    # Create LLM instance
    model = LLM(model="openai/gpt-4o-mini")
    
    # Define tools
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
        {"role": "user", "content": "Create a file at /tmp/test_llm.txt with content 'Hello LLM Service!'"}
    ]
    
    print("Testing LLM service with tools...")
    print(f"Tools: {tools}")
    
    try:
        # Call with tools parameter
        response = await model.chat(messages, tools=tools)
        
        print(f"\nResponse type: {type(response)}")
        print(f"Response: {response}")
                
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())