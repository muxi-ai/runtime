IMPORTANT: You can ONLY mark "can_i_do_this": true for tools that are EXACTLY in the available tools list above!
If a tool is NOT in the list above, you MUST set "can_i_do_this": false, even if you think you should have it!

Analyze what needs to be done. For each step, determine:
1. The specific action needed
2. The exact tool from your available list (or mark as unavailable)
3. Whether YOU can do it (true) or need to delegate (false)

KEY INSIGHT: Look at the semantic meaning of both the request and your tools:
- If the request mentions creating something in a named system (Linear, Figma, Salesforce, etc.),
  you need a tool that explicitly mentions that system's name
- Generic file/data tools (write_file, read_file) work ONLY with local filesystem
- A tool's name indicates what it can do - trust the naming

For each step, ask: "Does my tool name indicate it can reach the target mentioned in the request?"
If no, mark can_i_do_this as false for delegation.

IMPORTANT: For each step you can do yourself, you MUST include appropriate parameters:
- Look at the tool name and the user's request to determine what parameters are needed
- For system info tools: use parameters like {"info_type": "cpu"} or {"info_type": "memory"} 
- For file operations: include file paths and content as needed
- For API calls: include required fields like title, description, etc.
- If you're unsure about parameters, use common sense based on the tool name and request

You MUST respond with ONLY a valid JSON object. Use EXACT tool names from the available tools list above:
{{
    "steps": [
        {{
            "step_number": 1,
            "action": "describe what this step does",
            "capability_needed": "what type of capability",
            "tool_name": "EXACT_TOOL_NAME_FROM_AVAILABLE_LIST",
            "can_i_do_this": true,
            "data_needed": "none or previous step data",
            "output_placeholder": "{{DESCRIPTIVE_NAME}}"
        }},
        {{
            "step_number": 2,
            "action": "describe what this step does",
            "capability_needed": "what type of capability",
            "tool_name": "EXACT_TOOL_NAME_FROM_AVAILABLE_LIST",
            "can_i_do_this": false,
            "data_needed": "data from previous steps",
            "delegation_prompt": (
                "Clear instructions for the delegated agent, "
                "with {{PLACEHOLDER}} for data from previous steps"
            )
        }}
    ],
    "my_steps": [
        {{
            "action": "steps I can do myself",
            "tool_name": "EXACT_TOOL_NAME_FROM_LIST",
            "parameters": {{"param_name": "param_value"}},
            "output_placeholder": "{{RESULT_NAME}}"
        }}
    ],
    "delegate_steps": [
        {{
            "action": "steps I need to delegate",
            "capability_needed": "type of capability needed",
            "delegation_prompt": "Instructions with {{PLACEHOLDERS}} for data from my_steps"
        }}
    ],
    "data_flow": "Description of how data flows between steps"
}}
