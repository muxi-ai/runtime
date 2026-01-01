#!/usr/bin/env python3
"""
Test A2A response formatting to ensure proper formatting instead of raw dicts
"""

import json


def test_a2a_response_formatting():
    """Test that A2A responses are properly formatted"""

    # Simulate what happens in the current code
    # This is what we're getting from tool results
    tool_result = {
        'content': {
            'meta': None,
            'content': [
                {
                    'type': 'text',
                    'text': '{\n  "usage_percent": 61.1,\n  "core_count": 10,\n  "logical_count": 10,\n  "frequency": "not_available"\n}',  # noqa: E501
                    'annotations': None,
                    'meta': None
                }
            ],
            'structuredContent': None,
            'isError': False
        },
        'isError': False,
        'links': [],
        '_meta': {},
        'type': 'legacy'
    }

    # Current behavior - converts to string representation
    current_output = str(tool_result)
    print("Current output (raw dict as string):")
    print(current_output)
    print("\n" + "="*60 + "\n")

    # Desired behavior - extract meaningful content
    def format_tool_result(result):
        """Extract and format tool result content properly"""
        if isinstance(result, dict):
            # Check if it has the expected structure
            if 'content' in result and isinstance(result['content'], dict):
                content_obj = result['content']
                if 'content' in content_obj and isinstance(content_obj['content'], list):
                    # Extract text from content array
                    text_parts = []
                    for item in content_obj['content']:
                        if isinstance(item, dict) and item.get('type') == 'text':
                            text = item.get('text', '')
                            # Try to parse as JSON for pretty formatting
                            try:
                                parsed = json.loads(text)
                                text_parts.append(json.dumps(parsed, indent=2))
                            except Exception:
                                text_parts.append(text)
                    if text_parts:
                        return '\n'.join(text_parts)

            # Fallback to JSON formatting
            try:
                return json.dumps(result, indent=2)
            except Exception:
                return str(result)

        return str(result)

    # Proper formatting
    formatted_output = format_tool_result(tool_result)
    print("Desired output (properly formatted):")
    print(formatted_output)
    print("\n" + "="*60 + "\n")

    # Test with multiple tool results
    cpu_info = tool_result
    memory_info = {
        'content': {
            'content': [
                {
                    'type': 'text',
                    'text': '{\n  "virtual": {\n    "total": 34359738368,\n    "available": 7282622464,\n    "percent": 78.8\n  }\n}'  # noqa: E501
                }
            ]
        },
        'type': 'legacy'
    }

    # How it should be formatted in an A2A response
    print("Example formatted A2A response:")
    print("System Information Report:")
    print("\nCPU Information:")
    print(format_tool_result(cpu_info))
    print("\nMemory Information:")
    print(format_tool_result(memory_info))

    # Verify formatting improves readability
    assert "{'content'" not in format_tool_result(cpu_info)
    assert "usage_percent" in format_tool_result(cpu_info)
    print("\n✓ Test passed: Tool results are properly formatted")


if __name__ == "__main__":
    test_a2a_response_formatting()
