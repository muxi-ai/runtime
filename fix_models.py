#!/usr/bin/env python3
"""
Fix all formation files that use the non-existent gpt-5-nano model.
"""

import os
from pathlib import Path

def fix_model_in_file(filepath):
    """Replace gpt-5-nano with gpt-4o-mini in a file."""
    with open(filepath, 'r') as f:
        content = f.read()

    if 'gpt-5-nano' in content:
        updated = content.replace('openai/gpt-5-nano', 'openai/gpt-4o-mini')
        with open(filepath, 'w') as f:
            f.write(updated)
        return True
    return False

def main():
    tests_dir = Path('tests/e2e')
    fixed_count = 0

    # Find all yaml files
    for yaml_file in tests_dir.rglob('*.yaml'):
        if fix_model_in_file(yaml_file):
            print(f"✅ Fixed: {yaml_file}")
            fixed_count += 1

    print(f"\n📊 Total files fixed: {fixed_count}")

if __name__ == "__main__":
    main()