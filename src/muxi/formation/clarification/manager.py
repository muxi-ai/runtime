"""
Clarification manager for tracking multi-turn clarification requests.

This module manages active clarification requests and coordinates the
clarification process across multiple conversation turns.
"""

import time
from typing import Dict, Optional, Any

from ...datatypes.clarification import (
    ClarificationError,
    ClarificationResult,
    ClarificationResultStatus,
    ClarificationStatus,
    RequestType,
    ClarificationRequest,
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
        provided_info: Optional[Dict[str, Any]] = None,
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
            #  Info - TODO: add observability

            # Cancel any existing clarification for this user
            await self._cancel_existing_clarification(user_id)

            # Create new clarification request
            request = ClarificationRequest(
                request_id=None,  # Will be auto-generated in __post_init__
                user_id=user_id,
                agent_id=agent_id,
                request_type=request_type,
                tool_name=tool_name,
                intent=intent,
                provided_info=provided_info or {},
                status=ClarificationStatus.CLARIFYING,
            )

            # Store the request
            self.active_requests[request.request_id] = request
            self._user_to_request[user_id] = request.request_id

            #  Info - TODO: add observability
            return request

        except Exception as e:
            #  Error - TODO: add observability
            raise ClarificationError(f"Failed to start clarification: {e}")

    async def process_user_response(
        self, request_id: str, user_response: str
    ) -> ClarificationResult:
        """
        Process user response with single LLM call for all decisions.

        Args:
            request_id: ID of the clarification request
            user_response: User's response text

        Returns:
            ClarificationResult with next steps
        """
        try:
            request = self.active_requests.get(request_id)
            if not request:
                return ClarificationResult(
                    status=ClarificationResultStatus.ERROR,
                    error_message="Clarification request not found",
                )

            if request.status != ClarificationStatus.CLARIFYING:
                return ClarificationResult(
                    status=ClarificationResultStatus.ERROR,
                    error_message="Clarification request is not active",
                )

            # Get LLM model from overlord - this is always available as it's required
            # The formation won't start without a text model configured
            text_config = self.overlord._capability_models.get('text')
            llm_model = await self.overlord.create_model(
                model=text_config.get('model'),
                temperature=0,
                max_tokens=300,
                api_key=text_config.get('api_key')
            )

            # Build prompt for single LLM decision
            import json

            prompt = f"""Process this clarification response and determine next steps.

Context:
- Original request: {request.intent}
- Tool being configured: {request.tool_name or 'N/A'}
- Information already collected: {json.dumps(request.provided_info, indent=2)}
- User just said: {user_response}

The user's original request was vague ("{request.intent}") and we asked for clarification.
Now they've provided: "{user_response}"

Analyze if this provides enough information to proceed. Be VERY practical and avoid over-clarification.

IMPORTANT RULES:
- If the user mentions a specific technology, language, or error type, that's ENOUGH to proceed
- For bug fixes: knowing it's "Python syntax error" is sufficient - we can help debug
- **If the user provides actual CODE, that's ALWAYS enough** - mark as complete immediately
- For projects: knowing it's "web scraper" or "API" is sufficient to start
- Only continue clarifying if you literally cannot take ANY helpful action

SPECIAL CASE - CODE PROVIDED:
If the response contains code (look for patterns like "for", "if", "def", "class", "print", etc. or multi-line structure with indentation), ALWAYS mark is_complete as true. The user has given you concrete code to work with.

Return JSON with:
1. extracted: Key information from the response (e.g., bug type, language, project type)
2. next_question: ONLY if absolutely impossible to help (usually null). This should be in the same language as the user's original request.
3. is_complete: true unless you literally cannot provide ANY assistance

Examples of COMPLETE clarifications:
- "Build it" → "A web scraper" = COMPLETE (can build basic scraper)
- "Fix the bug" → "Python syntax error" = COMPLETE (can help with Python syntax)
- "Help with database" → "PostgreSQL" = COMPLETE (can help with PostgreSQL)

Return ONLY valid JSON, no explanation."""

            # Get LLM response
            messages = [{"role": "user", "content": prompt}]
            response = await llm_model.chat(messages, max_tokens=300, temperature=0)
            content = response.content if hasattr(response, 'content') else str(response)

            # Parse JSON response
            json_str = content[content.index('{'):content.rindex('}')+1] if '{' in content else '{}'
            result = json.loads(json_str)

            # Update request with extracted info
            extracted = result.get("extracted", {})
            request.provided_info.update(extracted)
            request.current_step += 1
            request.updated_at = time.time()

            # Check completion status
            if result.get("is_complete", False):
                request.status = ClarificationStatus.READY
                complete_params = await self._compile_complete_parameters(request)
                return ClarificationResult(
                    status=ClarificationResultStatus.COMPLETE,
                    complete_params=complete_params,
                    confidence=0.9,
                    extracted_info=extracted,
                )

            # Continue with next question
            next_question = result.get("next_question")
            if next_question:
                return ClarificationResult(
                    status=ClarificationResultStatus.CONTINUE,
                    next_question=next_question,
                    confidence=0.7,
                    extracted_info=extracted,
                )

            # No next question but not complete - error state
            request.status = ClarificationStatus.FAILED
            return ClarificationResult(
                status=ClarificationResultStatus.ERROR,
                error_message="Unable to determine next steps",
                extracted_info=extracted,
            )

        except json.JSONDecodeError:
            # LLM didn't return valid JSON, store raw response
            request.provided_info["response"] = user_response
            request.current_step += 1
            request.updated_at = time.time()
            return ClarificationResult(
                status=ClarificationResultStatus.CONTINUE,
                next_question="Could you provide more details?",
                extracted_info={"response": user_response},
            )
        except Exception as e:
            return ClarificationResult(
                status=ClarificationResultStatus.ERROR,
                error_message=f"Failed to process response: {e}",
            )

    async def complete_clarification(self, request_id: str) -> Dict[str, Any]:
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

            #  Info - TODO: add observability
            return complete_params

        except Exception as e:
            #  Error - TODO: add observability
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
                #  Info - TODO: add observability
                return True
            return False

        except Exception as e:
            #  Error - TODO: add observability
            _ = e  # remove this after implementing observability
            return False

    # Private helper methods

    async def _cancel_existing_clarification(self, user_id: str) -> None:
        """Cancel any existing clarification for the user"""
        existing_request = self.get_active_clarification(user_id)
        if existing_request:
            await self.cancel_clarification(existing_request.request_id)

    async def _extract_information_from_response(
        self, user_response: str, request: ClarificationRequest
    ) -> Dict[str, Any]:
        """DEPRECATED - Functionality moved to process_user_response."""
        return {"response": user_response}

    async def _has_sufficient_information(self, request: ClarificationRequest) -> bool:
        """DEPRECATED - Functionality moved to process_user_response."""
        return len(request.provided_info) > 0

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
        """DEPRECATED - Functionality moved to process_user_response."""
        return None

    async def _compile_complete_parameters(self, request: ClarificationRequest) -> Dict[str, Any]:
        """Compile all collected information into final parameter set"""
        complete_params = request.provided_info.copy()

        # Add any context enrichment
        if self.overlord:
            user_context = await self.overlord.get_user_context(request.user_id)
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
            "book_restaurant": {"required": ["location", "date", "time", "party_size"]},
            "book_flight": {
                "required": ["departure", "destination", "departure_date", "passengers"]
            },
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
