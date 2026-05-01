Rewrite this scheduling request into the prompt that will actually execute on schedule. Strip the timing, keep everything else.

Original Request: "{original_prompt}"{context_info}

The user has scheduled a task. When the schedule fires, an agent will receive your output as a fresh user message — with NO knowledge that it was scheduled. Your output must read like a complete, standalone instruction the agent can act on.

WHAT TO REMOVE
Remove ONLY the timing/recurrence words and phrases:
- "every minute", "every 3 minutes", "every hour", "hourly", "daily", "weekly", "monthly"
- "at 9am", "at noon", "on Monday", "on the first of each month"
- "recurring", "scheduled", "regularly", "periodically"

WHAT TO KEEP — CRITICAL
Keep EVERY other word in the request, especially:
- The verb and its object: "drink water", "send the report", "check email"
- The DELIVERY FRAMING: "remind me to ...", "notify me when ...", "send me ...", "tell me ...", "show me ...", "alert me about ..."
- The recipient: "remind ME", "tell US", "notify the team"
- The subject/topic that gives the action meaning

Delivery framing is NOT scheduling — it's the action itself. The agent needs to know it's supposed to send a reminder, deliver a notification, etc. Stripping "remind me to" turns a reminder into a confused statement of fact.

Examples — what to keep, what to drop:

| Original                                              | Correct rewrite                          | Wrong (strips framing)        |
|-------------------------------------------------------|------------------------------------------|-------------------------------|
| remind me to drink water every 3 minutes              | remind me to drink water                 | drink water                   |
| notify me when the build finishes every morning       | notify me when the build finishes        | the build finishes            |
| send me the sales summary every Friday at 5pm         | send me the sales summary                | sales summary                 |
| tell me a dad joke every minute                       | tell me a dad joke                       | dad joke                      |
| check my email every hour                             | check my email                           | email                         |
| generate the monthly report on the first of each month| generate the monthly report              | monthly report                |
| alert me if disk usage exceeds 90% every 5 minutes    | alert me if disk usage exceeds 90%       | disk usage exceeds 90%        |

If the original prompt is already self-contained without scheduling words (e.g., "send the daily standup summary"), return it unchanged.

DO NOT add words that were not in the original ("update", "reminder", "notification") unless they appeared in the user's framing already.

Return ONLY the rewritten action. No quotes, no explanation, no scheduling instructions.
