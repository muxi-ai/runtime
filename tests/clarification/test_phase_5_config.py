"""
Test Phase 5: Configuration Support for Clarification System

This module tests the configuration support implementation for the intelligent
parameter collection clarification system.
"""

import pytest
from unittest.mock import AsyncMock, patch
from src.muxi.runtime.overlord.overlord import Overlord
from src.muxi.runtime.clarification.types import QuestionStyle


class TestClarificationConfiguration:
    """Test clarification configuration parsing and application"""

    @pytest.mark.asyncio
    async def test_default_clarification_config(self):
        """Test that default clarification configuration is applied correctly"""
        overlord = Overlord()

        # Should have default configuration
        assert overlord.clarification_config.max_questions == 5
        assert overlord.clarification_config.style == QuestionStyle.CONVERSATIONAL
        assert overlord.clarification_config.persist_learned_info is False

    @pytest.mark.asyncio
    async def test_custom_clarification_config(self):
        """Test that custom clarification configuration is applied correctly"""
        formation_config = {
            "overlord": {
                "clarification": {
                    "max_questions": 10,
                    "style": "formal",
                    "persist_learned_info": True
                }
            }
        }

        overlord = Overlord(formation_config=formation_config)
        await overlord._initialize_clarification_config()

        # Should apply custom configuration
        assert overlord.clarification_config.max_questions == 10
        assert overlord.clarification_config.style == QuestionStyle.FORMAL
        assert overlord.clarification_config.persist_learned_info is True

    @pytest.mark.asyncio
    async def test_brief_style_configuration(self):
        """Test that brief style configuration is applied correctly"""
        formation_config = {
            "overlord": {
                "clarification": {
                    "style": "brief"
                }
            }
        }

        overlord = Overlord(formation_config=formation_config)
        await overlord._initialize_clarification_config()

        # Should apply brief style
        assert overlord.clarification_config.style == QuestionStyle.BRIEF

    @pytest.mark.asyncio
    async def test_invalid_style_fallback(self):
        """Test that invalid style configuration falls back to conversational"""
        formation_config = {
            "overlord": {
                "clarification": {
                    "style": "invalid_style"
                }
            }
        }

        overlord = Overlord(formation_config=formation_config)

        with patch('src.muxi.runtime.overlord.overlord.logger') as mock_logger:
            await overlord._initialize_clarification_config()

            # Should fall back to conversational and log warning
            assert overlord.clarification_config.style == QuestionStyle.CONVERSATIONAL
            mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_invalid_max_questions_fallback(self):
        """Test that invalid max_questions configuration falls back to default"""
        formation_config = {
            "overlord": {
                "clarification": {
                    "max_questions": -1
                }
            }
        }

        overlord = Overlord(formation_config=formation_config)

        with patch('src.muxi.runtime.overlord.overlord.logger') as mock_logger:
            await overlord._initialize_clarification_config()

            # Should fall back to default and log warning
            assert overlord.clarification_config.max_questions == 5
            mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_high_max_questions_warning(self):
        """Test that high max_questions configuration triggers warning"""
        formation_config = {
            "overlord": {
                "clarification": {
                    "max_questions": 25
                }
            }
        }

        overlord = Overlord(formation_config=formation_config)

        with patch('src.muxi.runtime.overlord.overlord.logger') as mock_logger:
            await overlord._initialize_clarification_config()

            # Should accept the value but log warning
            assert overlord.clarification_config.max_questions == 25
            mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_privacy_by_default(self):
        """Test that privacy-by-default is enforced"""
        formation_config = {
            "overlord": {
                "clarification": {
                    # Explicitly don't set persist_learned_info
                }
            }
        }

        overlord = Overlord(formation_config=formation_config)
        await overlord._initialize_clarification_config()

        # Should default to privacy-preserving (False)
        assert overlord.clarification_config.persist_learned_info is False

    @pytest.mark.asyncio
    async def test_no_clarification_config_section(self):
        """Test behavior when no clarification config section is provided"""
        formation_config = {
            "overlord": {}
        }

        overlord = Overlord(formation_config=formation_config)
        await overlord._initialize_clarification_config()

        # Should keep default configuration
        assert overlord.clarification_config.max_questions == 5
        assert overlord.clarification_config.style == QuestionStyle.CONVERSATIONAL
        assert overlord.clarification_config.persist_learned_info is False

    @pytest.mark.asyncio
    async def test_formation_config_integration(self):
        """Test that clarification config is processed during formation loading"""
        formation_config = {
            "overlord": {
                "clarification": {
                    "max_questions": 7,
                    "style": "formal",
                    "persist_learned_info": True
                }
            }
        }

        overlord = Overlord(formation_config=formation_config)

        # Mock the other config methods to avoid dependencies
        with patch.object(overlord, '_initialize_llm_config', new_callable=AsyncMock), \
             patch.object(overlord, '_initialize_auth_config', new_callable=AsyncMock), \
             patch.object(overlord, '_initialize_memory_config', new_callable=AsyncMock), \
             patch.object(overlord, '_initialize_logging_config', new_callable=AsyncMock), \
             patch.object(overlord, '_initialize_document_processing_config',
                          new_callable=AsyncMock), \
             patch.object(overlord, '_initialize_document_components', new_callable=AsyncMock):

            await overlord._apply_formation_config()

        # Should have applied the clarification configuration
        assert overlord.clarification_config.max_questions == 7
        assert overlord.clarification_config.style == QuestionStyle.FORMAL
        assert overlord.clarification_config.persist_learned_info is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
