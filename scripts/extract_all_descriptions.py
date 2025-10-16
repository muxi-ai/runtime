#!/usr/bin/env python3
"""
Extract descriptions from observe() calls with multi-line f-strings.
This handles complex cases that simple regex misses.
"""

import re
import csv
from pathlib import Path

def extract_multiline_description(file_path: str, start_line: int) -> str:
    """Extract description from observe() call, handling multi-line f-strings."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if start_line > len(lines):
            return "LINE_OUT_OF_RANGE"
        
        # Read from start_line onwards (up to 40 lines to capture full call)
        code = ''.join(lines[start_line-1:min(start_line+40, len(lines))])
        
        # Find observability.observe(
        obs_match = re.search(r'observability\.observe\s*\(', code)
        if not obs_match:
            return "NO_OBSERVE_FOUND"
        
        # Extract the full call by counting parens
        start_pos = obs_match.end()
        depth = 1
        pos = start_pos
        
        while pos < len(code) and depth > 0:
            if code[pos] == '(':
                depth += 1
            elif code[pos] == ')':
                depth -= 1
            pos += 1
        
        call_body = code[start_pos:pos-1]
        
        # Look for description= parameter
        # Handle various formats:
        # 1. description="simple string"
        # 2. description=f"f-string"
        # 3. description=( ... multi-line ... )
        
        # Try to find description= with parentheses (multi-line)
        desc_paren = re.search(r'description\s*=\s*\(([^)]+)\)', call_body, re.DOTALL)
        if desc_paren:
            # Extract the content, remove quotes and concatenate f-strings
            desc_content = desc_paren.group(1)
            # Remove f" and " markers, join lines
            cleaned = re.sub(r'f?["\']', '', desc_content)
            cleaned = ' '.join(cleaned.split())
            return f"f-string: {cleaned.strip()}"
        
        # Try simple string
        desc_simple = re.search(r'description\s*=\s*(["\'])(.*?)\1', call_body, re.DOTALL)
        if desc_simple:
            return desc_simple.group(2).strip()
        
        # Try f-string on one line
        desc_fstring = re.search(r'description\s*=\s*f(["\'])(.*?)\1', call_body, re.DOTALL)
        if desc_fstring:
            return f"f-string: {desc_fstring.group(2).strip()}"
        
        return "NO_DESC_PARAM"
        
    except Exception as e:
        return f"ERROR: {str(e)}"


# Main extraction
descriptions = {}

# Read CSV to get all NO DESCRIPTION entries
with open('observability_events_audit.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row['description'] == 'NO DESCRIPTION':
            file_path = row['file']
            line = int(row['line'])
            key = f"{file_path}:{line}"
            
            desc = extract_multiline_description(file_path, line)
            descriptions[key] = desc
            
            if desc not in ['NO_DESC_PARAM', 'NO_OBSERVE_FOUND', 'LINE_OUT_OF_RANGE'] and not desc.startswith('ERROR'):
                print(f"✓ {key}")
                print(f"  → {desc[:100]}...")
            else:
                print(f"✗ {key} - {desc}")

print(f"\n{'='*80}")
print(f"Extracted {len([d for d in descriptions.values() if d.startswith('f-string:')])} descriptions")
print(f"Failed: {len([d for d in descriptions.values() if not d.startswith('f-string:') and d not in ['NO_DESC_PARAM']])}")

# Update CSV
rows = []
updated = 0

with open('observability_events_audit.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row['description'] == 'NO DESCRIPTION':
            key = f"{row['file']}:{row['line']}"
            if key in descriptions and descriptions[key].startswith('f-string:'):
                row['description'] = descriptions[key]
                updated += 1
        rows.append(row)

# Write back
with open('observability_events_audit.csv', 'w', newline='', encoding='utf-8') as f:
    fieldnames = ['event_type', 'level', 'trigger', 'description', 'file', 'line', 'recommendation', 'comment', 'status']
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"\n✅ Updated {updated} descriptions in CSV")
remaining = sum(1 for r in rows if r['description'] == 'NO DESCRIPTION')
print(f"Remaining NO DESCRIPTION: {remaining}")
