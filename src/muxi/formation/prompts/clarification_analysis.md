Analyze this transcript to determine if clarification is needed regarding the user most recent request.

=== CONVERSATION TRANSCRIPT ===
{conversation}

=== AVAILABLE CONTEXT ===
{context}

=== SYSTEM CAPABILITIES ===
{capabilities}

=== MCP SERVICES AVAILABLE ===
{mcp_services}

=== AVAILABLE CREDENTIALS ===
{available_credentials}


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

MULTIMODAL CONTENT RULES:
- If user provides documents/images/files WITH explicit action verbs, that's clear - don't clarify
- Explicit actions include: summarize, analyze, list, extract, describe, compare, transcribe, translate, explain
- Examples of CLEAR requests (don't clarify):
  * "Summarize this document" (with file)
  * "List key features in this PDF" (with file)
  * "What's in this image?" (with image)
  * "Transcribe this audio" (with audio)
  * "Extract text from this document" (with file)
  * "Analyze this chart" (with image)
- Only clarify multimodal requests if action is truly ambiguous:
  * "Help me with this file" (no specific action)
  * "Do something with this" (no specific action)
  * "Fix this" (unclear what needs fixing)

CREDENTIAL HANDLING RULES:
- Mode: {cred_mode}
- If user wants to add credentials/accounts for an MCP service:
  * Set needs_clarification=true
  * Set mcp_service to the relevant service
  * question: "{redirect_message}"
- For requests that need MCP services but lack credentials, also trigger this flow

MULTIPLE CREDENTIAL SCENARIOS:
- Check the "AVAILABLE CREDENTIALS" section above to see how many credentials exist for each service
- If a request requires an MCP service but DOES NOT specify which account/credential:
  * If ONLY ONE credential exists for that service → it's CLEAR, set needs_clarification=false
  * If MULTIPLE credentials exist for that service → it's AMBIGUOUS, set needs_clarification=true
  * When ambiguous: Set mcp_service to the service name, question: "Which account would you like to use?"
- If request explicitly names an account (e.g., "my lily account", "use ranaroussi"), it's CLEAR:
  * Set needs_clarification=false regardless of how many credentials exist
- If user asks for help obtaining credentials:
  * Set needs_clarification=true
  * Set mcp_service to the relevant service
  * question: Provide general guidance like "To set up credentials for [service], you'll need to obtain an access token or API key from the service's settings or developer portal, then configure it in your credential manager."

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