"""
Response parser for extracting structured information from user clarification responses.

This module parses natural language responses to clarification questions and
extracts structured parameter values.
"""

import re

from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta

from .datatypes import ClarificationQuestion, ParameterExtractionError


class ClarificationResponseParser:
    """Parses user responses to clarification questions and extracts structured data"""

    def __init__(self, model=None):
        """
        Initialize the response parser

        Args:
            model: Optional LLM model for complex parsing tasks
        """
        self.model = model
        self._date_patterns = self._compile_date_patterns()
        self._time_patterns = self._compile_time_patterns()
        self._number_patterns = self._compile_number_patterns()

    async def parse_response(
        self, user_response: str, question: ClarificationQuestion, context: Dict[str, Any] = None
    ) -> Tuple[Any, float]:
        """
        Parse user response and extract the requested parameter value

        Args:
            user_response: User's natural language response
            question: The clarification question that was asked
            context: Additional context for parsing

        Returns:
            Tuple of (extracted_value, confidence_score)
        """
        try:
            #  Info - TODO: add observability

            # Clean and normalize the response
            cleaned_response = self._clean_response(user_response)

            # Choose parsing strategy based on parameter type
            param_type = question.parameter_type.lower()

            if param_type == "string":
                return await self._parse_string_response(cleaned_response, question)
            elif param_type in ["integer", "number", "int"]:
                return await self._parse_number_response(cleaned_response, question)
            elif param_type == "boolean":
                return await self._parse_boolean_response(cleaned_response, question)
            elif param_type == "date":
                return await self._parse_date_response(cleaned_response, question)
            elif param_type == "time":
                return await self._parse_time_response(cleaned_response, question)
            elif param_type == "array":
                return await self._parse_array_response(cleaned_response, question)
            else:
                # Default to string parsing
                return await self._parse_string_response(cleaned_response, question)

        except Exception as e:
            #  Error - TODO: add observability
            raise ParameterExtractionError(f"Failed to parse response: {e}")

    async def extract_multiple_parameters(
        self, user_response: str, questions: List[ClarificationQuestion]
    ) -> Dict[str, Tuple[Any, float]]:
        """
        Extract multiple parameters from a single response

        Args:
            user_response: User's response that may contain multiple answers
            questions: List of questions being answered

        Returns:
            Dictionary mapping parameter names to (value, confidence) tuples
        """
        try:
            extracted = {}

            for question in questions:
                value, confidence = await self.parse_response(user_response, question)
                if value is not None:
                    extracted[question.parameter_name] = (value, confidence)

            return extracted

        except Exception as e:
            #  Error - TODO: add observability
            raise ParameterExtractionError(f"Failed to extract multiple parameters: {e}")

    # Private parsing methods

    async def _parse_string_response(
        self, response: str, question: ClarificationQuestion
    ) -> Tuple[Optional[str], float]:
        """Parse string parameter from response"""

        if not response.strip():
            return None, 0.0

        # For string parameters, use the response directly but clean it up
        cleaned = response.strip()

        # Handle special cases based on parameter name
        param_name = question.parameter_name.lower()

        if "location" in param_name or "city" in param_name:
            return self._extract_location(cleaned)
        elif "cuisine" in param_name or "food" in param_name:
            return self._extract_cuisine(cleaned)
        elif "preference" in param_name:
            return self._extract_preferences(cleaned)
        else:
            # Generic string extraction
            return cleaned, 0.8

    async def _parse_number_response(
        self, response: str, question: ClarificationQuestion
    ) -> Tuple[Optional[int], float]:
        """Parse numeric parameter from response"""

        # Try to extract numbers from the response
        numbers = re.findall(r"\d+", response)

        if not numbers:
            # Try to parse written numbers
            written_numbers = self._parse_written_numbers(response)
            if written_numbers:
                return written_numbers[0], 0.8
            return None, 0.0

        # Use the first number found
        number = int(numbers[0])

        # Validate based on parameter name
        param_name = question.parameter_name.lower()
        confidence = 0.9

        if "party_size" in param_name or "people" in param_name:
            if 1 <= number <= 20:
                confidence = 0.95
            elif number > 20:
                confidence = 0.7
        elif "passengers" in param_name:
            if 1 <= number <= 10:
                confidence = 0.95
            else:
                confidence = 0.7

        return number, confidence

    async def _parse_boolean_response(
        self, response: str, question: ClarificationQuestion
    ) -> Tuple[Optional[bool], float]:
        """Parse boolean parameter from response"""

        response_lower = response.lower()

        # Positive indicators
        positive_words = ["yes", "y", "true", "confirm", "ok", "sure", "definitely", "absolutely"]
        negative_words = ["no", "n", "false", "cancel", "nope", "never", "not"]

        positive_score = sum(1 for word in positive_words if word in response_lower)
        negative_score = sum(1 for word in negative_words if word in response_lower)

        if positive_score > negative_score:
            return True, 0.9
        elif negative_score > positive_score:
            return False, 0.9
        else:
            # Ambiguous response
            return None, 0.0

    async def _parse_date_response(
        self, response: str, question: ClarificationQuestion
    ) -> Tuple[Optional[str], float]:
        """Parse date parameter from response"""

        # Try relative dates first
        relative_dates = self._parse_relative_dates(response)
        if relative_dates:
            return relative_dates[0], 0.9

        # Try absolute date patterns
        for pattern, format_str in self._date_patterns:
            match = pattern.search(response)
            if match:
                try:
                    # Validate the date
                    date_str = match.group(0)
                    parsed_date = datetime.strptime(date_str, format_str)
                    return parsed_date.strftime("%Y-%m-%d"), 0.95
                except ValueError:
                    continue

        return None, 0.0

    async def _parse_time_response(
        self, response: str, question: ClarificationQuestion
    ) -> Tuple[Optional[str], float]:
        """Parse time parameter from response"""

        # Try time patterns
        for pattern, format_str in self._time_patterns:
            match = pattern.search(response)
            if match:
                try:
                    time_str = match.group(0)
                    parsed_time = datetime.strptime(time_str, format_str)
                    return parsed_time.strftime("%H:%M"), 0.95
                except ValueError:
                    continue

        # Try relative time expressions
        relative_time = self._parse_relative_time(response)
        if relative_time:
            return relative_time, 0.8

        return None, 0.0

    async def _parse_array_response(
        self, response: str, question: ClarificationQuestion
    ) -> Tuple[Optional[List[str]], float]:
        """Parse array parameter from response"""

        # Split by common delimiters
        delimiters = [",", ";", " and ", " & ", "\n"]
        items = [response]

        for delimiter in delimiters:
            new_items = []
            for item in items:
                new_items.extend([i.strip() for i in item.split(delimiter)])
            items = new_items

        # Clean up items
        cleaned_items = [item for item in items if item and len(item) > 0]

        if cleaned_items:
            return cleaned_items, 0.8
        else:
            return None, 0.0

    # Helper methods

    def _clean_response(self, response: str) -> str:
        """Clean and normalize user response"""
        # Remove extra whitespace
        cleaned = re.sub(r"\s+", " ", response.strip())

        # Remove common filler words at the start
        filler_patterns = [
            r"^(well|so|um|uh|hmm|let me see|i think|maybe|probably)\s*,?\s*",
            r"^(yes|ok|sure)\s*,?\s*",
        ]

        for pattern in filler_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        return cleaned.strip()

    def _extract_location(self, response: str) -> Tuple[str, float]:
        """Extract location from response"""
        # Remove common prefixes
        prefixes = ["in ", "at ", "near ", "around ", "close to "]
        for prefix in prefixes:
            if response.lower().startswith(prefix):
                response = response[len(prefix):].strip()
                break

        # Basic validation - location should be reasonable length
        if 2 <= len(response) <= 50:
            return response, 0.9
        else:
            return response, 0.6

    def _extract_cuisine(self, response: str) -> Tuple[str, float]:
        """Extract cuisine type from response"""
        # Common cuisine mappings
        cuisine_map = {
            "italian": "Italian",
            "chinese": "Chinese",
            "mexican": "Mexican",
            "indian": "Indian",
            "japanese": "Japanese",
            "thai": "Thai",
            "french": "French",
            "pizza": "Italian",
            "sushi": "Japanese",
            "tacos": "Mexican",
        }

        response_lower = response.lower()
        for key, value in cuisine_map.items():
            if key in response_lower:
                return value, 0.9

        # Return as-is if not recognized
        return response, 0.7

    def _extract_preferences(self, response: str) -> Tuple[str, float]:
        """Extract preferences from response"""
        # Just return the response, preferences are subjective
        return response, 0.8

    def _parse_written_numbers(self, response: str) -> List[int]:
        """Parse written numbers like 'two', 'three'"""
        number_words = {
            "zero": 0,
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "eleven": 11,
            "twelve": 12,
            "thirteen": 13,
            "fourteen": 14,
            "fifteen": 15,
            "sixteen": 16,
            "seventeen": 17,
            "eighteen": 18,
            "nineteen": 19,
            "twenty": 20,
        }

        numbers = []
        response_lower = response.lower()

        for word, num in number_words.items():
            if word in response_lower:
                numbers.append(num)

        return numbers

    def _parse_relative_dates(self, response: str) -> List[str]:
        """Parse relative date expressions"""
        today = datetime.now()
        response_lower = response.lower()

        if "today" in response_lower:
            return [today.strftime("%Y-%m-%d")]
        elif "tomorrow" in response_lower:
            tomorrow = today + timedelta(days=1)
            return [tomorrow.strftime("%Y-%m-%d")]
        elif "yesterday" in response_lower:
            yesterday = today - timedelta(days=1)
            return [yesterday.strftime("%Y-%m-%d")]
        elif "next week" in response_lower:
            next_week = today + timedelta(weeks=1)
            return [next_week.strftime("%Y-%m-%d")]

        # Try to parse "in X days"
        days_match = re.search(r"in (\d+) days?", response_lower)
        if days_match:
            days = int(days_match.group(1))
            future_date = today + timedelta(days=days)
            return [future_date.strftime("%Y-%m-%d")]

        return []

    def _parse_relative_time(self, response: str) -> Optional[str]:
        """Parse relative time expressions"""
        response_lower = response.lower()

        time_mappings = {
            "morning": "09:00",
            "afternoon": "14:00",
            "evening": "18:00",
            "night": "20:00",
            "noon": "12:00",
            "midnight": "00:00",
            "breakfast": "08:00",
            "lunch": "12:00",
            "dinner": "19:00",
        }

        for phrase, time in time_mappings.items():
            if phrase in response_lower:
                return time

        return None

    def _compile_date_patterns(self) -> List[Tuple[re.Pattern, str]]:
        """Compile regex patterns for date parsing"""
        patterns = [
            (re.compile(r"\d{4}-\d{2}-\d{2}"), "%Y-%m-%d"),
            (re.compile(r"\d{1,2}/\d{1,2}/\d{4}"), "%m/%d/%Y"),
            (re.compile(r"\d{1,2}-\d{1,2}-\d{4}"), "%m-%d-%Y"),
            (re.compile(r"\d{1,2}/\d{1,2}"), "%m/%d"),
        ]
        return patterns

    def _compile_time_patterns(self) -> List[Tuple[re.Pattern, str]]:
        """Compile regex patterns for time parsing"""
        patterns = [
            (re.compile(r"\d{1,2}:\d{2}\s*(?:AM|PM)", re.IGNORECASE), "%I:%M %p"),
            (re.compile(r"\d{1,2}:\d{2}"), "%H:%M"),
            (re.compile(r"\d{1,2}\s*(?:AM|PM)", re.IGNORECASE), "%I %p"),
        ]
        return patterns

    def _compile_number_patterns(self) -> List[re.Pattern]:
        """Compile regex patterns for number extraction"""
        patterns = [
            re.compile(r"\b\d+\b"),
            re.compile(r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten)\b", re.IGNORECASE),
        ]
        return patterns
