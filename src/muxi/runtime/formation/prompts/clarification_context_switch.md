We're in a clarification dialog about: {original_request}

We asked: "{last_question}"
The user responded: "{response}"

Determine if the user is:
1. Answering our specific question (even if briefly)
2. Asking for something completely different/unrelated

Examples of context switches:
- We ask "Which account?" → User says "tell me a joke"
- We ask "What language?" → User says "what's the weather?"
- We ask "Which file?" → User says "create a new project"

Examples of NOT context switches (these ARE answers):
- We ask "What is the second source?" → User says "REST API endpoint"
- We ask "Which account?" → User says "the first one"
- We ask "What language?" → User says "Python"
- We ask "Which file?" → User says "never mind"

IMPORTANT: Short answers like "REST API endpoint" or "PostgreSQL database" are
typically ANSWERS to our question, not context switches.

Return "answering" if related to our question, "different" if unrelated.