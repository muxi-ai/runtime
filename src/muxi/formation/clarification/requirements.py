"""
Information requirement definitions for common tools and reasoning scenarios.

This module provides standardized requirement definitions for tools and
reasoning contexts to enable consistent clarification across the system.
"""

from typing import Any, Dict, List


class InformationRequirements:
    """Centralized definitions of information requirements for tools and reasoning"""

    def __init__(self):
        self.tool_requirements = self._load_tool_requirements()
        self.reasoning_requirements = self._load_reasoning_requirements()

    def get_tool_requirements(self, tool_name: str) -> Dict[str, Any]:
        """
        Get information requirements for a specific tool

        Args:
            tool_name: Name of the tool

        Returns:
            Dictionary containing parameter requirements
        """
        return self.tool_requirements.get(tool_name, {})

    def get_reasoning_requirements(self, intent: str) -> Dict[str, Any]:
        """
        Get information requirements for reasoning scenarios

        Args:
            intent: The reasoning intent/category

        Returns:
            Dictionary containing context requirements
        """
        for pattern, requirements in self.reasoning_requirements.items():
            if pattern.lower() in intent.lower():
                return requirements

        return self.reasoning_requirements.get("general", {})

    def get_all_tool_names(self) -> List[str]:
        """Get list of all supported tool names"""
        return list(self.tool_requirements.keys())

    def get_all_reasoning_categories(self) -> List[str]:
        """Get list of all reasoning categories"""
        return list(self.reasoning_requirements.keys())

    def _load_tool_requirements(self) -> Dict[str, Dict[str, Any]]:
        """Load tool requirement definitions"""
        return {
            "book_restaurant": {
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City, area, or specific address for the restaurant",
                        "required": True,
                        "examples": ["New York", "Manhattan", "Downtown Seattle"],
                        "validation": {"min_length": 2, "max_length": 100},
                    },
                    "date": {
                        "type": "date",
                        "description": "Date for the reservation",
                        "required": True,
                        "examples": ["2024-01-15", "tomorrow", "next Friday"],
                        "validation": {"future_only": True},
                    },
                    "time": {
                        "type": "time",
                        "description": "Time for the reservation",
                        "required": True,
                        "examples": ["7:30 PM", "19:30", "dinner time"],
                        "validation": {"format": "HH:MM"},
                    },
                    "party_size": {
                        "type": "integer",
                        "description": "Number of people for the reservation",
                        "required": True,
                        "examples": [2, 4, 6],
                        "validation": {"min": 1, "max": 20},
                    },
                    "cuisine": {
                        "type": "string",
                        "description": "Type of cuisine preferred",
                        "required": False,
                        "examples": ["Italian", "Chinese", "French", "Any"],
                        "validation": {"max_length": 50},
                    },
                    "price_range": {
                        "type": "string",
                        "description": "Preferred price range",
                        "required": False,
                        "examples": ["$", "$$", "$$$", "$$$$"],
                        "validation": {"enum": ["$", "$$", "$$$", "$$$$"]},
                    },
                    "special_requests": {
                        "type": "string",
                        "description": "Special dietary requirements or requests",
                        "required": False,
                        "examples": ["vegetarian", "gluten-free", "outdoor seating"],
                        "validation": {"max_length": 200},
                    },
                },
                "required": ["location", "date", "time", "party_size"],
                "priority_order": [
                    "location",
                    "date",
                    "time",
                    "party_size",
                    "cuisine",
                    "price_range",
                    "special_requests",
                ],
            },
            "book_flight": {
                "properties": {
                    "departure": {
                        "type": "string",
                        "description": "Departure location (city or airport)",
                        "required": True,
                        "examples": ["New York", "JFK", "Los Angeles"],
                        "validation": {"min_length": 2, "max_length": 100},
                    },
                    "destination": {
                        "type": "string",
                        "description": "Destination location (city or airport)",
                        "required": True,
                        "examples": ["London", "LHR", "Tokyo"],
                        "validation": {"min_length": 2, "max_length": 100},
                    },
                    "departure_date": {
                        "type": "date",
                        "description": "Date of departure",
                        "required": True,
                        "examples": ["2024-03-15", "next Monday", "March 15th"],
                        "validation": {"future_only": True},
                    },
                    "return_date": {
                        "type": "date",
                        "description": "Return date (for round-trip flights)",
                        "required": False,
                        "examples": ["2024-03-22", "one week later"],
                        "validation": {"after_departure": True},
                    },
                    "passengers": {
                        "type": "integer",
                        "description": "Number of passengers",
                        "required": True,
                        "examples": [1, 2, 4],
                        "validation": {"min": 1, "max": 9},
                    },
                    "class": {
                        "type": "string",
                        "description": "Flight class preference",
                        "required": False,
                        "examples": ["economy", "business", "first"],
                        "validation": {"enum": ["economy", "premium_economy", "business", "first"]},
                    },
                    "flexible_dates": {
                        "type": "boolean",
                        "description": "Whether dates are flexible for better prices",
                        "required": False,
                        "examples": [True, False],
                    },
                },
                "required": ["departure", "destination", "departure_date", "passengers"],
                "priority_order": [
                    "departure",
                    "destination",
                    "departure_date",
                    "passengers",
                    "return_date",
                    "class",
                    "flexible_dates",
                ],
            },
            "search_hotels": {
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City or area to search for hotels",
                        "required": True,
                        "examples": ["Paris", "Downtown Miami", "Near Times Square"],
                        "validation": {"min_length": 2, "max_length": 100},
                    },
                    "check_in": {
                        "type": "date",
                        "description": "Check-in date",
                        "required": True,
                        "examples": ["2024-06-01", "next Friday"],
                        "validation": {"future_only": True},
                    },
                    "check_out": {
                        "type": "date",
                        "description": "Check-out date",
                        "required": True,
                        "examples": ["2024-06-05", "4 days later"],
                        "validation": {"after_checkin": True},
                    },
                    "guests": {
                        "type": "integer",
                        "description": "Number of guests",
                        "required": True,
                        "examples": [1, 2, 4],
                        "validation": {"min": 1, "max": 8},
                    },
                    "budget": {
                        "type": "string",
                        "description": "Budget range per night",
                        "required": False,
                        "examples": ["under $100", "$100-200", "luxury"],
                        "validation": {"max_length": 50},
                    },
                },
                "required": ["location", "check_in", "check_out", "guests"],
                "priority_order": ["location", "check_in", "check_out", "guests", "budget"],
            },
        }

    def _load_reasoning_requirements(self) -> Dict[str, Dict[str, Any]]:
        """Load reasoning requirement definitions"""
        return {
            "investment": {
                "context_requirements": {
                    "risk_tolerance": {
                        "type": "string",
                        "description": "Investment risk comfort level",
                        "required": True,
                        "examples": ["conservative", "moderate", "aggressive"],
                        "validation": {"enum": ["conservative", "moderate", "aggressive"]},
                    },
                    "investment_timeline": {
                        "type": "string",
                        "description": "Time horizon for investments",
                        "required": True,
                        "examples": [
                            "working (< 2 years)",
                            "medium-term (2-10 years)",
                            "long-term (> 10 years)",
                        ],
                        "validation": {"max_length": 100},
                    },
                    "financial_goals": {
                        "type": "string",
                        "description": "Primary financial objectives",
                        "required": True,
                        "examples": ["retirement", "house purchase", "wealth building"],
                        "validation": {"max_length": 200},
                    },
                    "current_portfolio": {
                        "type": "string",
                        "description": "Current investment holdings",
                        "required": False,
                        "examples": [
                            "mostly cash",
                            "some stocks and bonds",
                            "diversified portfolio",
                        ],
                        "validation": {"max_length": 300},
                    },
                    "income_level": {
                        "type": "string",
                        "description": "Income range for investment planning",
                        "required": False,
                        "examples": ["under $50k", "$50k-$100k", "over $100k"],
                        "validation": {"max_length": 50},
                    },
                },
                "required": ["risk_tolerance", "investment_timeline", "financial_goals"],
                "priority_order": [
                    "risk_tolerance",
                    "investment_timeline",
                    "financial_goals",
                    "current_portfolio",
                    "income_level",
                ],
            },
            "technical_explanation": {
                "context_requirements": {
                    "technical_background": {
                        "type": "string",
                        "description": "Technical expertise level",
                        "required": True,
                        "examples": ["beginner", "intermediate", "advanced", "expert"],
                        "validation": {"enum": ["beginner", "intermediate", "advanced", "expert"]},
                    },
                    "specific_interest": {
                        "type": "string",
                        "description": "Specific aspect of interest",
                        "required": True,
                        "examples": [
                            "practical applications",
                            "theoretical concepts",
                            "implementation details",
                        ],
                        "validation": {"max_length": 200},
                    },
                    "use_case": {
                        "type": "string",
                        "description": "Intended use or application",
                        "required": False,
                        "examples": ["work project", "personal learning", "academic research"],
                        "validation": {"max_length": 200},
                    },
                    "time_available": {
                        "type": "string",
                        "description": "Time available for learning or explanation",
                        "required": False,
                        "examples": ["5 minutes", "detailed explanation", "just the basics"],
                        "validation": {"max_length": 100},
                    },
                },
                "required": ["technical_background", "specific_interest"],
                "priority_order": [
                    "technical_background",
                    "specific_interest",
                    "use_case",
                    "time_available",
                ],
            },
            "recommendation": {
                "context_requirements": {
                    "goals": {
                        "type": "string",
                        "description": "What you want to achieve",
                        "required": True,
                        "examples": ["improve health", "save money", "learn new skills"],
                        "validation": {"max_length": 200},
                    },
                    "constraints": {
                        "type": "string",
                        "description": "Limitations or restrictions",
                        "required": True,
                        "examples": ["limited time", "budget constraints", "physical limitations"],
                        "validation": {"max_length": 200},
                    },
                    "preferences": {
                        "type": "string",
                        "description": "Personal preferences or style",
                        "required": False,
                        "examples": ["prefer online", "hands-on learning", "structured approach"],
                        "validation": {"max_length": 200},
                    },
                    "experience_level": {
                        "type": "string",
                        "description": "Current experience with the topic",
                        "required": False,
                        "examples": ["complete beginner", "some experience", "quite experienced"],
                        "validation": {"max_length": 100},
                    },
                },
                "required": ["goals", "constraints"],
                "priority_order": ["goals", "constraints", "preferences", "experience_level"],
            },
            "general": {
                "context_requirements": {
                    "more_details": {
                        "type": "string",
                        "description": "Additional details about your request",
                        "required": True,
                        "examples": ["specific requirements", "background information", "context"],
                        "validation": {"max_length": 500},
                    },
                    "urgency": {
                        "type": "string",
                        "description": "How urgent or important this is",
                        "required": False,
                        "examples": ["very urgent", "when convenient", "just curious"],
                        "validation": {"max_length": 100},
                    },
                },
                "required": ["more_details"],
                "priority_order": ["more_details", "urgency"],
            },
        }

    def validate_parameter(self, param_name: str, value: Any, requirements: Dict[str, Any]) -> bool:
        """
        Validate a parameter value against its requirements

        Args:
            param_name: Name of the parameter
            value: Value to validate
            requirements: Parameter requirements

        Returns:
            True if valid, False otherwise
        """
        param_schema = requirements.get("properties", {}).get(param_name, {})
        validation_rules = param_schema.get("validation", {})

        # Type validation
        param_type = param_schema.get("type", "string")
        if not self._validate_type(value, param_type):
            return False

        # Custom validation rules
        for rule, constraint in validation_rules.items():
            if not self._validate_rule(value, rule, constraint):
                return False

        return True

    def _validate_type(self, value: Any, param_type: str) -> bool:
        """Validate parameter type"""
        if param_type == "string":
            return isinstance(value, str)
        elif param_type == "integer":
            return isinstance(value, int)
        elif param_type == "boolean":
            return isinstance(value, bool)
        elif param_type in ["date", "time"]:
            return isinstance(value, str)  # Dates/times are stored as strings
        elif param_type == "array":
            return isinstance(value, list)
        else:
            return True  # Unknown types pass validation

    def _validate_rule(self, value: Any, rule: str, constraint: Any) -> bool:
        """Validate a specific rule"""
        if rule == "min_length" and isinstance(value, str):
            return len(value) >= constraint
        elif rule == "max_length" and isinstance(value, str):
            return len(value) <= constraint
        elif rule == "min" and isinstance(value, (int, float)):
            return value >= constraint
        elif rule == "max" and isinstance(value, (int, float)):
            return value <= constraint
        elif rule == "enum":
            return value in constraint
        # Add more validation rules as needed
        return True
