"""
Enhanced tool processor with clarification support.

This module provides enhanced tool call processing that integrates with the
intelligent clarification system to handle incomplete or unclear tool calls.
"""


from typing import Dict, List, Any, Optional, Tuple

from ...services.mcp.parser import ToolParser, ToolCall
from .datatypes import ToolInformationAnalysis


class EnhancedToolProcessor:
    """
    Enhanced tool processor that integrates clarification with tool execution.

    This processor extends the standard tool parsing with:
    - Parameter validation and enrichment
    - Clarification integration for incomplete tools
    - Enhanced error handling and recovery
    - Context-aware parameter filling
    """

    def __init__(self, agent, clarification_analyzer, clarification_enricher):
        """
        Initialize the enhanced tool processor.

        Args:
            agent: The agent instance for tool execution
            clarification_analyzer: Analyzer for detecting missing information
            clarification_enricher: Enricher for filling parameters from context
        """
        self.agent = agent
        self.clarification_analyzer = clarification_analyzer
        self.clarification_enricher = clarification_enricher

    async def process_tool_calls_with_clarification(
        self,
        text: str,
        user_id: Any = None,
        user_context: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, List[ToolCall], Optional[str]]:
        """
        Process tool calls from text with clarification support.

        This method:
        1. Parses tool calls from the text
        2. Validates and enriches parameters
        3. Identifies missing information
        4. Returns clarification questions if needed
        5. Executes tools when ready

        Args:
            text: The text containing potential tool calls
            user_id: User ID for context enrichment
            user_context: User context for parameter enrichment

        Returns:
            Tuple of (processed_text, tool_calls, clarification_question)
            - processed_text: Text with tool calls processed
            - tool_calls: List of processed tool calls
            - clarification_question: Question if clarification needed, None otherwise
        """
        try:
            # Parse tool calls using existing parser
            cleaned_text, raw_tool_calls = ToolParser.parse(text)

            if not raw_tool_calls:
                # No tool calls found, return original text
                return text, [], None

            # Process each tool call for validation and enrichment
            processed_calls = []
            clarification_needed = False
            clarification_question = None

            for tool_call in raw_tool_calls:
                # Validate and enrich the tool call
                validation_result = await self._validate_and_enrich_tool_call(
                    tool_call, user_context or {}
                )

                if validation_result["needs_clarification"]:
                    clarification_needed = True
                    clarification_question = validation_result["clarification_question"]
                    # Don't process remaining tool calls if clarification is needed
                    break
                else:
                    # Tool call is ready - execute it
                    enhanced_call = validation_result["enhanced_call"]
                    try:
                        result = await self.agent.invoke_tool(
                            tool_name=enhanced_call.tool_name,
                            parameters=enhanced_call.parameters
                        )
                        enhanced_call.set_result(result)
                        processed_calls.append(enhanced_call)
                    except Exception as e:
                        #  Error - TODO: add observability
                        # Set error result
                        enhanced_call.set_result({
                            "error": str(e),
                            "status": "failed"
                        })
                        processed_calls.append(enhanced_call)

            if clarification_needed:
                # Return original text with clarification question
                return text, raw_tool_calls, clarification_question
            else:
                # Replace tool calls with results in the text
                final_text = ToolParser.replace_tool_calls_with_results(text, processed_calls)
                return final_text, processed_calls, None

        except Exception as e:
            #  Error - TODO: add observability
            _ = e  # remove this after implementing observability
            # Fall back to original text without processing
            return text, [], None

    async def _validate_and_enrich_tool_call(
        self,
        tool_call: ToolCall,
        user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate and enrich a single tool call.

        Args:
            tool_call: The tool call to validate and enrich
            user_context: User context for parameter enrichment

        Returns:
            Dict with validation results:
            - needs_clarification: bool
            - clarification_question: str or None
            - enhanced_call: ToolCall or None
        """
        try:
            # Get available tools from MCP service
            available_tools = []
            if self.agent._mcp_service:
                try:
                    available_tools = await self.agent._mcp_service.list_available_tools()
                except Exception as e:
                    #  Debug - TODO: add observability
                    _ = e  # remove this after implementing observability

                # Analyze the tool call for missing information
                analysis = await self.clarification_analyzer.analyze_tool_call(
                    tool_name=tool_call.tool_name,
                    provided_params=tool_call.parameters,
                    available_tools=available_tools,
                    user_context=user_context
                )

            # If analysis shows we can proceed, enrich parameters
            if analysis.can_proceed:
                # Enrich parameters using user context
                enriched_params = await self.clarification_enricher.enrich_parameters(
                    tool_name=tool_call.tool_name,
                    provided_params=tool_call.parameters,
                    user_context=user_context
                )

                # Create enhanced tool call with enriched parameters
                enhanced_call = ToolCall(
                    tool_name=tool_call.tool_name,
                    parameters=enriched_params,
                    full_text=tool_call.full_text,
                    start_pos=tool_call.start_pos,
                    end_pos=tool_call.end_pos
                )

                return {
                    "needs_clarification": False,
                    "clarification_question": None,
                    "enhanced_call": enhanced_call
                }
            else:
                # Missing information - generate clarification question
                clarification_question = self._generate_tool_clarification_question(
                    analysis, tool_call.tool_name
                )

                return {
                    "needs_clarification": True,
                    "clarification_question": clarification_question,
                    "enhanced_call": None
                }

        except Exception as e:
            #  Error - TODO: add observability
            _ = e  # remove this after implementing observability
            # On error, assume tool call is valid as-is
            return {
                "needs_clarification": False,
                "clarification_question": None,
                "enhanced_call": tool_call
            }

    def _generate_tool_clarification_question(
        self,
        analysis: ToolInformationAnalysis,
        tool_name: str
    ) -> str:
        """
        Generate a clarification question for a tool call.

        Args:
            analysis: The information analysis result
            tool_name: Name of the tool needing clarification

        Returns:
            A natural language clarification question
        """
        if not analysis.missing_info:
            return f"I need more information to use the {tool_name} tool properly."

        missing_params = analysis.missing_info

        if len(missing_params) == 1:
            param = missing_params[0]
            return f"To use the {tool_name} tool, I need to know: {param}. Can you provide this?"
        else:
            param_list = ", ".join(missing_params[:-1]) + f", and {missing_params[-1]}"
            return f"To use the {tool_name} tool, I need: {param_list}. Can you provide these?"

    async def validate_tool_response(
        self,
        tool_call: ToolCall,
        response: Dict[str, Any],
        user_id: Any = None
    ) -> Optional[str]:
        """
        Validate a tool response and potentially ask for clarification.

        This method checks if a tool response is satisfactory or if additional
        clarification is needed from the user.

        Args:
            tool_call: The original tool call
            response: The response from the tool
            user_id: User ID for clarification tracking

        Returns:
            A clarification question if needed, None if response is satisfactory
        """
        try:
            # Check if the response indicates an error that requires clarification
            if "error" in response:
                error_msg = response["error"]

                # Common errors that might need clarification
                if any(keyword in error_msg.lower() for keyword in [
                    "invalid", "missing", "required", "not found", "ambiguous"
                ]):
                    return (
                        f"The {tool_call.tool_name} tool encountered an issue: {error_msg}. "
                        "Could you provide more specific information?"
                    )

            # Check if the response suggests incomplete information
            if "partial" in str(response).lower() or "incomplete" in str(response).lower():
                return (
                    f"I got a partial response from {tool_call.tool_name}. "
                    "Would you like me to get more detailed information?"
                )

            # Response seems satisfactory
            return None

        except Exception as e:
            #  Error - TODO: add observability
            _ = e  # remove this after implementing observability
            return None

    async def handle_clarified_tool_execution(
        self,
        original_tool_call: ToolCall,
        clarified_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a tool call with clarified parameters.

        Args:
            original_tool_call: The original tool call that needed clarification
            clarified_params: The parameters obtained through clarification

        Returns:
            The result of executing the tool with clarified parameters
        """
        try:
            # Merge original parameters with clarified ones
            final_params = {**original_tool_call.parameters, **clarified_params}

            # Execute the tool with complete parameters
            result = await self.agent.invoke_tool(
                tool_name=original_tool_call.tool_name,
                parameters=final_params
            )

            # Update the original tool call with results
            original_tool_call.parameters = final_params
            original_tool_call.set_result(result)

            return result

        except Exception as e:
            #  Error - TODO: add observability
            error_result = {
                "error": str(e),
                "status": "failed"
            }
            original_tool_call.set_result(error_result)
            return error_result
