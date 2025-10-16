#!/usr/bin/env python3
"""
Remove SERVER_STARTED debug trace observe() calls from overlord.py

These are misused debug breadcrumbs that should be removed entirely.
"""

import re
import sys

def remove_server_started_observes(file_path):
    """Remove all observability.observe() calls with SERVER_STARTED event type."""
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Pattern to match observe() calls with SERVER_STARTED
    # Handles both single-line and multi-line observe calls
    pattern = r'observability\.observe\(\s*event_type=observability\.ServerEvents\.SERVER_STARTED,.*?\)'
    
    # Count matches before removal
    matches = list(re.finditer(pattern, content, re.DOTALL))
    print(f"Found {len(matches)} SERVER_STARTED observe() calls")
    
    if not matches:
        print("No SERVER_STARTED calls found!")
        return False
    
    # Show first few examples
    print("\nFirst 3 examples:")
    for i, match in enumerate(matches[:3]):
        snippet = match.group(0)[:100] + "..." if len(match.group(0)) > 100 else match.group(0)
        print(f"  {i+1}. Line ~{content[:match.start()].count(chr(10)) + 1}: {snippet}")
    
    # Remove all matches
    new_content = re.sub(pattern, '', content, flags=re.DOTALL)
    
    # Also remove any standalone comments that were before these calls
    # Pattern: lines with just "# Debug:" or "# Debug logging" before whitespace
    new_content = re.sub(r'\n\s*#\s*Debug:?\s*(?:Entry point|logging)?\s*\n\s*\n', '\n\n', new_content)
    
    # Clean up any double blank lines created
    new_content = re.sub(r'\n\n\n+', '\n\n', new_content)
    
    # Write back
    with open(file_path, 'w') as f:
        f.write(new_content)
    
    print(f"\n✓ Removed {len(matches)} SERVER_STARTED observe() calls")
    print(f"✓ Updated {file_path}")
    
    return True

if __name__ == "__main__":
    file_path = "src/muxi/formation/overlord/overlord.py"
    
    print("Removing SERVER_STARTED debug traces from overlord.py...")
    print("=" * 60)
    
    if remove_server_started_observes(file_path):
        print("\n" + "=" * 60)
        print("SUCCESS: All SERVER_STARTED calls removed")
        print("\nNext steps:")
        print("  1. Review the changes: git diff src/muxi/formation/overlord/overlord.py")
        print("  2. Run tests to ensure nothing broke")
        print("  3. Commit: git commit -am 'Remove SERVER_STARTED debug traces'")
    else:
        print("\nERROR: Failed to remove SERVER_STARTED calls")
        sys.exit(1)
