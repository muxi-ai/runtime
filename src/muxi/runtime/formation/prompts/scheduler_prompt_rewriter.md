Extract and rewrite the core action from this scheduling request, removing all scheduling/timing instructions.

Original Request: "{original_prompt}"{context_info}

IMPORTANT: The user has requested a scheduled task. Strip away ALL scheduling patterns
(like "every minute", "daily at", "every hour", etc.) and return ONLY the action to be performed.

Guidelines:
1. Remove all scheduling/timing words (every, daily, hourly, minute, at, recurring, etc.)
2. Keep ONLY the core action/task to be executed
3. Make it self-contained and clear
4. If the request is just an action with timing (e.g., "check my email every minute"), return just the action (e.g., "check my email")
5. Do NOT add words like "update", "reminder", or "notification" unless they were in the original action

Examples:
- "check my email every hour" → "check my email"
- "tell me a dad joke every minute" → "tell me a dad joke"
- "send weather report daily at 9am" → "send weather report"
- "remind me about the meeting every Monday" → "remind me about the meeting"
- "generate sales report on the first of each month" → "generate sales report"

Return only the extracted action, no scheduling instructions, no explanation.