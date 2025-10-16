#!/usr/bin/env python3
"""
Script to remove misused SERVER_STARTED debug trace observe() calls from overlord.py.
These are debug breadcrumbs that misuse ServerEvents.SERVER_STARTED.
"""

import re

# Line numbers where SERVER_STARTED should be removed (0-indexed will be line-1)
LINES_TO_REMOVE = [
    2579, 2622, 5462, 5919, 5939, 5964, 5981, 5998, 6017,
    6460, 6477, 6683, 6727, 6744, 6842,
    7581, 7599, 7644, 7654, 7668, 7685, 7695, 7712, 7731,
    7801, 7813, 7824, 7832, 7842, 7873, 7896,
    7990, 8050, 8090, 8127
]

def remove_observe_calls():
    file_path = 'src/muxi/formation/overlord/overlord.py'
    
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    removed_count = 0
    lines_to_skip = set()
    
    # For each target line, find the complete observe() call and mark for removal
    for line_num in LINES_TO_REMOVE:
        idx = line_num - 1  # Convert to 0-indexed
        
        # Find the start of the observe() call (look backwards for "observability.observe(")
        start_idx = idx
        while start_idx > 0:
            if 'observability.observe(' in lines[start_idx]:
                break
            start_idx -= 1
        
        # Find the end (matching closing parenthesis)
        end_idx = idx
        paren_count = 0
        found_start = False
        
        for i in range(start_idx, min(start_idx + 20, len(lines))):
            line = lines[i]
            if 'observability.observe(' in line:
                found_start = True
            if found_start:
                paren_count += line.count('(') - line.count(')')
                if paren_count == 0 and ')' in line:
                    end_idx = i
                    break
        
        # Mark all lines in this observe() call for removal
        for i in range(start_idx, end_idx + 1):
            lines_to_skip.add(i)
        
        removed_count += 1
    
    # Write back, skipping marked lines
    new_lines = [line for i, line in enumerate(lines) if i not in lines_to_skip]
    
    with open(file_path, 'w') as f:
        f.writelines(new_lines)
    
    print(f"Removed {removed_count} SERVER_STARTED debug trace observe() calls")
    print(f"Total lines removed: {len(lines_to_skip)}")
    print(f"File length: {len(lines)} → {len(new_lines)}")

if __name__ == '__main__':
    remove_observe_calls()
