#!/usr/bin/env python3
"""Fix async for loops that expect streaming but get MuxiResponse objects."""

import re
from pathlib import Path

def fix_file(filepath):
    """Fix async for patterns in a test file."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    original = content
    changes = 0
    
    # Pattern 1: response_gen = await overlord.chat(..., use_async=False,)
    # Need to add stream=False and change response_gen to response_obj
    pattern1 = r'(\s+)(response_gen\s*=\s*await\s+(?:overlord|self\.overlord)\.chat\([^)]+use_async=False,)\s*\)'
    
    def replace1(match):
        nonlocal changes
        changes += 1
        indent = match.group(1)
        call = match.group(2)
        return f'{indent}{call.replace("response_gen", "response_obj")}\n{indent}    stream=False,\n{indent})'
    
    content = re.sub(pattern1, replace1, content)
    
    # Pattern 2: async for chunk in response_gen: -> Extract response text
    pattern2 = r'(\s+)# Collect streaming response\s+response = ""\s+async for chunk in (response_gen|response):\s+response \+= chunk'
    
    def replace2(match):
        nonlocal changes
        changes += 1
        indent = match.group(1)
        var_name = match.group(2)
        obj_name = var_name.replace('_gen', '_obj') if '_gen' in var_name else 'response_obj'
        return f'{indent}# Extract response text\n{indent}response = {obj_name}.content if hasattr({obj_name}, \'content\') else str({obj_name})'
    
    content = re.sub(pattern2, replace2, content, flags=re.MULTILINE)
    
    if content != original:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"✓ Fixed {filepath.name} ({changes} changes)")
        return True
    else:
        print(f"- No changes needed for {filepath.name}")
        return False

if __name__ == '__main__':
    test_dir = Path(__file__).parent
    test_files = [
        'test_4b3_mcp_failure_handling.py',
        'test_4c2_update_linear_issue.py',
        'test_4c3_list_linear_issues.py',
        'test_4e1_verify_user_isolation.py',
        'test_4e2_multiple_users_permissions.py',
    ]
    
    total_fixed = 0
    for test_file in test_files:
        filepath = test_dir / test_file
        if filepath.exists():
            if fix_file(filepath):
                total_fixed += 1
        else:
            print(f"✗ File not found: {test_file}")
    
    print(f"\nTotal files fixed: {total_fixed}/{len(test_files)}")
