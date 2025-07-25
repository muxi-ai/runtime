#!/usr/bin/env python3
"""Test agent tool calling with mock MCP tools"""

import asyncio
import sys
import json
from typing import Dict, Any, List, Optional

sys.path.insert(0, ".")

from src.muxi.formation.agents.agent import Agent
from src.muxi.services.llm import LLM
from src.muxi.services import observability


class MockOverlord:
    """Mock overlord with MCP tools"""
    def __init__(self):
        self.mcp_service = MockMCPService()
        self.secrets_interpolator = None

    async def add_message_to_memory(self, **kwargs):
        pass


class MockMCPService:
    """Mock MCP service with filesystem tools"""
    def __init__(self):
        self.tool_registry = {
            "filesystem": {
                "create_file": {
                    "name": "create_file",
                    "description": "Create a file with specified content",
                    "inputSchema": {
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
                },
                "read_file": {
                    "name": "read_file",
                    "description": "Read content from a file",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "The file path to read"
                            }
                        },
                        "required": ["path"]
                    }
                }
            }
        }

    async def invoke_tool(self, server_id: str, tool_name: str, parameters: Dict[str, Any], **kwargs):
        """Mock tool invocation"""
        if tool_name == "create_file":
            path = parameters.get("path")
            content = parameters.get("content")
            # Actually create the file
            with open(path, "w") as f:
                f.write(content)
            return {"status": "success", "message": f"File created at {path}"}
        elif tool_name == "read_file":
            path = parameters.get("path")
            with open(path, "r") as f:
                content = f.read()
            return {"status": "success", "content": content}
        else:
            return {"status": "error", "message": f"Unknown tool: {tool_name}"}


async def main():
    # Skip observability initialization for this test

    # Create LLM
    model = LLM(model="openai/gpt-4o-mini")

    # Create mock overlord
    overlord = MockOverlord()

    # Create agent with system message about tools
    agent = Agent(
        model=model,
        overlord=overlord,
        system_message="You are a helpful assistant with access to filesystem tools. Use the create_file tool when asked to create files.",
        agent_id="test_agent"
    )

    # Override the invoke_tool method to use our mock
    async def mock_invoke_tool(tool_name: str, parameters: Dict[str, Any], server_id: Optional[str] = None, **kwargs):
        """Mock tool invocation"""
        actual_server_id = server_id or "filesystem"
        return await overlord.mcp_service.invoke_tool(actual_server_id, tool_name, parameters)

    agent.invoke_tool = mock_invoke_tool

    print("Testing agent with MCP tools...")

    # Send a message asking to create a file
    try:
        response = await agent.process_message(
            "Create a file at /tmp/test_agent_file.txt with the content 'Hello from agent with tools!'"
        )
    except Exception as e:
        print(f"Error processing message: {e}")
        import traceback
        traceback.print_exc()
        return

    print(f"\nAgent response: {response.content}")

    # Check if file was created
    import os
    if os.path.exists("/tmp/test_agent_file.txt"):
        with open("/tmp/test_agent_file.txt", "r") as f:
            content = f.read()
        print(f"\n✅ SUCCESS! File created with content: {content}")
        os.remove("/tmp/test_agent_file.txt")
    else:
        print("\n❌ FAILED: File was not created")


if __name__ == "__main__":
    asyncio.run(main())
