"""
Clarification manager for tracking multi-turn clarification requests.

This module manages active clarification requests and coordinates the
clarification process across multiple conversation turns.
"""


import time
from typing import Dict, Optional, Any

from .types import (
    ClarificationRequest,
    ClarificationResult,
    ClarificationStatus,
    RequestType,
    ClarificationError
)


class ClarificationManager:
    """Manages active clarification requests"""

    def __init__(self, overlord):
        """
        Initialize the clarification manager

        Args:
            overlord: Reference to the overlord for coordination
        """
        self.overlord = overlord
        self.active_requests: Dict[str, ClarificationRequest] = {}
        self._user_to_request: Dict[str, str] = {}  # user_id -> request_id mapping

    async def start_clarification(
        self,
        user_id: str,
        agent_id: str,
        request_type: RequestType,
        intent: str,
        tool_name: Optional[str] = None,
        provided_info: Optional[Dict[str, Any]] = None
    ) -> ClarificationRequest:
        """
        Start a new clarification process

        Args:
            user_id: ID of the user requesting clarification
            agent_id: ID of the agent handling the request
            request_type: Type of clarification (tool_call, reasoning, mixed)
            intent: User's primary intent
            tool_name: Name of tool if this is a tool clarification
            provided_info: Information already provided by user

        Returns:
            ClarificationRequest object tracking the clarification
        """
        try:
            #  Info - add observability event

            # Cancel any existing clarification for this user
            await self._cancel_existing_clarification(user_id)

            # Create new clarification request
            request = ClarificationRequest(
                request_id="",  # Will be auto-generated in __post_init__
                user_id=user_id,
                agent_id=agent_id,
                request_type=request_type,
                tool_name=tool_name,
                intent=intent,
                provided_info=provided_info or {},
                status=ClarificationStatus.CLARIFYING
            )

            # Store the request
            self.active_requests[request.request_id] = request
            self._user_to_request[user_id] = request.request_id

            #  Info - add observability event
            return request

        except Exception as e:
            #  Error - add observability event
            raise ClarificationError(f"Failed to start clarification: {e}")

    async def process_user_response(
        self,
        request_id: str,
        user_response: str
    ) -> ClarificationResult:
        """
        Process user's response to clarification question

        Args:
            request_id: ID of the clarification request
            user_response: User's response text

        Returns:
            ClarificationResult with next steps
        """
        try:
            #  Info - add observability event

            request = self.active_requests.get(request_id)
            if not request:
                return ClarificationResult(
                    status="error",
                    error_message="Clarification request not found"
                )

            if request.status != ClarificationStatus.CLARIFYING:
                return ClarificationResult(
                    status="error",
                    error_message="Clarification request is not active"
                )

            # Extract information from user response
            extracted_info = await self._extract_information_from_response(
                user_response, request
            )

            # Update request with extracted information
            request.provided_info.update(extracted_info)
            request.current_step += 1
            request.updated_at = time.time()

            # Check if we have enough information to proceed
            if await self._has_sufficient_information(request):
                # Complete the clarification
                request.status = ClarificationStatus.READY
                complete_params = await self._compile_complete_parameters(request)

                return ClarificationResult(
                    status="complete",
                    complete_params=complete_params,
                    confidence=0.9,
                    extracted_info=extracted_info
                )

            # Need more information - generate next question
            next_question = await self._generate_next_question(request)

            if next_question:
                return ClarificationResult(
                    status="continue",
                    next_question=next_question,
                    confidence=0.7,
                    extracted_info=extracted_info
                )
            else:
                # No more questions but still missing info - fail gracefully
                request.status = ClarificationStatus.FAILED
                return ClarificationResult(
                    status="error",
                    error_message="Unable to collect all required information",
                    extracted_info=extracted_info
                )

        except Exception as e:
            #  Error - add observability event
            return ClarificationResult(
                status="error",
                error_message=f"Failed to process response: {e}"
            )

    async def complete_clarification(
        self,
        request_id: str
    ) -> Dict[str, Any]:
        """
        Complete clarification and return full information set

        Args:
            request_id: ID of the clarification request

        Returns:
            Dictionary containing all collected information
        """
        try:
            request = self.active_requests.get(request_id)
            if not request:
                raise ClarificationError("Clarification request not found")

            complete_params = await self._compile_complete_parameters(request)

            # Clean up the request
            self._cleanup_request(request_id)

            #  Info - add observability event
            return complete_params

        except Exception as e:
            #  Error - add observability event
            raise ClarificationError(f"Failed to complete clarification: {e}")

    def get_active_clarification(self, user_id: str) -> Optional[ClarificationRequest]:
        """
        Get active clarification request for a user

        Args:
            user_id: ID of the user

        Returns:
            ClarificationRequest if active, None otherwise
        """
        request_id = self._user_to_request.get(user_id)
        if request_id:
            return self.active_requests.get(request_id)
        return None

    def has_active_clarification(self, user_id: str) -> bool:
        """
        Check if user has an active clarification request

        Args:
            user_id: ID of the user

        Returns:
            True if user has active clarification, False otherwise
        """
        request = self.get_active_clarification(user_id)
        return request is not None and request.status == ClarificationStatus.CLARIFYING

    async def cancel_clarification(self, request_id: str) -> bool:
        """
        Cancel an active clarification request

        Args:
            request_id: ID of the clarification request

        Returns:
            True if cancelled successfully, False otherwise
        """
        try:
            request = self.active_requests.get(request_id)
            if request:
                request.status = ClarificationStatus.CANCELLED
                self._cleanup_request(request_id)
                #  Info - add observability event
                return True
            return False

        except Exception as e:
            #  Error - add observability event
            _ = e  # remove this after implementing observability
            return False

    # Private helper methods

    async def _cancel_existing_clarification(self, user_id: str) -> None:
        """Cancel any existing clarification for the user"""
        existing_request = self.get_active_clarification(user_id)
        if existing_request:
            await self.cancel_clarification(existing_request.request_id)

    async def _extract_information_from_response(
        self,
        user_response: str,
        request: ClarificationRequest
    ) -> Dict[str, Any]:
        """Extract structured information from user's response"""
        extracted = {}

        # Get current question being answered
        if request.current_step < len(request.clarification_plan):
            current_question = request.clarification_plan[request.current_step]

            # Simple extraction based on parameter type
            param_name = current_question.parameter_name
            param_type = current_question.parameter_type

            # Basic type conversion
            if param_type == "integer":
                try:
                    # Extract numbers from response
                    import re
                    numbers = re.findall(r'\d+', user_response)
                    if numbers:
                        extracted[param_name] = int(numbers[0])
                except ValueError:
                    pass
            elif param_type == "boolean":
                response_lower = user_response.lower()
                if any(word in response_lower for word in ["yes", "true", "confirm"]):
                    extracted[param_name] = True
                elif any(word in response_lower for word in ["no", "false", "cancel"]):
                    extracted[param_name] = False
            else:
                # String or other types - use response directly
                extracted[param_name] = user_response.strip()

        return extracted

    async def _has_sufficient_information(self, request: ClarificationRequest) -> bool:
        """Check if request has sufficient information to proceed"""
        if request.request_type == RequestType.TOOL_CALL:
            # For tool calls, check if all required parameters are provided
            return await self._has_required_tool_parameters(request)
        else:
            # For reasoning, check if we have enough context
            return await self._has_sufficient_reasoning_context(request)

    async def _has_required_tool_parameters(self, request: ClarificationRequest) -> bool:
        """Check if all required tool parameters are available"""
        if not request.tool_name:
            return False

        # Get tool schema to check required parameters
        # In production, this would come from MCP service
        tool_schema = await self._get_tool_schema(request.tool_name)
        required_params = tool_schema.get("required", [])

        # Check if all required parameters are provided
        for param in required_params:
            if param not in request.provided_info:
                return False

        return True

    async def _has_sufficient_reasoning_context(self, request: ClarificationRequest) -> bool:
        """Check if we have sufficient context for reasoning"""
        # Simple heuristic - if we've asked enough questions or have key info
        if request.current_step >= 3:  # Asked enough questions
            return True

        # Check for key reasoning context
        key_contexts = ["background", "goals", "preferences", "constraints"]
        provided_contexts = sum(1 for ctx in key_contexts if ctx in request.provided_info)

        return provided_contexts >= 2  # Have at least 2 key contexts

    async def _generate_next_question(self, request: ClarificationRequest) -> Optional[str]:
        """Generate the next clarification question"""
        if request.current_step >= len(request.clarification_plan):
            # No more planned questions
            return None

        next_question = request.clarification_plan[request.current_step]
        return next_question.question_text

    async def _compile_complete_parameters(self, request: ClarificationRequest) -> Dict[str, Any]:
        """Compile all collected information into final parameter set"""
        complete_params = request.provided_info.copy()

        # Add any context enrichment
        if self.overlord:
            user_context = await self.overlord.get_user_context_memory(request.user_id)
            if user_context:
                # Fill any remaining gaps from context
                for key, value in user_context.items():
                    if key not in complete_params:
                        complete_params[key] = value

        return complete_params

    async def _get_tool_schema(self, tool_name: str) -> Dict[str, Any]:
        """Get tool schema - placeholder for MCP integration"""
        # Mock schemas for development
        schemas = {
            "book_restaurant": {
                "required": ["location", "date", "time", "party_size"]
            },
            "book_flight": {
                "required": ["departure", "destination", "departure_date", "passengers"]
            }
        }
        return schemas.get(tool_name, {"required": []})

    def _cleanup_request(self, request_id: str) -> None:
        """Clean up completed or cancelled request"""
        request = self.active_requests.get(request_id)
        if request:
            # Remove from user mapping
            if request.user_id in self._user_to_request:
                del self._user_to_request[request.user_id]

            # Remove from active requests
            if request_id in self.active_requests:
                del self.active_requests[request_id]
