#!/usr/bin/env python3
"""
Chunk 1 Detailed Event Review
Systematically reviews every problematic event in chunk 1 with code context.
"""

import csv
import os
import re
from pathlib import Path

BASE_DIR = Path("/Users/ran/Projects/muxi/code/runtime")

def read_code_context(file_path, line_num, context_lines=10):
    """Read code context around a specific line."""
    full_path = BASE_DIR / file_path
    
    if not full_path.exists():
        return None
    
    try:
        with open(full_path, 'r') as f:
            all_lines = f.readlines()
        
        line_idx = int(line_num) - 1
        start = max(0, line_idx - context_lines)
        end = min(len(all_lines), line_idx + context_lines + 1)
        
        context = {
            'start_line': start + 1,
            'end_line': end,
            'lines': all_lines[start:end],
            'target_line_idx': line_idx - start
        }
        return context
    except:
        return None

def format_code_context(context):
    """Format code context for display."""
    if not context:
        return "  [Could not read file]"
    
    lines = []
    for i, code_line in enumerate(context['lines']):
        line_num = context['start_line'] + i
        marker = ">>> " if i == context['target_line_idx'] else "    "
        lines.append(f"{marker}{line_num:4d}: {code_line.rstrip()}")
    
    return "\n".join(lines)

def analyze_event(event_dict):
    """Analyze a single event."""
    analysis = {
        'event': event_dict,
        'code_context': read_code_context(event_dict['file'], event_dict['line']),
    }
    
    # Categorize the problem
    rec = event_dict['recommendation']
    
    if 'MISSING DESCRIPTION' in rec:
        analysis['issue_category'] = 'MISSING_DESCRIPTION'
    elif 'REVIEW - DEBUG' in rec:
        analysis['issue_category'] = 'REVIEW_DEBUG_GRANULAR'
    elif 'ANTI-PATTERN' in rec:
        analysis['issue_category'] = 'ANTI_PATTERN'
    elif 'MISNOMER' in rec:
        analysis['issue_category'] = 'MISNOMER'
    elif 'REPLACE' in rec:
        analysis['issue_category'] = 'REPLACE_GENERIC'
    elif 'REMOVE' in rec:
        analysis['issue_category'] = 'REMOVE'
    elif 'REVIEW' in rec:
        analysis['issue_category'] = 'NEEDS_REVIEW'
    else:
        analysis['issue_category'] = 'OTHER'
    
    return analysis

# Read chunk 1
with open(BASE_DIR / 'scripts/chunk_1_events.csv', 'r') as f:
    reader = csv.DictReader(f)
    events = list(reader)

# Separate problematic from OK
problematic = [e for e in events if not e['recommendation'].startswith('OK')]
ok_events = [e for e in events if e['recommendation'].startswith('OK')]

print("="*100)
print("CHUNK 1 DETAILED REVIEW WITH CODE CONTEXT")
print("="*100)
print(f"\nTotal events: {len(events)}")
print(f"Problematic events: {len(problematic)}")
print(f"OK events to verify: {len(ok_events)}\n")

# Categorize problematic events
categories = {}
for event in problematic:
    analysis = analyze_event(event)
    cat = analysis['issue_category']
    if cat not in categories:
        categories[cat] = []
    categories[cat].append(analysis)

print("Issues by category:")
for cat in sorted(categories.keys()):
    print(f"  {cat}: {len(categories[cat])}")

# Now create a detailed review report
report = []
report.append("\n" + "="*100)
report.append("DETAILED REVIEW - ALL PROBLEMATIC EVENTS")
report.append("="*100)

# Review by category
for cat in ['MISSING_DESCRIPTION', 'REVIEW_DEBUG_GRANULAR', 'ANTI_PATTERN', 'MISNOMER', 'REPLACE_GENERIC', 'REMOVE', 'NEEDS_REVIEW']:
    if cat not in categories:
        continue
    
    analyses = categories[cat]
    report.append(f"\n\n{'='*100}")
    report.append(f"{cat}: {len(analyses)} events")
    report.append('='*100)
    
    for i, analysis in enumerate(analyses[:3], 1):  # Show first 3 of each category
        event = analysis['event']
        code = analysis['code_context']
        
        report.append(f"\n{i}. {event['event_type']} [{event['level']}]")
        report.append(f"   Location: {event['file']}:{event['line']}")
        report.append(f"   Description: {event['description']}")
        report.append(f"   Recommendation: {event['recommendation']}")
        report.append(f"\n   CODE CONTEXT:")
        report.append("   " + "\n   ".join(format_code_context(code).split("\n")))
        report.append("")
    
    if len(analyses) > 3:
        report.append(f"\n   ... and {len(analyses) - 3} more events in this category")

# Write report
report_text = "\n".join(report)
report_file = BASE_DIR / 'CHUNK_1_REVIEW_DETAILED.md'

with open(report_file, 'w') as f:
    f.write(report_text)

print(f"\n\n✓ Report written to: {report_file}")
print(f"\nReport preview (first 100 lines):")
print("\n".join(report_text.split("\n")[:100]))
