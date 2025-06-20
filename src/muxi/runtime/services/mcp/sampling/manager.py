"""High-level MCP Sampling management."""

from typing import List, Dict, Any, TYPE_CHECKING
from .client import MCPSamplingClient
from ....datatypes.exceptions import MCPRequestError

if TYPE_CHECKING:
    from ..service import MCPService


class MCPSamplingManager:
    """High-level sampling management for MCP servers."""

    def __init__(self, service: "MCPService"):
        """Initialize sampling manager.

        Args:
            service: MCPService instance for accessing transports
        """
        self.service = service
        self.client = MCPSamplingClient()

    async def create_message(
        self,
        server_id: str,
        messages: List[Dict[str, Any]],
        **kwargs
    ) -> Dict[str, Any]:
        """Create a message using MCP server's sampling capability.

        Args:
            server_id: ID of the MCP server
            messages: List of conversation messages
            **kwargs: Additional parameters for message creation

        Returns:
            Generated message response

        Raises:
            MCPRequestError: If server not found or message creation fails
        """
        transport = self.service.get_transport(server_id)
        if not transport:
            raise MCPRequestError(f"MCP server '{server_id}' not found or not connected")

        return await self.client.create_message(transport, messages, **kwargs)

    async def create_simple_message(
        self,
        server_id: str,
        user_message: str,
        system_prompt: str = None,
        temperature: float = None,
        max_tokens: int = None
    ) -> str:
        """Create a simple message from user text.

        Args:
            server_id: ID of the MCP server
            user_message: User's message text
            system_prompt: Optional system prompt
            temperature: Optional temperature for generation
            max_tokens: Optional maximum tokens

        Returns:
            Generated response text

        Raises:
            MCPRequestError: If server not found or message creation fails
        """
        # Prepare messages
        messages = [{"role": "user", "content": user_message}]

        # Create message with parameters
        result = await self.create_message(
            server_id=server_id,
            messages=messages,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens
        )

        # Extract text content
        return self.client.extract_text_content(result)

    async def continue_conversation(
        self,
        server_id: str,
        conversation_history: List[str],
        new_message: str,
        system_prompt: str = None,
        **kwargs
    ) -> str:
        """Continue an existing conversation.

        Args:
            server_id: ID of the MCP server
            conversation_history: Previous conversation messages
            new_message: New user message to add
            system_prompt: Optional system prompt
            **kwargs: Additional parameters for message creation

        Returns:
            Generated response text

        Raises:
            MCPRequestError: If server not found or message creation fails
        """
        # Prepare conversation messages
        messages = self.client.prepare_conversation_messages(conversation_history)

        # Add new user message
        messages.append({"role": "user", "content": new_message})

        # Create response
        result = await self.create_message(
            server_id=server_id,
            messages=messages,
            system_prompt=system_prompt,
            **kwargs
        )

        # Extract text content
        return self.client.extract_text_content(result)

    async def create_with_model_preferences(
        self,
        server_id: str,
        messages: List[Dict[str, Any]],
        cost_priority: float = None,
        speed_priority: float = None,
        intelligence_priority: float = None,
        model_hints: List[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Create message with specific model preferences.

        Args:
            server_id: ID of the MCP server
            messages: List of conversation messages
            cost_priority: Priority for cost optimization (0.0-1.0)
            speed_priority: Priority for speed optimization (0.0-1.0)
            intelligence_priority: Priority for intelligence (0.0-1.0)
            model_hints: Optional model hints or names
            **kwargs: Additional parameters for message creation

        Returns:
            Generated message response with preference-optimized model

        Raises:
            MCPRequestError: If server not found or message creation fails
        """
        # Create model preferences
        model_preferences = self.client.create_model_preferences(
            hints=model_hints,
            cost_priority=cost_priority,
            speed_priority=speed_priority,
            intelligence_priority=intelligence_priority
        )

        # Create message with preferences
        return await self.create_message(
            server_id=server_id,
            messages=messages,
            model_preferences=model_preferences,
            **kwargs
        )

    async def batch_create_messages(
        self,
        server_id: str,
        message_batches: List[List[Dict[str, Any]]],
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Create multiple messages in batch.

        Args:
            server_id: ID of the MCP server
            message_batches: List of message lists to process
            **kwargs: Additional parameters for message creation

        Returns:
            List of generated message responses

        Raises:
            MCPRequestError: If server not found or any message creation fails
        """
        results = []

        for messages in message_batches:
            try:
                result = await self.create_message(
                    server_id=server_id,
                    messages=messages,
                    **kwargs
                )
                results.append(result)
            except Exception as e:
                # Add error result to maintain batch order
                results.append({
                    "error": str(e),
                    "success": False
                })

        return results

    async def create_with_context_strategy(
        self,
        server_id: str,
        messages: List[Dict[str, Any]],
        include_context: str = "thisServer",
        **kwargs
    ) -> Dict[str, Any]:
        """Create message with specific context inclusion strategy.

        Args:
            server_id: ID of the MCP server
            messages: List of conversation messages
            include_context: Context strategy ("thisServer", "allServers", "none")
            **kwargs: Additional parameters for message creation

        Returns:
            Generated message response with context strategy applied

        Raises:
            MCPRequestError: If server not found or message creation fails
        """
        return await self.create_message(
            server_id=server_id,
            messages=messages,
            include_context=include_context,
            **kwargs
        )

    def format_conversation_for_sampling(
        self,
        conversation: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """Format conversation for sampling API.

        Args:
            conversation: List of conversation turns with role and content

        Returns:
            Formatted message list for sampling
        """
        messages = []

        for turn in conversation:
            role = turn.get("role", "user")
            content = turn.get("content", "")

            message = {
                "role": role,
                "content": content
            }

            messages.append(message)

        return messages

    async def test_sampling_capability(self, server_id: str) -> Dict[str, Any]:
        """Test sampling capability for a server.

        Args:
            server_id: ID of the MCP server to test

        Returns:
            Test results with success/failure information
        """
        test_results = {
            "server_id": server_id,
            "sampling_success": False,
            "response_length": 0,
            "model_used": None,
            "stop_reason": None,
            "test_errors": []
        }

        try:
            # Test simple message creation
            test_messages = [{"role": "user", "content": "Hello, can you respond with a simple greeting?"}]

            result = await self.create_message(
                server_id=server_id,
                messages=test_messages,
                max_tokens=50,
                temperature=0.7
            )

            test_results["sampling_success"] = True
            test_results["response_length"] = len(self.client.extract_text_content(result))
            test_results["model_used"] = result.get("model")
            test_results["stop_reason"] = result.get("stopReason")

            # Test usage information if available
            if "usage" in result:
                test_results["input_tokens"] = result["usage"].get("inputTokens")
                test_results["output_tokens"] = result["usage"].get("outputTokens")

        except Exception as e:
            test_results["test_errors"].append(f"Sampling test failed: {e}")

        return test_results

    def get_sampling_summary(self, results: List[Dict[str, Any]]) -> str:
        """Generate a summary of sampling results.

        Args:
            results: List of sampling results

        Returns:
            Human-readable summary string
        """
        if not results:
            return "No sampling results available"

        successful_results = [r for r in results if r.get("success", True) and "error" not in r]
        error_results = [r for r in results if "error" in r]

        summary_lines = [
            f"🤖 Sampling Results ({len(results)} total):",
            f"  ✅ Successful: {len(successful_results)}",
            f"  ❌ Failed: {len(error_results)}"
        ]

        if successful_results:
            # Analyze successful results
            models_used = set()
            total_length = 0

            for result in successful_results:
                if "model" in result:
                    models_used.add(result["model"])

                content = self.client.extract_text_content(result)
                total_length += len(content)

            if models_used:
                summary_lines.append(f"  🔧 Models used: {', '.join(models_used)}")

            if total_length > 0:
                avg_length = total_length / len(successful_results)
                summary_lines.append(f"  📏 Average response length: {avg_length:.0f} characters")

        if error_results:
            summary_lines.append("\nErrors:")
            for i, error_result in enumerate(error_results[:3]):  # Show first 3 errors
                error_msg = error_result.get("error", "Unknown error")
                summary_lines.append(f"  {i+1}. {error_msg}")

            if len(error_results) > 3:
                summary_lines.append(f"  ... and {len(error_results) - 3} more errors")

        return "\n".join(summary_lines)
