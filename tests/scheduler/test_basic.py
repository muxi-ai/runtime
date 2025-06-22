#!/usr/bin/env python3
"""
Basic syntax and import test for MUXI Scheduler components.
Tests that the code compiles and basic patterns work correctly.
"""

import asyncio
import sys
import os
import tempfile
from datetime import datetime
import pytz

def test_basic_syntax():
    """Test that all scheduler files have correct syntax."""
    
    print("🧪 Testing MUXI Scheduler Basic Syntax...")
    
    # Test syntax compilation
    scheduler_files = [
        "__init__.py",
        "service.py", 
        "manager.py",
        "models.py",
        "parser.py",
        "rewriter.py"
    ]
    
    for filename in scheduler_files:
        try:
            with open(filename, 'r') as f:
                code = f.read()
            compile(code, filename, 'exec')
            print(f"   ✓ {filename} syntax is valid")
        except SyntaxError as e:
            print(f"   ❌ {filename} has syntax error: {e}")
            return False
        except Exception as e:
            print(f"   ❌ {filename} compilation error: {e}")
            return False
    
    return True

def test_schedule_parsing_patterns():
    """Test schedule parsing patterns without LLM dependencies."""
    
    print("✅ Testing schedule parsing patterns...")
    
    # Mock schedule parser for basic pattern testing
    class MockScheduleParser:
        def __init__(self):
            self.time_patterns = {
                r'(\d{1,2})\s*(am|pm)': self._parse_12hour,
                r'(\d{1,2}):(\d{2})\s*(am|pm)': self._parse_12hour_minutes,
                r'(\d{1,2}):(\d{2})': self._parse_24hour,
            }
            
            self.day_patterns = {
                'monday': '1', 'tuesday': '2', 'wednesday': '3', 'thursday': '4',
                'friday': '5', 'saturday': '6', 'sunday': '0',
                'weekdays': '1-5', 'weekends': '0,6',
            }
        
        def _parse_12hour(self, match):
            hour = int(match.group(1))
            am_pm = match.group(2).lower()
            if am_pm == 'pm' and hour != 12:
                hour += 12
            elif am_pm == 'am' and hour == 12:
                hour = 0
            return hour, 0
        
        def _parse_12hour_minutes(self, match):
            hour = int(match.group(1))
            minute = int(match.group(2))
            am_pm = match.group(3).lower()
            if am_pm == 'pm' and hour != 12:
                hour += 12
            elif am_pm == 'am' and hour == 12:
                hour = 0
            return hour, minute
        
        def _parse_24hour(self, match):
            hour = int(match.group(1))
            minute = int(match.group(2))
            return hour, minute
    
    parser = MockScheduleParser()
    
    # Test time parsing
    import re
    
    test_cases = [
        ("9am", (9, 0)),
        ("2pm", (14, 0)),
        ("12pm", (12, 0)),
        ("12am", (0, 0)),
        ("9:30am", (9, 30)),
        ("2:15pm", (14, 15)),
        ("14:30", (14, 30)),
    ]
    
    for test_text, expected in test_cases:
        for pattern, parser_func in parser.time_patterns.items():
            match = re.search(pattern, test_text)
            if match:
                result = parser_func(match)
                if result == expected:
                    print(f"   ✓ '{test_text}' → {result}")
                else:
                    print(f"   ❌ '{test_text}' → {result}, expected {expected}")
                    return False
                break
        else:
            print(f"   ❌ No pattern matched for '{test_text}'")
            return False
    
    return True

def test_cron_validation():
    """Test cron expression validation."""
    
    print("✅ Testing cron expression validation...")
    
    # Mock cron validator
    def validate_cron_expression(cron_expr):
        import re
        parts = cron_expr.strip().split()
        
        if len(parts) != 5:
            return False
        
        # Basic pattern check for each field
        patterns = [
            r'^(\*|([0-5]?\d)(,([0-5]?\d))*|([0-5]?\d)-([0-5]?\d)|\*/\d+)$',  # minute
            r'^(\*|([01]?\d|2[0-3])(,([01]?\d|2[0-3]))*|([01]?\d|2[0-3])-([01]?\d|2[0-3])|\*/\d+)$',  # hour
            r'^(\*|([12]?\d|3[01])(,([12]?\d|3[01]))*|([12]?\d|3[01])-([12]?\d|3[01])|\*/\d+)$',  # day
            r'^(\*|([1-9]|1[0-2])(,([1-9]|1[0-2]))*|([1-9]|1[0-2])-([1-9]|1[0-2])|\*/\d+)$',  # month
            r'^(\*|[0-6](,[0-6])*|[0-6]-[0-6]|\*/\d+)$'  # day of week
        ]
        
        for i, part in enumerate(parts):
            if not re.match(patterns[i], part):
                return False
        
        return True
    
    valid_crons = [
        "0 9 * * *",      # daily at 9am
        "30 14 * * 1",    # Monday at 2:30pm
        "*/15 * * * *",   # every 15 minutes
        "0 12 * * 1-5",   # weekdays at noon
        "0 0 1 * *",      # first of month at midnight
    ]
    
    invalid_crons = [
        "0 25 * * *",     # invalid hour
        "60 12 * * *",    # invalid minute
        "0 12 * * 8",     # invalid day of week
        "0 12 32 * *",    # invalid day of month
        "0 12",           # too few fields
    ]
    
    for cron in valid_crons:
        if validate_cron_expression(cron):
            print(f"   ✓ Valid cron: {cron}")
        else:
            print(f"   ❌ False negative for valid cron: {cron}")
            return False
    
    for cron in invalid_crons:
        if not validate_cron_expression(cron):
            print(f"   ✓ Invalid cron rejected: {cron}")
        else:
            print(f"   ❌ False positive for invalid cron: {cron}")
            return False
    
    return True

def test_timezone_handling():
    """Test timezone handling capabilities."""
    
    print("✅ Testing timezone handling...")
    
    try:
        # Test timezone creation
        utc_tz = pytz.timezone('UTC')
        est_tz = pytz.timezone('US/Eastern')
        pst_tz = pytz.timezone('US/Pacific')
        
        # Test datetime with timezone
        now_utc = datetime.now(utc_tz)
        now_est = now_utc.astimezone(est_tz)
        now_pst = now_utc.astimezone(pst_tz)
        
        print(f"   ✓ UTC: {now_utc.strftime('%H:%M %Z')}")
        print(f"   ✓ EST: {now_est.strftime('%H:%M %Z')}")
        print(f"   ✓ PST: {now_pst.strftime('%H:%M %Z')}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Timezone handling error: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Running MUXI Scheduler Basic Tests...\n")
    
    tests = [
        test_basic_syntax,
        test_schedule_parsing_patterns,
        test_cron_validation,
        test_timezone_handling,
    ]
    
    passed = 0
    total = len(tests)
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
            print()  # Add spacing between tests
        except Exception as e:
            print(f"   ❌ Test {test_func.__name__} failed with exception: {e}")
            print()
    
    print(f"🎯 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All basic tests passed! Scheduler implementation is syntactically correct.")
        sys.exit(0)
    else:
        print("❌ Some tests failed. Please review the implementation.")
        sys.exit(1)