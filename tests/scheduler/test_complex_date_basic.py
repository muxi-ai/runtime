#!/usr/bin/env python3
"""
Basic test for complex date pattern functionality without full MUXI dependencies.
"""

from datetime import datetime


def test_nth_weekday_calculation():
    """Test nth weekday of month calculation."""
    
    def is_nth_weekday_of_month(dt, n, weekday_name):
        """Check if date is the Nth occurrence of a weekday in the month."""
        weekday_map = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        
        target_weekday = weekday_map.get(weekday_name.lower())
        if target_weekday is None:
            return False
            
        # Check if current date is the target weekday
        if dt.weekday() != target_weekday:
            return False
            
        # Calculate which occurrence this is
        occurrence = (dt.day - 1) // 7 + 1
        return occurrence == n
    
    # Test cases
    test_cases = [
        # First Monday of January 2024 is Jan 1
        (datetime(2024, 1, 1), 1, "monday", True),
        (datetime(2024, 1, 8), 1, "monday", False),  # Second Monday
        
        # Third Tuesday of January 2024 is Jan 16
        (datetime(2024, 1, 16), 3, "tuesday", True),
        (datetime(2024, 1, 9), 3, "tuesday", False),  # Second Tuesday
        
        # Fourth Friday of January 2024 is Jan 26
        (datetime(2024, 1, 26), 4, "friday", True),
        (datetime(2024, 1, 19), 4, "friday", False),  # Third Friday
    ]
    
    print("Testing nth weekday calculations...")
    for dt, n, weekday, expected in test_cases:
        result = is_nth_weekday_of_month(dt, n, weekday)
        status = "✓" if result == expected else "✗"
        print(f"   {status} {dt.date()} is {n}th {weekday}: {result} (expected {expected})")


def test_last_weekday_calculation():
    """Test last weekday of month calculation."""
    
    def is_last_weekday_of_month(dt, weekday_name):
        """Check if date is the last occurrence of a weekday in the month."""
        from datetime import timedelta
        
        weekday_map = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }
        
        target_weekday = weekday_map.get(weekday_name.lower())
        if target_weekday is None:
            return False
            
        # Check if current date is the target weekday
        if dt.weekday() != target_weekday:
            return False
            
        # Check if adding 7 days would be in the next month
        next_week = dt + timedelta(days=7)
        return next_week.month != dt.month
    
    test_cases = [
        # Last Friday of January 2024 is Jan 26
        (datetime(2024, 1, 26), "friday", True),
        (datetime(2024, 1, 19), "friday", False),  # Not last
        
        # Last Monday of January 2024 is Jan 29
        (datetime(2024, 1, 29), "monday", True),
        (datetime(2024, 1, 22), "monday", False),  # Not last
        
        # Last Sunday of February 2024 is Feb 25
        (datetime(2024, 2, 25), "sunday", True),
        (datetime(2024, 2, 18), "sunday", False),  # Not last
    ]
    
    print("\nTesting last weekday calculations...")
    for dt, weekday, expected in test_cases:
        result = is_last_weekday_of_month(dt, weekday)
        status = "✓" if result == expected else "✗"
        print(f"   {status} {dt.date()} is last {weekday}: {result} (expected {expected})")


def test_days_before_month_end():
    """Test N days before month end calculation."""
    
    def is_n_days_before_month_end(dt, n):
        """Check if date is N days before the end of the month."""
        from datetime import datetime, timedelta
        
        # Get last day of current month
        if dt.month == 12:
            last_day = datetime(dt.year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = datetime(dt.year, dt.month + 1, 1) - timedelta(days=1)
            
        # Check if current date is N days before last day
        target_date = last_day - timedelta(days=n)
        return dt.date() == target_date.date()
    
    test_cases = [
        # 2 days before end of January 2024 (31st) is Jan 29
        (datetime(2024, 1, 29), 2, True),
        (datetime(2024, 1, 30), 2, False),
        
        # 1 day before end of February 2024 (29th - leap year) is Feb 28
        (datetime(2024, 2, 28), 1, True),
        (datetime(2024, 2, 27), 1, False),
        
        # 0 days before end (last day)
        (datetime(2024, 1, 31), 0, True),
        (datetime(2024, 2, 29), 0, True),  # Leap year
    ]
    
    print("\nTesting days before month end calculations...")
    for dt, days_before, expected in test_cases:
        result = is_n_days_before_month_end(dt, days_before)
        status = "✓" if result == expected else "✗"
        print(f"   {status} {dt.date()} is {days_before} days before end: {result} (expected {expected})")


def test_pattern_validation():
    """Test complex date pattern validation."""
    import re
    
    def validate_complex_date_pattern(pattern):
        """Validate complex date pattern format."""
        valid_patterns = [
            r'^first_\w+_of_month$',
            r'^last_\w+_of_month$',
            r'^nth_weekday:\d+:\w+$',
            r'^nth_day:\d+$',
            r'^last_day_minus:\d+$',
        ]
        
        pattern_lower = pattern.lower()
        for valid_pattern in valid_patterns:
            if re.match(valid_pattern, pattern_lower):
                # Additional validation for nth_weekday
                if pattern_lower.startswith('nth_weekday:'):
                    parts = pattern_lower.split(':')
                    if len(parts) == 3:
                        try:
                            n = int(parts[1])
                            if 1 <= n <= 5:  # Valid week number
                                weekday = parts[2]
                                if weekday in ['monday', 'tuesday', 'wednesday', 'thursday', 
                                             'friday', 'saturday', 'sunday']:
                                    return True
                        except ValueError:
                            pass
                    return False
                return True
        
        return False
    
    valid_patterns = [
        "first_monday_of_month",
        "last_friday_of_month",
        "nth_weekday:3:tuesday",
        "nth_day:15",
        "last_day_minus:2",
    ]
    
    invalid_patterns = [
        "random_pattern",
        "nth_weekday:6:monday",  # 6th occurrence invalid
        "nth_weekday:3:invalidday",
        "last_invalidday_of_month",
        "nth_day:abc",
    ]
    
    print("\nTesting pattern validation...")
    
    print("  Valid patterns:")
    for pattern in valid_patterns:
        result = validate_complex_date_pattern(pattern)
        status = "✓" if result else "✗"
        print(f"   {status} '{pattern}': {result}")
    
    print("  Invalid patterns:")
    for pattern in invalid_patterns:
        result = validate_complex_date_pattern(pattern)
        status = "✓" if not result else "✗"
        print(f"   {status} '{pattern}': {result} (should be False)")


if __name__ == "__main__":
    print("🧪 Running Complex Date Pattern Basic Tests...\n")
    
    try:
        test_nth_weekday_calculation()
        test_last_weekday_calculation()
        test_days_before_month_end()
        test_pattern_validation()
        
        print("\n🎉 All complex date pattern tests completed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()