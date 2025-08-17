#!/usr/bin/env python3
"""Quick check all classes for usage"""

import re
from pathlib import Path

def check_all_classes():
    # Read the file
    with open('dead-code/all_classes.md', 'r') as f:
        lines = f.readlines()
    
    updated_lines = []
    dead_count = 0
    used_count = 0
    
    for line in lines:
        if line.startswith('#') or not line.strip():
            updated_lines.append(line)
            continue
            
        # Parse line
        match = re.match(r'^[✅❌-]\s+(\w+)\s+-\s+(.+)$', line.strip())
        if match:
            class_name = match.group(1)
            file_path = match.group(2)
            
            # Simple check: grep for the class name
            count = 0
            try:
                for py_file in Path('src/muxi').rglob('*.py'):
                    with open(py_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # Count whole word matches
                        pattern = r'\b' + re.escape(class_name) + r'\b'
                        matches = re.findall(pattern, content)
                        count += len(matches)
            except Exception:
                pass
            
            if count <= 1:
                updated_lines.append(f"❌ {class_name} - {file_path}\n")
                dead_count += 1
                print(f"❌ {class_name} - DEAD ({count} occurrence)")
            else:
                updated_lines.append(f"✅ {class_name} - {file_path}\n")
                used_count += 1
                print(f"✅ {class_name} - USED ({count} occurrences)")
        else:
            updated_lines.append(line)
    
    # Write back
    with open('dead-code/all_classes.md', 'w') as f:
        f.writelines(updated_lines)
    
    print(f"\n{'='*60}")
    print(f"SUMMARY:")
    print(f"Dead classes: {dead_count}")
    print(f"Used classes: {used_count}")
    print(f"Total: {dead_count + used_count}")

if __name__ == "__main__":
    check_all_classes()