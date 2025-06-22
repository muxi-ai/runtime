#!/usr/bin/env python3
"""
Example: MUXI Scheduler with Complex Date Pattern Exclusions

This example demonstrates how to create scheduled jobs with complex
date-based exclusion rules that go beyond simple cron patterns.
"""

# Example job creation with complex date exclusions:

# 1. Monthly report - except last Friday of month (for month-end processing)
job1 = {
    "user_id": "user123",
    "formation_id": "formation456", 
    "title": "Daily Sales Report",
    "original_prompt": "Generate daily sales report and send to team",
    "schedule": "every day at 9am",
    "exclusions": [
        "except weekends",
        "except the last Friday of each month"  # Complex date pattern
    ]
}

# 2. Weekly team check-in - except first Monday (monthly all-hands)
job2 = {
    "user_id": "user123",
    "formation_id": "formation456",
    "title": "Weekly Team Check-in", 
    "original_prompt": "Send team check-in reminder",
    "schedule": "every Monday at 10am",
    "exclusions": [
        "except the first Monday of the month"  # Complex date pattern
    ]
}

# 3. Database backup - except 2 days before month end (heavy processing)
job3 = {
    "user_id": "user123",
    "formation_id": "formation456",
    "title": "Daily Database Backup",
    "original_prompt": "Run database backup and verify integrity",
    "schedule": "every day at 2am",
    "exclusions": [
        "except 2 days before the end of the month"  # Complex date pattern
    ]
}

# 4. Inventory check - only on 3rd Tuesday (quarterly pattern)
job4 = {
    "user_id": "user123", 
    "formation_id": "formation456",
    "title": "Quarterly Inventory Check",
    "original_prompt": "Generate inventory report and check for discrepancies",
    "schedule": "every Tuesday at 3pm",
    "exclusions": [
        "except if not the 3rd Tuesday of the month"  # Complex date pattern
    ]
}

# The scheduler will parse these natural language exclusions and create
# the appropriate complex date rules:

# Expected exclusion rules generated:
exclusion_rules_examples = [
    {
        "type": "complex_date",
        "pattern": "last_friday_of_month",
        "description": "Exclude the last Friday of each month"
    },
    {
        "type": "complex_date", 
        "pattern": "first_monday_of_month",
        "description": "Exclude the first Monday of each month"
    },
    {
        "type": "complex_date",
        "pattern": "last_day_minus:2", 
        "description": "Exclude 2 days before the end of the month"
    },
    {
        "type": "complex_date",
        "pattern": "nth_weekday:3:tuesday",
        "description": "Exclude every 3rd Tuesday of the month"
    }
]

# Multilingual support - the LLM will understand these patterns in any language:
multilingual_examples = [
    "außer am letzten Freitag des Monats",     # German
    "sauf le premier lundi du mois",            # French
    "excepto el tercer martes",                 # Spanish
    "除了每月的最后一个星期五",                    # Chinese
]

# Complex date pattern formats supported:
# - first_DAY_of_month: First occurrence of DAY in month
# - last_DAY_of_month: Last occurrence of DAY in month
# - nth_weekday:N:DAY: Nth occurrence of DAY in month (N=1-5)
# - nth_day:N: Nth day of month (N=1-31)
# - last_day_minus:N: N days before end of month (N=0-30)

print("MUXI Scheduler Complex Date Exclusion Examples")
print("=" * 50)
print("\nSupported complex date patterns:")
print("- Last Friday of month")
print("- First Monday of month") 
print("- 3rd Tuesday of month")
print("- 15th day of month")
print("- 2 days before month end")
print("\nThese patterns work alongside regular cron exclusions!")
print("\nThe LLM understands these patterns in multiple languages.")