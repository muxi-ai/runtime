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
- **Simple greetings and pleasantries NEVER need clarification** (e.g., "hello", "hi", "good morning", "how are you", etc. in any language)
- If the request is clear enough to make an attempt, don't clarify
- If user provides code or specific error, that's usually enough
- For vague requests like "help me" or "fix this", DO clarify
- If we lack the tools/capabilities, don't clarify (fail fast)
- Detect if user wants brainstorming/planning vs direct action

CONVERSATION CONTEXT INFERENCE RULES:
- **CRITICAL**: Use the conversation transcript above to infer intent for follow-up questions
- If the user's message references or continues a previous topic, infer their intent from context
- Examples of follow-up questions that should NOT need clarification:
  * Previous: "What's the capital of France?" → Follow-up: "What about Germany?" → Infer: asking about Germany's capital
  * Previous: "How much is a Tesla Model 3?" → Follow-up: "And the Model Y?" → Infer: asking about Model Y's price
  * Previous: "List my repositories" → Follow-up: "Delete the first one" → Infer: delete the first repository listed
  * Previous: "Show me the weather in Paris" → Follow-up: "And tomorrow?" → Infer: weather in Paris tomorrow
- Pattern: If user says "what about X?", "and X?", "how about X?", "the same for X", look at previous question to understand the pattern
- If context makes the intent clear, set needs_clarification=false even if the message alone would be ambiguous
- Only ask for clarification if the intent remains truly unclear even WITH the conversation context

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
- **IMPORTANT**: If request explicitly names an account that matches an available credential, it's CLEAR:
  * Set needs_clarification=false regardless of how many credentials exist
  * Examples of explicit account naming:
    - "my lily account" → matches "lily automaze" credential
    - "use ranaroussi" → matches "ranaroussi" credential
    - "in the ranaroussi account" → matches "ranaroussi" credential
    - "lily's repositories" → matches "lily automaze" credential
    - "ranaroussi account" → matches "ranaroussi" credential
  * Match account names case-insensitively and allow partial matches
  * If you find ANY part of an available account name in the request, treat it as explicit naming
- If user asks for help obtaining credentials:
  * IMPORTANT: Detect help requests like "I don't know how", "how do I get", "help me", "can you help", "what is", "where do I"
  * Look at conversation context - if system just asked for credentials and user seems confused, treat as help request
  * Set needs_clarification=true
  * Set reason="help_request"
  * Set mode="direct"
  * Set mcp_service to the relevant service
  * question: Provide detailed step-by-step guidance for obtaining credentials for that specific service

MCP SERVICE DETECTION:
- Analyze the request to determine which MCP service (if any) would be needed to fulfill it
- Match request intent to available MCP service capabilities listed in "MCP SERVICES AVAILABLE"
- Examples:
  * "list my repositories" → likely needs github-mcp (if available) 
  * "create an issue" → could be github-mcp or linear-mcp (check which is available)
  * "search the web" → needs web-search-mcp
- IMPORTANT: If a request requires a service type but that service is NOT in the available list, set needs_clarification=false and let the agent handle it (fail fast)
- Set mcp_service to the detected service id (e.g., "github", "linear") or null if not relevant

Return JSON:
{{
    "needs_clarification": boolean,
    "reason": "ambiguous|missing_info|no_capability|clear",
    "mode": "direct|brainstorm|planning",
    "question": "clarification question in the specified style or null",
    "confidence": 0.0 to 1.0,
    "mcp_service": "service_name or null"
}}