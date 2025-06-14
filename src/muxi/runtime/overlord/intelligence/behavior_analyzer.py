"""
User Behavior Analyzer for User Experience Intelligence

Analyzes user behavior patterns to infer implicit preferences.
Works with both conversation patterns and feedback data.
"""

import time
import statistics
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict, Counter
from .types import (
    Message,
    FeedbackEvent,
    ImplicitPreference,
    PreferenceType,
    ConfidenceScore,
    BehaviorAnalysisResult,
)
import re


class UserBehaviorAnalyzer:
    """Analyze user behavior to infer implicit preferences"""

    def __init__(self):
        """Initialize behavior analyzer"""
        self.behavior_patterns = {
            "message_length_preferences": self._analyze_message_length_patterns,
            "response_time_preferences": self._analyze_response_time_patterns,
            "interaction_frequency": self._analyze_interaction_frequency,
            "content_engagement": self._analyze_content_engagement,
            "format_preferences": self._analyze_format_preferences,
            "technical_depth_preferences": self._analyze_technical_depth,
            "feedback_patterns": self._analyze_feedback_patterns,
        }

    async def infer_preferences(
        self, conversation_history: List[Message], feedback_data: List[FeedbackEvent]
    ) -> BehaviorAnalysisResult:
        """
        Analyze user behavior to infer implicit preferences

        Args:
            conversation_history: List of conversation messages
            feedback_data: List of user feedback events

        Returns:
            BehaviorAnalysisResult with inferred preferences and patterns
        """
        if not conversation_history and not feedback_data:
            return BehaviorAnalysisResult(
                implicit_preferences=[],
                behavioral_patterns={},
                confidence_score=0.0,
                analysis_method="behavioral_analysis",
                data_sources=[],
            )

        # Analyze different behavior patterns
        behavioral_patterns = {}
        implicit_preferences = []
        data_sources = []

        # Add data sources
        if conversation_history:
            data_sources.append("conversation_history")
        if feedback_data:
            data_sources.append("feedback_data")

        # Run all behavior analysis methods
        for pattern_name, analysis_method in self.behavior_patterns.items():
            try:
                pattern_result = await analysis_method(conversation_history, feedback_data)
                if pattern_result:
                    behavioral_patterns[pattern_name] = pattern_result

                    # Extract preferences from pattern analysis
                    pattern_preferences = self._extract_preferences_from_pattern(
                        pattern_name, pattern_result, conversation_history, feedback_data
                    )
                    implicit_preferences.extend(pattern_preferences)

            except Exception as e:
                print(f"Error analyzing {pattern_name}: {e}")
                continue

        # Calculate overall confidence
        confidence_score = self._calculate_analysis_confidence(
            implicit_preferences, behavioral_patterns, len(conversation_history), len(feedback_data)
        )

        return BehaviorAnalysisResult(
            implicit_preferences=implicit_preferences,
            behavioral_patterns=behavioral_patterns,
            confidence_score=confidence_score,
            analysis_method="behavioral_analysis",
            data_sources=data_sources,
        )

    async def _analyze_message_length_patterns(
        self, messages: List[Message], feedback: List[FeedbackEvent]
    ) -> Dict[str, Any]:
        """Analyze user's message length patterns to infer communication preferences"""
        if not messages:
            return {}

        user_messages = [msg for msg in messages if msg.role == "user"]
        assistant_messages = [msg for msg in messages if msg.role == "assistant"]

        if not user_messages or not assistant_messages:
            return {}

        user_lengths = [len(msg.content) for msg in user_messages]
        assistant_lengths = [len(msg.content) for msg in assistant_messages]

        # Analyze patterns
        avg_user_length = statistics.mean(user_lengths)
        avg_assistant_length = statistics.mean(assistant_lengths)

        # Look for correlation between user message length and engagement
        engagement_scores = self._calculate_message_engagement(messages, feedback)

        return {
            "average_user_message_length": avg_user_length,
            "average_assistant_response_length": avg_assistant_length,
            "user_length_variance": (
                statistics.variance(user_lengths) if len(user_lengths) > 1 else 0
            ),
            "length_engagement_correlation": self._calculate_length_engagement_correlation(
                assistant_lengths, engagement_scores
            ),
            "preferred_response_length_range": self._infer_preferred_length_range(
                assistant_lengths, engagement_scores
            ),
        }

    async def _analyze_response_time_patterns(
        self, messages: List[Message], feedback: List[FeedbackEvent]
    ) -> Dict[str, Any]:
        """Analyze response time patterns to infer pace preferences"""
        if len(messages) < 2:
            return {}

        response_times = []
        for i in range(1, len(messages)):
            if messages[i - 1].role == "user" and messages[i].role == "assistant":
                response_time = messages[i].timestamp - messages[i - 1].timestamp
                response_times.append(response_time)

        if not response_times:
            return {}

        return {
            "average_response_time": statistics.mean(response_times),
            "response_time_variance": (
                statistics.variance(response_times) if len(response_times) > 1 else 0
            ),
            "fastest_response_time": min(response_times),
            "slowest_response_time": max(response_times),
            "preferred_response_time_range": self._infer_preferred_response_time(
                response_times, feedback
            ),
        }

    async def _analyze_interaction_frequency(
        self, messages: List[Message], feedback: List[FeedbackEvent]
    ) -> Dict[str, Any]:
        """Analyze interaction frequency patterns"""
        if not messages:
            return {}

        # Group messages by day
        daily_counts = defaultdict(int)
        for msg in messages:
            if msg.role == "user":
                day = int(msg.timestamp // 86400)  # Group by day
                daily_counts[day] += 1

        if not daily_counts:
            return {}

        counts = list(daily_counts.values())

        return {
            "average_daily_interactions": statistics.mean(counts),
            "interaction_frequency_variance": statistics.variance(counts) if len(counts) > 1 else 0,
            "most_active_day_count": max(counts),
            "interaction_consistency": self._calculate_interaction_consistency(daily_counts),
        }

    async def _analyze_content_engagement(
        self, messages: List[Message], feedback: List[FeedbackEvent]
    ) -> Dict[str, Any]:
        """Analyze engagement with different content types"""
        if not messages:
            return {}

        # Categorize messages by content type
        content_categories = {
            "technical": ["code", "function", "class", "import", "def", "return", "algorithm"],
            "explanatory": ["explain", "why", "how", "what", "because", "reason"],
            "instructional": ["step", "first", "then", "next", "finally", "process"],
            "conversational": ["think", "feel", "opinion", "prefer", "like", "want"],
        }

        category_engagement = {}

        for category, keywords in content_categories.items():
            category_messages = []
            for msg in messages:
                if msg.role == "assistant":
                    content_lower = msg.content.lower()
                    keyword_count = sum(1 for keyword in keywords if keyword in content_lower)
                    if keyword_count > 0:
                        category_messages.append(msg)

            if category_messages:
                engagement_score = self._calculate_category_engagement(category_messages, feedback)
                category_engagement[category] = {
                    "message_count": len(category_messages),
                    "engagement_score": engagement_score,
                    "average_length": statistics.mean(
                        [len(msg.content) for msg in category_messages]
                    ),
                }

        return category_engagement

    async def _analyze_format_preferences(
        self, messages: List[Message], feedback: List[FeedbackEvent]
    ) -> Dict[str, Any]:
        """Analyze preferences for different response formats"""
        if not messages:
            return {}

        format_patterns = {
            "lists": [r"(?:^|\n)\s*[-•*]\s+", r"(?:^|\n)\s*\d+\.\s+"],
            "code_blocks": [r"```", r"`[^`]+`"],
            "headers": [r"(?:^|\n)#+\s+", r"(?:^|\n)[A-Z][A-Za-z\s]+:"],
            "tables": [r"\|.*\|", r"┌.*┐"],
            "structured": [r"(?:^|\n)\s*\w+:\s+", r"(?:^|\n)\s*\*\*\w+\*\*"],
        }

        format_usage = {}

        for format_name, patterns in format_patterns.items():
            format_messages = []
            for msg in messages:
                if msg.role == "assistant":
                    pattern_count = sum(
                        len(re.findall(pattern, msg.content)) for pattern in patterns
                    )
                    if pattern_count > 0:
                        format_messages.append((msg, pattern_count))

            if format_messages:
                engagement_score = self._calculate_format_engagement(format_messages, feedback)
                format_usage[format_name] = {
                    "usage_count": len(format_messages),
                    "engagement_score": engagement_score,
                    "average_pattern_density": statistics.mean(
                        [count for _, count in format_messages]
                    ),
                }

        return format_usage

    async def _analyze_technical_depth(
        self, messages: List[Message], feedback: List[FeedbackEvent]
    ) -> Dict[str, Any]:
        """Analyze preferences for technical depth in responses"""
        if not messages:
            return {}

        technical_indicators = {
            "high_technical": [
                "implementation",
                "algorithm",
                "optimization",
                "architecture",
                "protocol",
            ],
            "medium_technical": ["function", "method", "process", "system", "structure"],
            "low_technical": ["simple", "easy", "basic", "overview", "summary"],
        }

        depth_engagement = {}

        for depth_level, indicators in technical_indicators.items():
            depth_messages = []
            for msg in messages:
                if msg.role == "assistant":
                    content_lower = msg.content.lower()
                    indicator_count = sum(
                        1 for indicator in indicators if indicator in content_lower
                    )
                    if indicator_count > 0:
                        depth_messages.append(msg)

            if depth_messages:
                engagement_score = self._calculate_category_engagement(depth_messages, feedback)
                depth_engagement[depth_level] = {
                    "message_count": len(depth_messages),
                    "engagement_score": engagement_score,
                }

        return depth_engagement

    async def _analyze_feedback_patterns(
        self, messages: List[Message], feedback: List[FeedbackEvent]
    ) -> Dict[str, Any]:
        """Analyze explicit feedback patterns"""
        if not feedback:
            return {}

        feedback_types = Counter(f.feedback_type for f in feedback)
        feedback_timing = [f.timestamp for f in feedback]

        # Analyze feedback content for common themes
        positive_feedback = [f for f in feedback if f.feedback_type == "positive"]
        negative_feedback = [f for f in feedback if f.feedback_type == "negative"]
        corrections = [f for f in feedback if f.feedback_type == "correction"]

        return {
            "feedback_type_distribution": dict(feedback_types),
            "total_feedback_count": len(feedback),
            "positive_ratio": len(positive_feedback) / len(feedback) if feedback else 0,
            "correction_patterns": self._analyze_correction_patterns(corrections),
            "feedback_frequency": len(feedback) / max(1, len(messages)) * 100,  # Percentage
        }

    def _extract_preferences_from_pattern(
        self,
        pattern_name: str,
        pattern_result: Dict[str, Any],
        messages: List[Message],
        feedback: List[FeedbackEvent],
    ) -> List[ImplicitPreference]:
        """Extract implicit preferences from behavior pattern analysis"""
        preferences = []
        current_time = time.time()

        if pattern_name == "message_length_patterns":
            # Infer detail level preference
            preferred_length = pattern_result.get("preferred_response_length_range", {})
            if preferred_length:
                detail_level = self._infer_detail_level_from_length(preferred_length)
                if detail_level:
                    confidence = ConfidenceScore(
                        value=0.7,
                        data_points=len(messages),
                        recency=0.8,
                        consistency=1.0 - pattern_result.get("user_length_variance", 0) / 1000,
                    )

                    preferences.append(
                        ImplicitPreference(
                            preference_type=PreferenceType.DETAIL_LEVEL,
                            value=detail_level,
                            confidence=confidence,
                            inference_method="message_length_analysis",
                            supporting_evidence=[
                                f"Average preferred response length: {preferred_length}"
                            ],
                            timestamp=current_time,
                        )
                    )

        elif pattern_name == "response_time_patterns":
            # Infer interaction pace preference
            avg_response_time = pattern_result.get("average_response_time", 0)
            pace = self._infer_pace_from_response_time(avg_response_time)
            if pace:
                confidence = ConfidenceScore(
                    value=0.6,
                    data_points=len(messages) // 2,  # Pairs of messages
                    recency=0.7,
                    consistency=0.8,
                )

                preferences.append(
                    ImplicitPreference(
                        preference_type=PreferenceType.INTERACTION_PACE,
                        value=pace,
                        confidence=confidence,
                        inference_method="response_time_analysis",
                        supporting_evidence=[
                            f"Average response time tolerance: {avg_response_time:.1f}s"
                        ],
                        timestamp=current_time,
                    )
                )

        elif pattern_name == "content_engagement":
            # Infer content type preferences
            best_engagement = max(
                pattern_result.items(), key=lambda x: x[1].get("engagement_score", 0)
            )
            if best_engagement[1].get("engagement_score", 0) > 0.6:
                confidence = ConfidenceScore(
                    value=0.65,
                    data_points=best_engagement[1].get("message_count", 0),
                    recency=0.7,
                    consistency=0.75,
                )

                preferences.append(
                    ImplicitPreference(
                        preference_type=PreferenceType.CONTENT_TYPE,
                        value=best_engagement[0],
                        confidence=confidence,
                        inference_method="content_engagement_analysis",
                        supporting_evidence=[
                            f"Highest engagement with {best_engagement[0]} content"
                        ],
                        timestamp=current_time,
                    )
                )

        elif pattern_name == "format_preferences":
            # Infer format preferences
            best_format = max(pattern_result.items(), key=lambda x: x[1].get("engagement_score", 0))
            if best_format[1].get("engagement_score", 0) > 0.6:
                confidence = ConfidenceScore(
                    value=0.65,
                    data_points=best_format[1].get("usage_count", 0),
                    recency=0.7,
                    consistency=0.75,
                )

                preferences.append(
                    ImplicitPreference(
                        preference_type=PreferenceType.RESPONSE_FORMAT,
                        value=best_format[0],
                        confidence=confidence,
                        inference_method="format_engagement_analysis",
                        supporting_evidence=[f"Highest engagement with {best_format[0]} format"],
                        timestamp=current_time,
                    )
                )

        elif pattern_name == "technical_depth_preferences":
            # Infer technical depth preference
            best_depth = max(pattern_result.items(), key=lambda x: x[1].get("engagement_score", 0))
            if best_depth[1].get("engagement_score", 0) > 0.6:
                confidence = ConfidenceScore(
                    value=0.7,
                    data_points=best_depth[1].get("message_count", 0),
                    recency=0.8,
                    consistency=0.8,
                )

                preferences.append(
                    ImplicitPreference(
                        preference_type=PreferenceType.TECHNICAL_DEPTH,
                        value=best_depth[0],
                        confidence=confidence,
                        inference_method="technical_depth_analysis",
                        supporting_evidence=[
                            f"Highest engagement with {best_depth[0]} technical depth"
                        ],
                        timestamp=current_time,
                    )
                )

        return preferences

    # Helper methods for analysis
    def _calculate_message_engagement(
        self, messages: List[Message], feedback: List[FeedbackEvent]
    ) -> List[float]:
        """Calculate engagement scores for messages based on feedback"""
        engagement_scores = []

        for msg in messages:
            if msg.role == "assistant":
                # Find feedback for this message
                msg_feedback = [
                    f
                    for f in feedback
                    if f.timestamp > msg.timestamp and f.timestamp < msg.timestamp + 3600
                ]  # Within 1 hour

                if msg_feedback:
                    positive_count = sum(1 for f in msg_feedback if f.feedback_type == "positive")
                    negative_count = sum(1 for f in msg_feedback if f.feedback_type == "negative")
                    total_feedback = len(msg_feedback)

                    if total_feedback > 0:
                        engagement = positive_count / total_feedback
                    else:
                        engagement = 0.5  # Neutral if no feedback
                else:
                    engagement = 0.5  # Neutral if no feedback

                engagement_scores.append(engagement)

        return engagement_scores

    def _calculate_length_engagement_correlation(
        self, lengths: List[int], engagement_scores: List[float]
    ) -> float:
        """Calculate correlation between response length and engagement"""
        if len(lengths) != len(engagement_scores) or len(lengths) < 2:
            return 0.0

        try:
            import numpy as np

            correlation = np.corrcoef(lengths, engagement_scores)[0, 1]
            return correlation if not np.isnan(correlation) else 0.0
        except ImportError:
            # Fallback calculation without numpy
            return self._simple_correlation(lengths, engagement_scores)

    def _simple_correlation(self, x: List[float], y: List[float]) -> float:
        """Simple correlation calculation without numpy"""
        if len(x) != len(y) or len(x) < 2:
            return 0.0

        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi * xi for xi in x)
        sum_y2 = sum(yi * yi for yi in y)

        numerator = n * sum_xy - sum_x * sum_y
        denominator = ((n * sum_x2 - sum_x * sum_x) * (n * sum_y2 - sum_y * sum_y)) ** 0.5

        return numerator / denominator if denominator != 0 else 0.0

    def _infer_preferred_length_range(
        self, lengths: List[int], engagement_scores: List[float]
    ) -> Dict[str, int]:
        """Infer preferred response length range based on engagement"""
        if not lengths or not engagement_scores:
            return {}

        # Find high-engagement messages
        high_engagement_threshold = 0.7
        high_engagement_lengths = [
            lengths[i]
            for i, score in enumerate(engagement_scores)
            if score >= high_engagement_threshold
        ]

        if high_engagement_lengths:
            return {
                "min": min(high_engagement_lengths),
                "max": max(high_engagement_lengths),
                "average": int(statistics.mean(high_engagement_lengths)),
            }

        return {}

    def _infer_preferred_response_time(
        self, response_times: List[float], feedback: List[FeedbackEvent]
    ) -> Dict[str, float]:
        """Infer preferred response time based on feedback patterns"""
        # This is a simplified implementation
        # In practice, you'd correlate response times with feedback
        if response_times:
            return {
                "preferred_max": (
                    statistics.mean(response_times) + statistics.stdev(response_times)
                    if len(response_times) > 1
                    else statistics.mean(response_times)
                ),
                "acceptable_range": statistics.mean(response_times),
            }
        return {}

    def _calculate_interaction_consistency(self, daily_counts: Dict[int, int]) -> float:
        """Calculate consistency of user interactions"""
        if len(daily_counts) < 2:
            return 1.0

        counts = list(daily_counts.values())
        mean_count = statistics.mean(counts)
        variance = statistics.variance(counts)

        # Consistency is inverse of coefficient of variation
        if mean_count > 0:
            cv = (variance**0.5) / mean_count
            return max(0.0, 1.0 - cv)

        return 0.0

    def _calculate_category_engagement(
        self, messages: List[Message], feedback: List[FeedbackEvent]
    ) -> float:
        """Calculate engagement score for a category of messages"""
        if not messages:
            return 0.0

        total_engagement = 0.0
        for msg in messages:
            msg_feedback = [
                f
                for f in feedback
                if f.timestamp > msg.timestamp and f.timestamp < msg.timestamp + 3600
            ]

            if msg_feedback:
                positive_count = sum(1 for f in msg_feedback if f.feedback_type == "positive")
                total_feedback = len(msg_feedback)
                engagement = positive_count / total_feedback if total_feedback > 0 else 0.5
            else:
                engagement = 0.5

            total_engagement += engagement

        return total_engagement / len(messages)

    def _calculate_format_engagement(
        self, format_messages: List[Tuple[Message, int]], feedback: List[FeedbackEvent]
    ) -> float:
        """Calculate engagement score for format usage"""
        if not format_messages:
            return 0.0

        total_engagement = 0.0
        for msg, pattern_count in format_messages:
            msg_feedback = [
                f
                for f in feedback
                if f.timestamp > msg.timestamp and f.timestamp < msg.timestamp + 3600
            ]

            if msg_feedback:
                positive_count = sum(1 for f in msg_feedback if f.feedback_type == "positive")
                total_feedback = len(msg_feedback)
                engagement = positive_count / total_feedback if total_feedback > 0 else 0.5
            else:
                engagement = 0.5

            # Weight by pattern density
            weighted_engagement = engagement * min(pattern_count / 3, 1.0)
            total_engagement += weighted_engagement

        return total_engagement / len(format_messages)

    def _analyze_correction_patterns(self, corrections: List[FeedbackEvent]) -> Dict[str, Any]:
        """Analyze patterns in user corrections"""
        if not corrections:
            return {}

        # Analyze common correction themes
        correction_themes = defaultdict(int)
        for correction in corrections:
            content = correction.feedback_content.lower()

            # Simple theme detection
            if any(word in content for word in ["too long", "verbose", "lengthy"]):
                correction_themes["too_verbose"] += 1
            elif any(word in content for word in ["too short", "brief", "more detail"]):
                correction_themes["too_brief"] += 1
            elif any(word in content for word in ["too technical", "complex", "simpler"]):
                correction_themes["too_technical"] += 1
            elif any(word in content for word in ["not technical", "more detail", "deeper"]):
                correction_themes["not_technical_enough"] += 1

        return {
            "total_corrections": len(corrections),
            "theme_distribution": dict(correction_themes),
            "most_common_theme": (
                max(correction_themes.items(), key=lambda x: x[1])[0] if correction_themes else None
            ),
        }

    def _infer_detail_level_from_length(self, length_range: Dict[str, int]) -> Optional[str]:
        """Infer detail level preference from preferred length range"""
        if not length_range or "average" not in length_range:
            return None

        avg_length = length_range["average"]

        if avg_length < 100:
            return "brief"
        elif avg_length < 300:
            return "concise"
        elif avg_length < 600:
            return "detailed"
        else:
            return "comprehensive"

    def _infer_pace_from_response_time(self, avg_response_time: float) -> Optional[str]:
        """Infer interaction pace preference from response time tolerance"""
        if avg_response_time < 2:
            return "immediate"
        elif avg_response_time < 10:
            return "quick"
        elif avg_response_time < 30:
            return "normal"
        else:
            return "relaxed"

    def _calculate_analysis_confidence(
        self,
        preferences: List[ImplicitPreference],
        behavioral_patterns: Dict[str, Any],
        message_count: int,
        feedback_count: int,
    ) -> float:
        """Calculate overall confidence in behavior analysis"""
        if not preferences:
            return 0.0

        # Base confidence on preference quality
        avg_preference_confidence = sum(
            p.confidence.weighted_confidence for p in preferences
        ) / len(preferences)

        # Adjust for data volume
        data_volume_factor = min((message_count + feedback_count) / 20, 1.0)

        # Adjust for pattern diversity
        pattern_diversity_factor = min(len(behavioral_patterns) / 5, 1.0)

        return (
            avg_preference_confidence * 0.6
            + data_volume_factor * 0.3
            + pattern_diversity_factor * 0.1
        )
