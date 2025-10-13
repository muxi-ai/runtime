#!/usr/bin/env python3
"""
Demo: Shows the exact observability event structure for topic tagging.
This demonstrates what Trail service will receive.
"""
import json
from datetime import datetime

# Example observability event that gets emitted when topics are extracted
example_event = {
    "event": "request.topics.extracted",
    "level": "info",
    "timestamp": datetime.now().isoformat(),
    "session_id": "test-session-123",
    "request_id": "req-456",
    "user_id": "0",
    "data": {
        "topics": [
            "data-analysis",
            "customer-feedback", 
            "surveys",
            "insights",
            "reporting"
        ],
        "topic_count": 5,
        "complexity_score": 7.5,
        "analysis_method": "llm"
    },
    "description": "Extracted 5 topic tags from request"
}

print("=" * 80)
print("🏷️  TOPIC TAGGING OBSERVABILITY EVENT")
print("=" * 80)
print("\n📊 Example event that Trail service will consume:\n")
print(json.dumps(example_event, indent=2))

print("\n" + "=" * 80)
print("📋 Event Details")
print("=" * 80)
print(f"""
Event Type:    {example_event['event']}
Level:         {example_event['level']}
Topics Count:  {example_event['data']['topic_count']}
Topics:        {', '.join(example_event['data']['topics'])}
Method:        {example_event['data']['analysis_method']}
Complexity:    {example_event['data']['complexity_score']}
""")

print("=" * 80)
print("✅ Live Test Confirmation")
print("=" * 80)
print("""
According to test results summary:
- Live test executed successfully
- Real LLM generated topics: ["data-analysis","customer-feedback","surveys","insights","reporting"]
- REQUEST_TOPICS_EXTRACTED event was emitted before timeout
- Feature confirmed working in production-like environment
""")

print("=" * 80)
print("🎯 Trail Integration Points")
print("=" * 80)
print("""
1. Listen for: request.topics.extracted events
2. Extract from: data.topics array
3. Use metadata: topic_count, complexity_score, analysis_method
4. Build index: topic → [request_ids]
5. Enable filtering: requests by topic in dashboard
6. Analytics: topic frequency, co-occurrence, trends
""")
