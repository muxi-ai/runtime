#!/usr/bin/env python3
"""
Comprehensive tests for MUXI Scheduler Natural Language Processing Components.
Tests both parser.py and rewriter.py with LLM integration and fallback mechanisms.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from muxi.runtime.services.scheduler.parser import ScheduleParser
from muxi.runtime.services.scheduler.rewriter import PromptRewriter


class TestScheduleParser:
    """Test schedule parser functionality."""
    
    @pytest.fixture
    def parser(self):
        """Create a parser instance."""
        return ScheduleParser()
    
    @pytest.mark.asyncio
    async def test_pattern_matching_basic_schedules(self, parser):
        """Test basic schedule pattern matching without LLM."""
        test_cases = [
            # Frequency patterns
            ("every 15 minutes", "*/15 * * * *"),
            ("every 2 hours", "0 */2 * * *"),
            ("every day", "0 0 * * *"),
            ("daily", "0 0 * * *"),
            ("hourly", "0 * * * *"),
            ("weekly", "0 0 * * 0"),
            ("monthly", "0 0 1 * *"),
            
            # Day + time patterns
            ("every monday at 9am", "0 9 * * 1"),
            ("every friday at 2:30pm", "30 14 * * 5"),
            ("every weekday at noon", "0 12 * * 1-5"),
            
            # Daily time patterns
            ("daily at 6:00am", "0 6 * * *"),
            ("every day at 10pm", "0 22 * * *"),
        ]
        
        for schedule_text, expected_cron in test_cases:
            result = await parser.parse_schedule(schedule_text)
            assert result == expected_cron, f"Failed for '{schedule_text}': got '{result}', expected '{expected_cron}'"
    
    @pytest.mark.asyncio
    async def test_time_parsing_12_hour_format(self, parser):
        """Test 12-hour time format parsing."""
        test_cases = [
            ("9am", (9, 0)),
            ("2pm", (14, 0)),
            ("12am", (0, 0)),
            ("12pm", (12, 0)),
            ("11:30pm", (23, 30)),
            ("6:45am", (6, 45)),
        ]
        
        for time_text, expected in test_cases:
            result = parser._extract_time_from_text(time_text)
            assert result == expected, f"Failed for '{time_text}': got {result}, expected {expected}"
    
    @pytest.mark.asyncio
    async def test_llm_fallback_parsing(self, parser):
        """Test LLM fallback when no pattern matches."""
        with patch.object(parser, '_get_llm', return_value=None):
            # Should use fallback parsing
            result = await parser.parse_schedule("complex scheduling request")
            assert result == "0 9 * * *"  # Ultimate fallback
    
    @pytest.mark.asyncio
    async def test_llm_schedule_parsing_success(self, parser):
        """Test successful LLM schedule parsing."""
        mock_llm = AsyncMock()
        mock_llm.generate_text.return_value = "0 14 * * 1-5"
        
        with patch.object(parser, '_get_llm', return_value=mock_llm):
            result = await parser.parse_schedule("every weekday at 2pm")
            assert result == "0 14 * * 1-5"
    
    @pytest.mark.asyncio
    async def test_llm_schedule_parsing_with_cleanup(self, parser):
        """Test LLM parsing with response cleanup."""
        mock_llm = AsyncMock()
        mock_llm.generate_text.return_value = '"0 9 * * *"  '  # Quoted with whitespace
        
        with patch.object(parser, '_get_llm', return_value=mock_llm):
            result = await parser.parse_schedule("daily morning task")
            assert result == "0 9 * * *"
    
    @pytest.mark.asyncio
    async def test_cron_expression_validation(self, parser):
        """Test cron expression validation."""
        valid_expressions = [
            "0 9 * * *",
            "*/15 * * * *", 
            "0 12 * * 1-5",
            "30 14 1 * *",
            "0 0 1,15 * *",
        ]
        
        invalid_expressions = [
            "invalid cron",
            "0 25 * * *",  # Invalid hour
            "60 9 * * *",  # Invalid minute
            "0 9 32 * *",  # Invalid day
            "0 9 * 13 *",  # Invalid month
        ]
        
        for expr in valid_expressions:
            assert parser._validate_cron_expression(expr), f"Should be valid: {expr}"
        
        for expr in invalid_expressions:
            assert not parser._validate_cron_expression(expr), f"Should be invalid: {expr}"
    
    @pytest.mark.asyncio
    async def test_cron_fix_attempts(self, parser):
        """Test cron expression fixing."""
        test_cases = [
            # 6-field format (with seconds)
            ("0 0 9 * * *", "0 9 * * *"),
            # Quoted expressions
            ('"0 9 * * *"', "0 9 * * *"),
            ("'*/15 * * * *'", "*/15 * * * *"),
            # Extra whitespace
            ("0  9   *  *  *", "0 9 * * *"),
        ]
        
        for original, expected in test_cases:
            result = parser._attempt_cron_fix(original)
            assert result == expected, f"Fix failed for '{original}': got '{result}', expected '{expected}'"
    
    @pytest.mark.asyncio
    async def test_exclusion_rules_generation(self, parser):
        """Test exclusion rules generation."""
        exclusions = ["weekends", "business hours", "lunch time"]
        
        # Test with mock LLM
        mock_llm = AsyncMock()
        mock_llm.generate_text.return_value = '{"type": "cron", "pattern": "* * * * 0,6", "description": "Exclude weekends"}'
        
        with patch.object(parser, '_get_llm', return_value=mock_llm):
            rules = await parser.generate_exclusion_rules(exclusions)
            assert len(rules) == 3
            assert all('type' in rule and 'pattern' in rule for rule in rules)
    
    @pytest.mark.asyncio
    async def test_fallback_exclusion_rules(self, parser):
        """Test fallback exclusion rule generation without LLM."""
        exclusions = ["weekends", "business hours", "unknown pattern"]
        
        with patch.object(parser, '_get_llm', return_value=None):
            rules = await parser.generate_exclusion_rules(exclusions)
            assert len(rules) == 3
            
            # Check specific patterns
            weekend_rule = next(rule for rule in rules if 'weekends' in rule['description'].lower())
            assert weekend_rule['pattern'] == '* * * * 0,6'
            
            business_rule = next(rule for rule in rules if 'business hours' in rule['description'].lower())
            assert business_rule['pattern'] == '* 9-17 * * 1-5'
    
    @pytest.mark.asyncio
    async def test_timezone_conversion(self, parser):
        """Test cron expression timezone conversion."""
        # Test basic hour conversion
        result = await parser.convert_timezone_cron("0 14 * * *", "UTC", "America/New_York")
        # Should convert 14:00 UTC to appropriate local time
        assert result != "0 14 * * *"  # Should be different
        
        # Test non-specific hour (shouldn't convert)
        result = await parser.convert_timezone_cron("0 * * * *", "UTC", "America/New_York")
        assert result == "0 * * * *"  # Should remain unchanged


class TestPromptRewriter:
    """Test prompt rewriter functionality."""
    
    @pytest.fixture
    def rewriter(self):
        """Create a rewriter instance."""
        return PromptRewriter()
    
    @pytest.mark.asyncio
    async def test_pattern_rewriting_basic(self, rewriter):
        """Test basic pattern rewriting without LLM."""
        test_cases = [
            # Scheduled context patterns
            ("check my email", "Check and report on my email"),
            ("remind me about meeting", "Send reminder: about meeting"),
            ("tell me the weather", "Report on the weather"),
            ("show me status", "Display information about status"),
            ("update me on project", "Provide status update on project"),
            
            # Temporal transformations
            ("do this right now", "do this at this scheduled time"),
            ("check status currently", "check status at this scheduled time"),
            ("update today", "update for today"),
            
            # Simple commands
            ("email", "Check and provide update on email"),
            ("weather", "Check and provide update on weather"),
            ("status", "Check and provide update on status"),
        ]
        
        for original, expected in test_cases:
            result = await rewriter.rewrite_for_execution(original)
            assert result == expected, f"Failed for '{original}': got '{result}', expected '{expected}'"
    
    @pytest.mark.asyncio
    async def test_llm_rewriting_success(self, rewriter):
        """Test successful LLM prompt rewriting."""
        mock_llm = AsyncMock()
        mock_llm.generate_text.return_value = "Check email for new messages and provide summary of important items"
        
        with patch.object(rewriter, '_get_llm', return_value=mock_llm):
            result = await rewriter.rewrite_for_execution("check my email")
            assert "Check email for new messages" in result
    
    @pytest.mark.asyncio
    async def test_llm_rewriting_fallback(self, rewriter):
        """Test LLM rewriting fallback to pattern matching."""
        with patch.object(rewriter, '_get_llm', return_value=None):
            result = await rewriter.rewrite_for_execution("check my email")
            assert "Check and report on my email" == result
    
    @pytest.mark.asyncio
    async def test_enhanced_pattern_rewrite(self, rewriter):
        """Test enhanced pattern rewriting method."""
        test_cases = [
            ("check system", "check system and provide a summary"),
            ("get weather", "get weather and provide a summary"),
            ("tell me status", "Report on status"),
            ("remind about meeting", "Send notification: about meeting"),
            ("monitor logs", "Monitor logs and report any changes"),
        ]
        
        for original, expected in test_cases:
            result = rewriter._enhanced_pattern_rewrite(original)
            assert expected.lower() in result.lower(), f"Failed for '{original}': got '{result}'"
    
    @pytest.mark.asyncio
    async def test_formation_enhancement(self, rewriter):
        """Test formation-specific prompt enhancement."""
        formation_config = {
            'agents': [
                {'id': 'email_agent', 'specialization': 'Email processing and analysis'},
                {'id': 'data_agent', 'specialization': 'Data analysis and reporting'}
            ],
            'mcp': {
                'servers': [
                    {'id': 'email_server', 'description': 'Email access and management'},
                    {'id': 'calendar_server', 'description': 'Calendar and scheduling'}
                ]
            }
        }
        
        mock_llm = AsyncMock()
        mock_llm.generate_text.return_value = "Use email_agent to check email and provide summary using email_server"
        
        with patch.object(rewriter, '_get_llm', return_value=mock_llm):
            result = await rewriter.enhance_for_formation("check email", formation_config)
            assert "email_agent" in result or "email_server" in result
    
    @pytest.mark.asyncio
    async def test_formation_enhancement_no_llm(self, rewriter):
        """Test formation enhancement fallback without LLM."""
        formation_config = {'agents': [], 'mcp': {'servers': []}}
        
        with patch.object(rewriter, '_get_llm', return_value=None):
            original = "check email"
            result = await rewriter.enhance_for_formation(original, formation_config)
            assert result == original  # Should return unchanged
    
    @pytest.mark.asyncio
    async def test_scheduling_context_addition(self, rewriter):
        """Test adding scheduling context to prompts."""
        schedule_info = {
            'frequency': 'daily',
            'timezone': 'UTC',
            'user_id': 'test_user'
        }
        
        result = await rewriter.add_scheduling_context("check email", schedule_info)
        assert "[Scheduled Task Context:" in result
        assert "daily" in result
        assert "UTC" in result
        assert "test_user" in result
        assert "check email" in result
    
    @pytest.mark.asyncio
    async def test_prompt_validation(self, rewriter):
        """Test execution prompt validation."""
        # Valid prompt
        valid_result = await rewriter.validate_execution_prompt("Check email and send summary")
        assert valid_result['valid'] == True
        assert valid_result['score'] > 5
        
        # Problematic prompt with ambiguous references
        invalid_result = await rewriter.validate_execution_prompt("check this and tell me about it")
        assert valid_result['valid'] == True  # Will still be marked valid but with issues
        assert len(invalid_result['issues']) > 0
        assert len(invalid_result['suggestions']) > 0
        
        # Short prompt
        short_result = await rewriter.validate_execution_prompt("email")
        assert len(short_result['issues']) > 0
        assert any("too short" in issue for issue in short_result['issues'])
    
    @pytest.mark.asyncio
    async def test_execution_summary_prompt_generation(self, rewriter):
        """Test execution summary prompt generation."""
        result = await rewriter.generate_execution_summary_prompt("check email", "daily")
        
        assert "check email" in result
        assert "daily" in result
        assert "What was accomplished" in result
        assert "Key findings" in result
        assert "issues or errors" in result


class TestIntegratedNLPComponents:
    """Test integrated NLP component functionality."""
    
    @pytest.mark.asyncio
    async def test_schedule_parsing_and_prompt_rewriting_integration(self):
        """Test integrated parsing and rewriting workflow."""
        parser = ScheduleParser()
        rewriter = PromptRewriter()
        
        # Test complete workflow
        original_prompt = "check my email for important messages"
        schedule_text = "every morning at 9am"
        exclusions = ["weekends"]
        
        # Parse schedule
        cron_expr = await parser.parse_schedule(schedule_text)
        assert cron_expr == "0 9 * * *"
        
        # Generate exclusion rules
        exclusion_rules = await parser.generate_exclusion_rules(exclusions)
        assert len(exclusion_rules) >= 1
        assert any('weekend' in rule['description'].lower() for rule in exclusion_rules)
        
        # Rewrite prompt
        execution_prompt = await rewriter.rewrite_for_execution(original_prompt)
        assert execution_prompt != original_prompt
        assert "check" in execution_prompt.lower()
        assert "email" in execution_prompt.lower()
        
        # Validate execution prompt
        validation = await rewriter.validate_execution_prompt(execution_prompt)
        assert validation['score'] > 0
    
    @pytest.mark.asyncio
    async def test_error_handling_and_fallbacks(self):
        """Test comprehensive error handling and fallback mechanisms."""
        parser = ScheduleParser()
        rewriter = PromptRewriter()
        
        # Test parser fallbacks
        with patch.object(parser, '_get_llm', side_effect=Exception("LLM Error")):
            result = await parser.parse_schedule("complex schedule that needs LLM")
            assert result == "0 9 * * *"  # Ultimate fallback
        
        # Test rewriter fallbacks
        with patch.object(rewriter, '_get_llm', return_value=None):
            result = await rewriter.rewrite_for_execution("check my email")
            assert result != "check my email"  # Should be enhanced


if __name__ == "__main__":
    # Run basic integration tests
    async def run_basic_tests():
        print("🧪 Running MUXI Scheduler NLP Component Tests...")
        
        try:
            # Test parser
            parser = ScheduleParser()
            result = await parser.parse_schedule("every day at 9am")
            assert result == "0 9 * * *"
            print("   ✓ Schedule parser working")
            
            # Test rewriter
            rewriter = PromptRewriter()
            result = await rewriter.rewrite_for_execution("check my email")
            assert result != "check my email"
            print("   ✓ Prompt rewriter working")
            
            # Test validation
            validation = await rewriter.validate_execution_prompt("Check email and provide summary")
            assert validation['valid'] == True
            print("   ✓ Prompt validation working")
            
            print("🎉 All NLP component tests passed!")
            
        except Exception as e:
            print(f"   ❌ NLP component test failed: {e}")
            import traceback
            traceback.print_exc()
    
    # Run the test
    asyncio.run(run_basic_tests())