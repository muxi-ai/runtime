"""High-level MCP Prompt management."""

from typing import List, Dict, Any, TYPE_CHECKING
from .discovery import MCPPromptDiscovery
from ....datatypes.exceptions import MCPRequestError

if TYPE_CHECKING:
    from ..service import MCPService


class MCPPromptManager:
    """High-level prompt management for MCP servers."""

    def __init__(self, service: "MCPService"):
        """Initialize prompt manager.

        Args:
            service: MCPService instance for accessing transports
        """
        self.service = service
        self.discovery = MCPPromptDiscovery()

    async def get_prompts(self, server_id: str) -> List[Dict[str, Any]]:
        """Get all prompts from a specific MCP server.

        Args:
            server_id: ID of the MCP server to query

        Returns:
            List of prompt definitions

        Raises:
            MCPRequestError: If server not found or prompts query fails
        """
        transport = self.service.get_transport(server_id)
        if not transport:
            raise MCPRequestError(f"MCP server '{server_id}' not found or not connected")

        return await self.discovery.list_prompts(transport)

    async def get_prompt(
        self,
        server_id: str,
        name: str,
        arguments: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Get a specific prompt with optional argument substitution.

        Args:
            server_id: ID of the MCP server
            name: Name of the prompt to retrieve
            arguments: Optional arguments for template substitution

        Returns:
            Prompt content with messages

        Raises:
            MCPRequestError: If server not found or prompt retrieval fails
        """
        transport = self.service.get_transport(server_id)
        if not transport:
            raise MCPRequestError(f"MCP server '{server_id}' not found or not connected")

        return await self.discovery.get_prompt(transport, name, arguments)

    async def get_prompt_text(
        self,
        server_id: str,
        name: str,
        arguments: Dict[str, Any] = None
    ) -> str:
        """Get prompt content as formatted text.

        Args:
            server_id: ID of the MCP server
            name: Name of the prompt to retrieve
            arguments: Optional arguments for template substitution

        Returns:
            Combined text content from all prompt messages

        Raises:
            MCPRequestError: If server not found or prompt retrieval fails
        """
        prompt_content = await self.get_prompt(server_id, name, arguments)
        return self.discovery.extract_prompt_text(prompt_content)

    async def find_prompts_by_name(
        self,
        server_id: str,
        name_pattern: str
    ) -> List[Dict[str, Any]]:
        """Find prompts by name pattern.

        Args:
            server_id: ID of the MCP server
            name_pattern: Pattern to match in prompt names (case-insensitive)

        Returns:
            List of matching prompt definitions

        Raises:
            MCPRequestError: If server not found or prompts query fails
        """
        prompts = await self.get_prompts(server_id)
        pattern_lower = name_pattern.lower()

        matching_prompts = [
            prompt for prompt in prompts
            if pattern_lower in prompt.get("name", "").lower()
        ]

        return matching_prompts

    async def get_prompts_with_arguments(self, server_id: str) -> List[Dict[str, Any]]:
        """Get prompts that accept arguments.

        Args:
            server_id: ID of the MCP server

        Returns:
            List of prompt definitions that have arguments

        Raises:
            MCPRequestError: If server not found or prompts query fails
        """
        prompts = await self.get_prompts(server_id)

        parametric_prompts = [
            prompt for prompt in prompts
            if prompt.get("arguments")
        ]

        return parametric_prompts

    async def get_simple_prompts(self, server_id: str) -> List[Dict[str, Any]]:
        """Get prompts that don't require arguments.

        Args:
            server_id: ID of the MCP server

        Returns:
            List of prompt definitions without arguments

        Raises:
            MCPRequestError: If server not found or prompts query fails
        """
        prompts = await self.get_prompts(server_id)

        simple_prompts = [
            prompt for prompt in prompts
            if not prompt.get("arguments")
        ]

        return simple_prompts

    def validate_prompt_arguments(
        self,
        prompt: Dict[str, Any],
        provided_args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate and prepare arguments for a prompt.

        Args:
            prompt: Prompt definition with argument specifications
            provided_args: Arguments provided by user

        Returns:
            Validated and processed arguments

        Raises:
            MCPRequestError: If argument validation fails
        """
        prompt_args = prompt.get("arguments", [])
        validated_args = {}

        # Check required arguments
        for arg_spec in prompt_args:
            arg_name = arg_spec.get("name")
            is_required = arg_spec.get("required", False)

            if is_required and arg_name not in provided_args:
                raise MCPRequestError(f"Required argument '{arg_name}' missing for prompt '{prompt.get('name')}'")

            if arg_name in provided_args:
                validated_args[arg_name] = provided_args[arg_name]
            elif "default" in arg_spec:
                validated_args[arg_name] = arg_spec["default"]

        # Check for unexpected arguments
        expected_arg_names = {arg.get("name") for arg in prompt_args}
        for provided_arg in provided_args:
            if provided_arg not in expected_arg_names:
                raise MCPRequestError(f"Unexpected argument '{provided_arg}' for prompt '{prompt.get('name')}'")

        return validated_args

    async def execute_prompt_with_validation(
        self,
        server_id: str,
        name: str,
        arguments: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Execute a prompt with argument validation.

        Args:
            server_id: ID of the MCP server
            name: Name of the prompt to retrieve
            arguments: Arguments for template substitution

        Returns:
            Prompt content with validated arguments applied

        Raises:
            MCPRequestError: If validation fails or prompt retrieval fails
        """
        # First get the prompt definition to validate arguments
        prompts = await self.get_prompts(server_id)
        prompt_def = None

        for prompt in prompts:
            if prompt.get("name") == name:
                prompt_def = prompt
                break

        if not prompt_def:
            raise MCPRequestError(f"Prompt '{name}' not found on server '{server_id}'")

        # Validate arguments if provided
        validated_args = None
        if arguments:
            validated_args = self.validate_prompt_arguments(prompt_def, arguments)

        # Get the prompt with validated arguments
        return await self.get_prompt(server_id, name, validated_args)

    def get_prompt_summary(self, prompts: List[Dict[str, Any]]) -> str:
        """Generate a summary of available prompts.

        Args:
            prompts: List of prompt definitions

        Returns:
            Human-readable summary string
        """
        return self.discovery.format_prompt_summary(prompts)

    def get_prompt_details(self, prompt: Dict[str, Any]) -> str:
        """Get detailed information about a specific prompt.

        Args:
            prompt: Prompt definition

        Returns:
            Detailed prompt information string
        """
        name = prompt.get("name", "Unnamed")
        description = prompt.get("description", "No description")

        details_lines = [
            f"📝 Prompt: {name}",
            f"Description: {description}"
        ]

        # Add argument information
        arguments = prompt.get("arguments", [])
        if arguments:
            details_lines.append(f"\nArguments ({len(arguments)}):")

            arg_info = self.discovery.get_prompt_arguments_info(prompt)
            for arg in arg_info:
                arg_line = f"  • {arg['name']}: {arg['type']}"
                if arg['required']:
                    arg_line += " (required)"
                if 'default' in arg:
                    arg_line += f" (default: {arg['default']})"
                if arg['description']:
                    arg_line += f" - {arg['description']}"
                details_lines.append(arg_line)
        else:
            details_lines.append("\nNo arguments required")

        return "\n".join(details_lines)

    async def test_prompt_access(self, server_id: str) -> Dict[str, Any]:
        """Test prompt access capabilities for a server.

        Args:
            server_id: ID of the MCP server to test

        Returns:
            Test results with success/failure information
        """
        test_results = {
            "server_id": server_id,
            "list_prompts_success": False,
            "get_prompt_success": False,
            "prompt_count": 0,
            "simple_prompt_count": 0,
            "parametric_prompt_count": 0,
            "test_errors": []
        }

        try:
            # Test prompt listing
            prompts = await self.get_prompts(server_id)
            test_results["list_prompts_success"] = True
            test_results["prompt_count"] = len(prompts)

            # Count simple vs parametric prompts
            simple_prompts = [p for p in prompts if not p.get("arguments")]
            parametric_prompts = [p for p in prompts if p.get("arguments")]

            test_results["simple_prompt_count"] = len(simple_prompts)
            test_results["parametric_prompt_count"] = len(parametric_prompts)

            # Test getting a simple prompt if available
            if simple_prompts:
                try:
                    first_prompt = simple_prompts[0]
                    name = first_prompt.get("name")

                    if name:
                        content = await self.get_prompt(server_id, name)
                        test_results["get_prompt_success"] = True
                        test_results["sample_prompt_messages"] = len(content.get("messages", []))
                except Exception as e:
                    test_results["test_errors"].append(f"Prompt retrieval failed: {e}")

        except Exception as e:
            test_results["test_errors"].append(f"Prompt listing failed: {e}")

        return test_results
