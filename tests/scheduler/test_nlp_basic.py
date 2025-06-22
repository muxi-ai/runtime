#!/usr/bin/env python3
"""
Basic tests for MUXI Scheduler NLP Components without external dependencies.
Tests core functionality of parser and rewriter without requiring full MUXI setup.
"""

import asyncio
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime


class MockObservability:
    """Mock observability for testing."""
    
    @staticmethod
    def observe(*args, **kwargs):
        pass

# Mock the observability module
observability = MockObservability()


class MockLLM:
    """Mock LLM for testing."""
    
    async def generate_text(self, prompt: str) -> str:
        # Simple mock responses based on prompt content
        if "cron" in prompt.lower():
            return "0 9 * * *"
        elif "json" in prompt.lower():
            return '{"type": "cron", "pattern": "* * * * 0,6", "description": "Exclude weekends"}'
        else:
            return "Execute scheduled task: mock response"


class SimpleScheduleParser:
    """Simplified version of ScheduleParser for testing."""
    
    def __init__(self):
        self.llm = None
        
        # Common time patterns
        self.time_patterns = {
            r'(\d{1,2})\s*(am|pm)': self._parse_12hour,
            r'(\d{1,2}):(\d{2})\s*(am|pm)': self._parse_12hour_minutes,
            r'(\d{1,2}):(\d{2})': self._parse_24hour,
        }
        
        # Common frequency patterns
        self.frequency_patterns = {
            r'every\s+(\d+)\s+minutes?': lambda m: f"*/{m.group(1)} * * * *",
            r'every\s+(\d+)\s+hours?': lambda m: f"0 */{m.group(1)} * * *",
            r'every\s+(\d+)\s+days?': lambda m: f"0 0 */{m.group(1)} * *",
            r'every\s+hour': lambda m: "0 * * * *",
            r'every\s+day': lambda m: "0 0 * * *",
            r'hourly': lambda m: "0 * * * *",
            r'daily': lambda m: "0 0 * * *",
            r'weekly': lambda m: "0 0 * * 0",
            r'monthly': lambda m: "0 0 1 * *",
        }
        
        # Day patterns
        self.day_patterns = {
            'monday': '1', 'tuesday': '2', 'wednesday': '3', 'thursday': '4',
            'friday': '5', 'saturday': '6', 'sunday': '0',
            'weekdays': '1-5', 'weekends': '0,6',
        }
    
    def _parse_12hour(self, match) -> Tuple[int, int]:
        hour = int(match.group(1))
        am_pm = match.group(2).lower()
        
        if am_pm == 'pm' and hour != 12:
            hour += 12
        elif am_pm == 'am' and hour == 12:
            hour = 0
        
        return hour, 0
    
    def _parse_12hour_minutes(self, match) -> Tuple[int, int]:
        hour = int(match.group(1))
        minute = int(match.group(2))
        am_pm = match.group(3).lower()
        
        if am_pm == 'pm' and hour != 12:
            hour += 12
        elif am_pm == 'am' and hour == 12:
            hour = 0
        
        return hour, minute
    
    def _parse_24hour(self, match) -> Tuple[int, int]:
        hour = int(match.group(1))
        minute = int(match.group(2))
        return hour, minute
    
    def _extract_time_from_text(self, text: str) -> Optional[Tuple[int, int]]:
        for pattern, parser in self.time_patterns.items():
            match = re.search(pattern, text)
            if match:
                return parser(match)
        return None
    
    def _extract_day_from_text(self, text: str) -> Optional[str]:
        for day_text, day_spec in self.day_patterns.items():
            if day_text in text:
                return day_spec
        return None
    
    async def parse_schedule(self, schedule_text: str, timezone: str = "UTC") -> str:
        schedule_lower = schedule_text.lower().strip()
        
        # Try pattern matching first
        for pattern, cron_func in self.frequency_patterns.items():
            match = re.search(pattern, schedule_lower)
            if match:
                base_cron = cron_func(match)
                
                # Check for time specification
                time_spec = self._extract_time_from_text(schedule_lower)
                if time_spec:
                    hour, minute = time_spec
                    parts = base_cron.split()
                    if len(parts) >= 2:
                        parts[0] = str(minute)
                        parts[1] = str(hour)
                    base_cron = ' '.join(parts)
                
                # Check for day specification
                day_spec = self._extract_day_from_text(schedule_lower)
                if day_spec:
                    parts = base_cron.split()
                    if len(parts) >= 5:
                        parts[4] = day_spec
                    base_cron = ' '.join(parts)
                
                return base_cron
        
        # Check for specific day + time patterns
        day_time_pattern = r'every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekdays?|weekends?)\s+(?:at\s+)?(.+)'
        match = re.search(day_time_pattern, schedule_lower)
        if match:
            day_text = match.group(1)
            time_text = match.group(2)
            
            day_spec = self.day_patterns.get(day_text)
            time_spec = self._extract_time_from_text(time_text)
            
            if day_spec and time_spec:
                hour, minute = time_spec
                return f"{minute} {hour} * * {day_spec}"
        
        # Check for daily at specific time
        daily_time_pattern = r'(?:every\s+day|daily)\s+(?:at\s+)?(.+)'
        match = re.search(daily_time_pattern, schedule_lower)
        if match:
            time_text = match.group(1)
            time_spec = self._extract_time_from_text(time_text)
            
            if time_spec:
                hour, minute = time_spec
                return f"{minute} {hour} * * *"
        
        # Fallback
        return "0 9 * * *"


class SimplePromptRewriter:
    """Simplified version of PromptRewriter for testing."""
    
    def __init__(self):
        self.llm = None
        
        self.scheduled_context_patterns = {
            'check': 'Check and report on',
            'remind me': 'Send reminder:',
            'tell me': 'Provide update on',
            'show me': 'Display information about',
            'let me know': 'Notify about',
            'update me': 'Provide status update on',
        }
        
        self.temporal_transforms = {
            'now': 'at this scheduled time',
            'right now': 'at this scheduled time',
            'currently': 'at this scheduled time',
        }
    
    async def rewrite_for_execution(self, original_prompt: str) -> str:
        prompt_lower = original_prompt.lower().strip()
        
        # Apply scheduled context transformations
        for pattern, replacement in self.scheduled_context_patterns.items():
            if prompt_lower.startswith(pattern):
                rest_of_prompt = original_prompt[len(pattern):].strip()
                return f"{replacement} {rest_of_prompt}".strip()
        
        # Apply temporal transformations
        rewritten = original_prompt
        for temporal_ref, replacement in self.temporal_transforms.items():
            rewritten = rewritten.replace(temporal_ref, replacement)
        
        # Add context if it looks like a command without clear action
        simple_commands = ['email', 'status', 'report', 'weather', 'news']
        if prompt_lower in simple_commands:
            return f"Check and provide update on {prompt_lower}"
        
        # If prompt is very short, expand it
        if len(original_prompt.split()) <= 2 and not original_prompt.endswith('?'):
            return f"Provide information and status update on: {original_prompt}"
        
        return rewritten


def run_parser_tests():
    """Run basic parser tests."""
    print("🧪 Testing Schedule Parser...")
    
    parser = SimpleScheduleParser()
    
    # Test cases
    test_cases = [
        ("every day at 9am", "0 9 * * *"),
        ("every monday at 2pm", "0 14 * * 1"),
        ("every 15 minutes", "*/15 * * * *"),
        ("every hour", "0 * * * *"),
        ("daily", "0 0 * * *"),
        ("weekly", "0 0 * * 0"),
        ("every weekday at noon", "0 12 * * 1-5"),
    ]
    
    async def run_tests():
        for schedule_text, expected in test_cases:
            result = await parser.parse_schedule(schedule_text)
            if result == expected:
                print(f"   ✓ '{schedule_text}' → '{result}'")
            else:
                print(f"   ❌ '{schedule_text}' → '{result}' (expected '{expected}')")
    
    asyncio.run(run_tests())


def run_rewriter_tests():
    """Run basic rewriter tests."""
    print("\n🧪 Testing Prompt Rewriter...")
    
    rewriter = SimplePromptRewriter()
    
    test_cases = [
        ("check my email", "Check and report on my email"),
        ("remind me about meeting", "Send reminder: about meeting"),
        ("tell me the weather", "Provide update on the weather"),
        ("email", "Check and provide update on email"),
        ("do this right now", "do this at this scheduled time"),
    ]
    
    async def run_tests():
        for original, expected in test_cases:
            result = await rewriter.rewrite_for_execution(original)
            if result == expected:
                print(f"   ✓ '{original}' → '{result}'")
            else:
                print(f"   ❌ '{original}' → '{result}' (expected '{expected}')")
    
    asyncio.run(run_tests())


def run_time_parsing_tests():
    """Test time parsing functionality."""
    print("\n🧪 Testing Time Parsing...")
    
    parser = SimpleScheduleParser()
    
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
        if result == expected:
            print(f"   ✓ '{time_text}' → {result}")
        else:
            print(f"   ❌ '{time_text}' → {result} (expected {expected})")


if __name__ == "__main__":
    print("🧪 Running MUXI Scheduler NLP Basic Tests...")
    
    try:
        run_parser_tests()
        run_rewriter_tests()
        run_time_parsing_tests()
        
        print("\n🎉 All basic NLP tests completed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()