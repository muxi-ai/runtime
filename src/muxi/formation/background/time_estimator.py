"""
Time estimation for async request processing.

This module estimates processing time using request analysis to help
determine if requests should be processed asynchronously.
"""

from typing import Optional, Dict

from ...services import observability


class TimeEstimator:
    """Estimates processing time using request analysis."""

    def __init__(self, analyzer):
        """
        Initialize time estimator.

        Args:
            analyzer: RequestAnalyzer instance for complexity assessment
        """
        self.analyzer = analyzer

    async def estimate_processing_time(
        self, request: str, context: Optional[Dict] = None
    ) -> Optional[float]:
        """
        Estimate processing time in seconds.

        Uses the existing RequestAnalyzer to assess complexity and
        calculate estimated processing time based on various factors.

        Args:
            request: Request text to analyze
            context: Optional context for the request

        Returns:
            Estimated processing time in seconds, or None if estimation fails
        """
        try:
            # Leverage existing RequestAnalyzer for complexity assessment
            analysis = await self.analyzer.analyze_request(request, context)

            # Base time for any request (10 seconds)
            base_time = 10.0

            # Complexity multiplier based on analysis score (1-10 scale)
            complexity_multiplier = max(1.0, analysis.complexity_score / 5.0)

            # Capability multiplier - more capabilities = more time
            required_capabilities = getattr(analysis, "required_capabilities", [])
            capability_multiplier = max(1.0, len(required_capabilities))

            # Decomposition multiplier - complex tasks requiring breakdown
            decomposition_multiplier = (
                2.0 if getattr(analysis, "requires_decomposition", False) else 1.0
            )

            # Multi-agent multiplier - coordination overhead
            multi_agent_multiplier = (
                1.5 if getattr(analysis, "requires_multi_agent", False) else 1.0
            )

            # Calculate estimated time
            estimated_seconds = (
                base_time
                * complexity_multiplier
                * capability_multiplier
                * decomposition_multiplier
                * multi_agent_multiplier
            )

            # Cap at 1 hour maximum
            estimated_seconds = min(estimated_seconds, 3600)

            observability.observe(
                event_type=observability.SystemEvents.PERFORMANCE_DURATION_RECORDED,
                level=observability.EventLevel.DEBUG,
                data={
                    "estimated_seconds": round(estimated_seconds, 1),
                    "complexity_score": analysis.complexity_score,
                    "capabilities_count": len(required_capabilities),
                    "requires_decomposition": getattr(analysis, 'requires_decomposition', False),
                    "requires_multi_agent": getattr(analysis, 'requires_multi_agent', False),
                },
                description=(
                    f"Time estimation completed: {estimated_seconds:.1f}s "
                    f"(complexity: {analysis.complexity_score}, "
                    f"capabilities: {len(required_capabilities)})"
                ),
            )

            return estimated_seconds

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.VALIDATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "time_estimation",
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                description=f"Time estimation failed: {type(e).__name__} - {str(e)}",
            )
            return None

    async def estimate_with_historical_data(
        self, request: str, context: Optional[Dict] = None, request_history=None
    ) -> Optional[float]:
        """
        Estimate processing time including historical data.

        Args:
            request: Request text to analyze
            context: Optional context for the request
            request_history: RequestHistory instance for historical patterns

        Returns:
            Estimated processing time in seconds with historical adjustment
        """
        # Get base estimation
        base_estimate = await self.estimate_processing_time(request, context)
        if base_estimate is None:
            return None

        # If no history available, return base estimate
        if request_history is None:
            return base_estimate

        try:
            # Try to get historical average for similar request patterns
            request_type = await self._classify_request_type(request)
            historical_average = await request_history.get_average_time_for_pattern(request_type)

            if historical_average is not None:
                # Blend base estimate with historical data (70% historical, 30% analysis)
                adjusted_estimate = 0.7 * historical_average + 0.3 * base_estimate

                observability.observe(
                    event_type=observability.SystemEvents.PERFORMANCE_DURATION_RECORDED,
                    level=observability.EventLevel.DEBUG,
                    data={
                        "adjusted_seconds": round(adjusted_estimate, 1),
                        "base_estimate": round(base_estimate, 1),
                        "historical_average": round(historical_average, 1),
                        "request_type": request_type,
                    },
                    description=(
                        f"Adjusted time estimate: {adjusted_estimate:.1f}s "
                        f"(70% historical: {historical_average:.1f}s, "
                        f"30% analysis: {base_estimate:.1f}s)"
                    ),
                )

                return adjusted_estimate
            else:
                return base_estimate

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.VALIDATION_FAILED,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "historical_time_estimation",
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                description=(
                    f"Historical time estimation failed "
                    f"({type(e).__name__}: {str(e)}), "
                    f"falling back to base estimate"
                ),
            )
            return base_estimate

    async def _classify_request_type(self, request: str) -> str:
        """
        Classify request into a type for historical pattern matching.

        Args:
            request: Request text to classify

        Returns:
            Request type string for pattern matching
        """
        request_lower = request.lower()

        # Simple keyword-based classification
        if any(word in request_lower for word in ["analyze", "analysis", "report"]):
            return "analysis"
        elif any(word in request_lower for word in ["create", "generate", "build"]):
            return "creation"
        elif any(word in request_lower for word in ["search", "find", "lookup"]):
            return "search"
        elif any(word in request_lower for word in ["summarize", "summary"]):
            return "summarization"
        elif any(word in request_lower for word in ["explain", "describe"]):
            return "explanation"
        else:
            return "general"

    def should_use_async(
        self, estimated_time: Optional[float], threshold_seconds: float = 30.0
    ) -> bool:
        """
        Determine if a request should be processed asynchronously.

        Args:
            estimated_time: Estimated processing time in seconds
            threshold_seconds: Threshold above which to use async processing

        Returns:
            True if request should be processed asynchronously
        """
        if estimated_time is None:
            # If we can't estimate, be conservative and use sync
            return False

        return estimated_time > threshold_seconds
