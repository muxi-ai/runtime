"""
Unit tests for threat_type field validator in RequestAnalysis
"""

import pytest
from pydantic import ValidationError

from muxi.runtime.datatypes.workflow import RequestAnalysis


class TestThreatTypeValidator:
    """Test threat_type field validation."""

    def test_none_value_allowed(self):
        """Test that None is a valid value."""
        analysis = RequestAnalysis(
            complexity_score=5.0,
            requires_decomposition=False,
            requires_approval=False,
            implicit_subtasks=["task1"],
            required_capabilities=["cap1"],
            acceptance_criteria=["crit1"],
            confidence_score=0.8,
            is_security_threat=False,
            threat_type=None,
        )
        assert analysis.threat_type is None

    def test_valid_threat_types(self):
        """Test all valid threat type values."""
        valid_threats = [
            "prompt_injection",
            "credential_fishing",
            "information_extraction",
            "jailbreak",
        ]

        for threat in valid_threats:
            analysis = RequestAnalysis(
                complexity_score=5.0,
                requires_decomposition=False,
                requires_approval=False,
                implicit_subtasks=["task1"],
                required_capabilities=["cap1"],
                acceptance_criteria=["crit1"],
                confidence_score=0.8,
                is_security_threat=True,
                threat_type=threat,
            )
            assert analysis.threat_type == threat

    def test_normalization_lowercase(self):
        """Test that threat types are normalized to lowercase."""
        test_cases = [
            ("PROMPT_INJECTION", "prompt_injection"),
            ("Credential_Fishing", "credential_fishing"),
            ("Information_Extraction", "information_extraction"),
            ("JailBreak", "jailbreak"),
        ]

        for input_val, expected in test_cases:
            analysis = RequestAnalysis(
                complexity_score=5.0,
                requires_decomposition=False,
                requires_approval=False,
                implicit_subtasks=["task1"],
                required_capabilities=["cap1"],
                acceptance_criteria=["crit1"],
                confidence_score=0.8,
                is_security_threat=True,
                threat_type=input_val,
            )
            assert analysis.threat_type == expected

    def test_normalization_whitespace(self):
        """Test that whitespace is stripped."""
        test_cases = [
            "  prompt_injection  ",
            "\tcredential_fishing\t",
            "\ninformation_extraction\n",
            "  jailbreak  ",
        ]

        for input_val in test_cases:
            analysis = RequestAnalysis(
                complexity_score=5.0,
                requires_decomposition=False,
                requires_approval=False,
                implicit_subtasks=["task1"],
                required_capabilities=["cap1"],
                acceptance_criteria=["crit1"],
                confidence_score=0.8,
                is_security_threat=True,
                threat_type=input_val,
            )
            assert analysis.threat_type == input_val.strip().lower()

    def test_combined_normalization(self):
        """Test normalization of both case and whitespace."""
        analysis = RequestAnalysis(
            complexity_score=5.0,
            requires_decomposition=False,
            requires_approval=False,
            implicit_subtasks=["task1"],
            required_capabilities=["cap1"],
            acceptance_criteria=["crit1"],
            confidence_score=0.8,
            is_security_threat=True,
            threat_type="  PROMPT_INJECTION  ",
        )
        assert analysis.threat_type == "prompt_injection"

    def test_invalid_threat_type_string(self):
        """Test that invalid threat type strings raise ValueError."""
        invalid_values = [
            "invalid_threat",
            "sql_injection",
            "xss",
            "code_injection",
            "path_traversal",
        ]

        for invalid in invalid_values:
            with pytest.raises(ValidationError) as exc_info:
                RequestAnalysis(
                    complexity_score=5.0,
                    requires_decomposition=False,
                    requires_approval=False,
                    implicit_subtasks=["task1"],
                    required_capabilities=["cap1"],
                    acceptance_criteria=["crit1"],
                    confidence_score=0.8,
                    is_security_threat=True,
                    threat_type=invalid,
                )

            # Check error message contains the invalid value and valid options
            error_msg = str(exc_info.value)
            assert invalid in error_msg or invalid.upper() in error_msg
            assert "credential_fishing" in error_msg
            assert "information_extraction" in error_msg
            assert "jailbreak" in error_msg
            assert "prompt_injection" in error_msg

    def test_non_string_value_rejected(self):
        """Test that non-string, non-None values are rejected."""
        invalid_values = [
            123,
            ["prompt_injection"],
            {"type": "prompt_injection"},
            True,
        ]

        for invalid in invalid_values:
            with pytest.raises(ValidationError) as exc_info:
                RequestAnalysis(
                    complexity_score=5.0,
                    requires_decomposition=False,
                    requires_approval=False,
                    implicit_subtasks=["task1"],
                    required_capabilities=["cap1"],
                    acceptance_criteria=["crit1"],
                    confidence_score=0.8,
                    is_security_threat=True,
                    threat_type=invalid,
                )

            error_msg = str(exc_info.value)
            # Pydantic catches type errors before our validator runs
            assert (
                "must be a string or None" in error_msg
                or "Input should be a valid string" in error_msg
            )

    def test_empty_string_rejected(self):
        """Test that empty string (after stripping) is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            RequestAnalysis(
                complexity_score=5.0,
                requires_decomposition=False,
                requires_approval=False,
                implicit_subtasks=["task1"],
                required_capabilities=["cap1"],
                acceptance_criteria=["crit1"],
                confidence_score=0.8,
                is_security_threat=True,
                threat_type="   ",  # Only whitespace
            )

        error_msg = str(exc_info.value)
        assert "Invalid threat_type" in error_msg

    def test_security_threat_false_with_none(self):
        """Test that is_security_threat=False can have threat_type=None."""
        analysis = RequestAnalysis(
            complexity_score=5.0,
            requires_decomposition=False,
            requires_approval=False,
            implicit_subtasks=["task1"],
            required_capabilities=["cap1"],
            acceptance_criteria=["crit1"],
            confidence_score=0.8,
            is_security_threat=False,
            threat_type=None,
        )
        assert not analysis.is_security_threat
        assert analysis.threat_type is None

    def test_security_threat_true_with_valid_type(self):
        """Test that is_security_threat=True can have valid threat_type."""
        analysis = RequestAnalysis(
            complexity_score=5.0,
            requires_decomposition=False,
            requires_approval=False,
            implicit_subtasks=["task1"],
            required_capabilities=["cap1"],
            acceptance_criteria=["crit1"],
            confidence_score=0.8,
            is_security_threat=True,
            threat_type="prompt_injection",
        )
        assert analysis.is_security_threat
        assert analysis.threat_type == "prompt_injection"
