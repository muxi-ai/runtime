Analyze this transcript to determine if clarification is needed regarding the user most recent request.

=== CONVERSATION TRANSCRIPT ===
{conversation}

=== AVAILABLE CONTEXT ===
{context}

=== SYSTEM CAPABILITIES ===
{capabilities}

=== MCP SERVICES AVAILABLE ===
{mcp_services}


=== INSTRUCTIONS ===
Be {response_style}.

Determine:
1. Is the request clear enough to attempt execution?
2. What mode of interaction does the user want?
3. If clarification needed, what should we ask?
4. Which MCP service (if any) is this request about?

IMPORTANT RULES:
- If the request is clear enough to make an attempt, don't clarify
- If user provides code or specific error, that's usually enough
- For vague requests like "help me" or "fix this", DO clarify
- If we lack the tools/capabilities, don't clarify (fail fast)
- Detect if user wants brainstorming/planning vs direct action

CREDENTIAL HANDLING RULES:
- Mode: {cred_mode}
- If user wants to add credentials/accounts for an MCP service (GitHub, etc):
  * Set needs_clarification=true
  * Set mcp_service to the relevant service (e.g., "github-mcp" for GitHub)
  * question: "{redirect_message}"
- Examples: "add new GitHub account", "I want to add a new GitHub account", "configure GitHub auth"
- For requests that need MCP services but lack credentials, also trigger this flow

MCP SERVICE DETECTION:
- Only set mcp_service if the request clearly needs one of the available MCP services
- Set to null if not relevant or not asking about MCP service

Return JSON:
{{
    "needs_clarification": boolean,
    "reason": "ambiguous|missing_info|no_capability|clear",
    "mode": "direct|brainstorm|planning",
    "question": "clarification question in the specified style or null",
    "confidence": 0.0 to 1.0,
    "mcp_service": "service_name or null"
}}