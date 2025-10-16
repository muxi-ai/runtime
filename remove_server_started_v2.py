#!/usr/bin/env python3
"""
Remove SERVER_STARTED debug trace observe() calls from overlord.py (v2 - improved)

These are misused debug breadcrumbs that should be removed entirely.
"""

import re

def remove_server_started_observes(file_path):
    """Remove all observability.observe() calls with SERVER_STARTED event type."""
    
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    # Find all observe() calls with SERVER_STARTED
    in_observe_block = False
    observe_start = -1
    observe_indent = 0
    lines_to_remove = []
    removed_count = 0
    
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        
        # Check if this line starts an observe block with SERVER_STARTED
        if 'observability.observe(' in line:
            # Look ahead to find SERVER_STARTED
            look_ahead = min(i + 10, len(lines))
            block_text = ''.join(lines[i:look_ahead])
            
            if 'ServerEvents.SERVER_STARTED' in block_text:
                # Found a SERVER_STARTED observe block
                in_observe_block = True
                observe_start = i
                observe_indent = len(line) - len(stripped)
                
                # Also check if there's a debug comment in the line before
                if i > 0:
                    prev_line = lines[i-1].strip()
                    if prev_line.startswith('#') and 'Debug' in prev_line:
                        lines_to_remove.append(i-1)
                
                lines_to_remove.append(i)
        
        # If we're in an observe block, keep adding lines until we find the closing paren
        elif in_observe_block:
            lines_to_remove.append(i)
            
            # Check for closing parenthesis at the same or lesser indent level
            curr_indent = len(line) - len(line.lstrip())
            if stripped.rstrip().endswith(')') and curr_indent <= observe_indent:
                in_observe_block = False
                removed_count += 1
        
        i += 1
    
    # Remove the identified lines (in reverse to preserve indices)
    for line_idx in reversed(lines_to_remove):
        del lines[line_idx]
    
    # Write back
    with open(file_path, 'w') as f:
        f.writelines(lines)
    
    print(f"✓ Removed {removed_count} SERVER_STARTED observe() calls")
    print(f"✓ Removed {len(lines_to_remove)} total lines")
    print(f"✓ Updated {file_path}")
    
    return removed_count

if __name__ == "__main__":
    file_path = "src/muxi/formation/overlord/overlord.py"
    
    print("Removing SERVER_STARTED debug traces from overlord.py (v2)...")
    print("=" * 60)
    
    count = remove_server_started_observes(file_path)
    
    if count > 0:
        print("\n" + "=" * 60)
        print(f"SUCCESS: Removed {count} SERVER_STARTED calls")
        print("\nVerifying syntax...")
        
        # Verify Python syntax
        import subprocess
        result = subprocess.run(
            ["python3", "-m", "py_compile", file_path],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✓ Python syntax is valid")
            print("\nNext steps:")
            print("  1. Review: git diff src/muxi/formation/overlord/overlord.py | less")
            print("  2. Commit: git commit -am 'Remove SERVER_STARTED debug traces'")
        else:
            print("✗ Syntax error detected:")
            print(result.stderr)
            print("\nPlease review and fix manually")
    else:
        print("\nNo SERVER_STARTED calls found")
