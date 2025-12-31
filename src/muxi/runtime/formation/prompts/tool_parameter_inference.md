Based on the user's request and tool requirements, determine the appropriate parameter values.

User Request: {user_request}
Tool Name: {tool_name}
Action Description: {action_description}

Required Parameters:
{parameters_section}

Analyze the user's request and provide appropriate parameter values.
Respond with ONLY a valid JSON object containing the parameter values.
Example: {{"param1": "value1", "param2": 123}}

If you cannot determine a value from context:
- For enums: use the first available option
- For booleans: use false (safer default)
- For strings: use an empty string
- For numbers: use 0