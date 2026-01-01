#!/usr/bin/env python3
"""Base test class for Area 4 MCP tests with standardized patterns."""

import sys
import asyncio
from pathlib import Path
from typing import Dict, Any, Tuple, List
import json

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from muxi.runtime.formation import Formation  # noqa: E402

# Import from common module
from common import BaseE2ETest  # noqa: E402
from common import TestOutputFormatter  # noqa: E402


class BaseMCPTest(BaseE2ETest):
    """Base class for MCP (Model Context Protocol) tests."""

    # Shared formation directory for all MCP tests
    FORMATION_DIR = Path(__file__).parent / "formations" / "formation-mcp"

    # MCP server configurations
    MCP_CONFIGS = {
        "weather": "formation.afs",  # Default with weather MCP
        "memory": "formation-memory.yaml",  # With memory MCP
        "filesystem": "formation-filesystem.yaml",  # File system access
        "multi": "formation-multi.yaml",  # Multiple MCP servers
    }

    def __init__(self, test_name: str = "MCP Test", test_description: str = "MCP test", test_area: str = "4_mcp"):
        """Initialize base MCP test."""
        super().__init__(test_name, test_description, test_area)
        self.formatter = TestOutputFormatter()
        self.formation = None
        self.overlord = None
        self.available_tools = []

    async def setup_mcp_formation(self, mcp_config: str = "weather") -> Formation:
        """Setup formation with MCP servers.

        Args:
            mcp_config: One of the MCP_CONFIGS keys (currently all use formation.afs)

        Returns:
            Configured Formation instance
        """
        # All configs use the same formation.afs for now
        config_file = "formation.afs"
        formation_path = self.FORMATION_DIR / config_file

        self.formation = Formation()
        await self.formation.load(str(formation_path))

        # Store overlord reference
        self.overlord = await self.formation.start_overlord()

        # Get available tools
        await self.discover_tools()

        return self.formation

    async def discover_tools(self) -> List[str]:
        """Discover available MCP tools.

        Returns:
            List of available tool names
        """
        try:
            # Query overlord for available tools
            response = await self.overlord.chat(
                "What tools do you have available? List them briefly.",
                user_id="test_user",
                use_async=False,
                stream=False,
            )

            # Handle response
            if hasattr(response, "__aiter__"):
                response_text = ""
                async for chunk in response:
                    response_text += chunk
            else:
                response_text = response.content if hasattr(response, "content") else str(response)

            # Parse tools from response (simplified)
            # In practice, this would use MCP protocol to get tool list
            self.available_tools = self.parse_tools_from_response(response_text)

            return self.available_tools

        except Exception as e:
            print(f"  ⚠️ Could not discover tools: {e}")
            return []

    def parse_tools_from_response(self, response: str) -> List[str]:
        """Parse tool names from response text.

        Args:
            response: Response text containing tool information

        Returns:
            List of tool names
        """
        tools = []
        response_lower = response.lower()

        # Common MCP tools to look for
        known_tools = [
            "weather",
            "get_weather",
            "get_forecast",
            "memory",
            "store_memory",
            "recall_memory",
            "filesystem",
            "read_file",
            "write_file",
            "search",
            "web_search",
            "calculator",
            "calculate",
        ]

        for tool in known_tools:
            if tool in response_lower:
                tools.append(tool)

        return tools

    async def execute_tool(
        self, tool_name: str, params: Dict[str, Any], user_id: str = "test_user"
    ) -> Tuple[bool, str]:
        """Execute an MCP tool through natural language.

        Args:
            tool_name: Name of the tool to execute
            params: Parameters for the tool
            user_id: User ID for the request

        Returns:
            Tuple of (success, result)
        """
        try:
            # Build natural language request that triggers tool use
            if tool_name == "weather" or tool_name == "get_weather":
                location = params.get("location", "San Francisco")
                request = f"What's the weather in {location}?"
            elif tool_name == "memory" or tool_name == "store_memory":
                content = params.get("content", "test memory")
                request = f"Please remember this: {content}"
            elif tool_name == "filesystem" or tool_name == "read_file":
                path = params.get("path", "/tmp/test.txt")
                request = f"Read the file at {path}"
            else:
                # Generic tool request
                request = f"Use the {tool_name} tool with parameters: {json.dumps(params)}"

            # Execute through overlord
            response = await self.overlord.chat(
                request, user_id=user_id, use_async=False, stream=False
            )

            # Handle response
            if hasattr(response, "__aiter__"):
                response_text = ""
                async for chunk in response:
                    response_text += chunk
            else:
                response_text = response.content if hasattr(response, "content") else str(response)

            # Check if tool was executed (simplified check)
            success = tool_name in response_text.lower() or "error" not in response_text.lower()

            return success, response_text

        except Exception as e:
            return False, f"Tool execution error: {str(e)}"

    async def test_tool_discovery(self) -> Tuple[bool, List[str]]:
        """Test MCP tool discovery.

        Returns:
            Tuple of (success, discovered_tools)
        """
        try:
            tools = await self.discover_tools()
            success = len(tools) > 0
            return success, tools

        except Exception:
            return False, []

    async def test_tool_execution(self, tool_name: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Test execution of a specific tool.

        Args:
            tool_name: Tool to test
            params: Tool parameters

        Returns:
            Tuple of (success, result)
        """
        return await self.execute_tool(tool_name, params)

    async def test_multi_tool_workflow(
        self, workflow: List[Tuple[str, Dict]], user_id: str = "test_user"
    ) -> Tuple[bool, List[str]]:
        """Test a workflow using multiple tools.

        Args:
            workflow: List of (tool_name, params) tuples
            user_id: User ID for the request

        Returns:
            Tuple of (success, results)
        """
        results = []
        all_success = True

        for tool_name, params in workflow:
            success, result = await self.execute_tool(tool_name, params, user_id)
            results.append(result)
            if not success:
                all_success = False

            # Small delay between tools
            await asyncio.sleep(1)

        return all_success, results

    async def test_credential_handling(self, service: str = "weather") -> Tuple[bool, str]:
        """Test MCP credential handling.

        Args:
            service: Service requiring credentials

        Returns:
            Tuple of (success, details)
        """
        try:
            # Try to use a service that requires credentials
            if service == "weather":
                request = "What's the weather in Tokyo? (This requires API credentials)"
            else:
                request = f"Use the {service} service"

            response = await self.overlord.chat(
                request, user_id="test_user", use_async=False, stream=False
            )

            # Handle response
            if hasattr(response, "__aiter__"):
                response_text = ""
                async for chunk in response:
                    response_text += chunk
            else:
                response_text = response.content if hasattr(response, "content") else str(response)

            # Check if credentials were handled
            if "credential" in response_text.lower() or "api key" in response_text.lower():
                return True, "Credential handling detected"
            elif "error" in response_text.lower():
                return False, "Credential error"
            else:
                return True, "Request processed"

        except Exception as e:
            return False, f"Error: {str(e)}"

    async def cleanup(self):
        """Clean up formation and resources."""
        if self.formation:
            try:
                await self.formation.shutdown()
            except Exception:
                pass
        self.formation = None
        self.overlord = None
        self.available_tools = []

    def print_test_header(self, test_name: str, description: str):
        """Print standardized test header."""
        self.formatter.print_test_header(test_name, description)

    def print_test_result(
        self,
        test_name: str,
        success: bool,
        checks: List[str],
        transcript: List[Tuple[str, str]],
        duration: float,
    ):
        """Print standardized test result."""
        self.formatter.print_test_result(test_name, success, checks, transcript, duration)
