#!/usr/bin/env python3
"""
Audit all observability.observe() calls in the codebase.
Extract event types, levels, triggers, and descriptions into a CSV.
"""

import re
import csv
from pathlib import Path
from typing import List, Dict, Any


def extract_observe_calls(file_path: Path) -> List[Dict[str, Any]]:
    """Extract all observability.observe() calls from a Python file."""
    events = []
    
    try:
        content = file_path.read_text()
        lines = content.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Look for observability.observe( calls
            if 'observability.observe(' in line:
                # Extract the full call (might span multiple lines)
                call_lines = [line]
                paren_count = line.count('(') - line.count(')')
                j = i + 1
                
                while paren_count > 0 and j < len(lines):
                    call_lines.append(lines[j])
                    paren_count += lines[j].count('(') - lines[j].count(')')
                    j += 1
                
                full_call = '\n'.join(call_lines)
                
                # Extract event_type (handle both enum and string formats)
                event_match = re.search(r'event_type=observability\.(SystemEvents|ConversationEvents|ErrorEvents|ServerEvents|APIEvents)\.(\w+)', full_call)
                if event_match:
                    event_type = f"{event_match.group(1)}.{event_match.group(2)}"
                else:
                    # Try raw string format
                    string_match = re.search(r'event_type="([^"]+)"', full_call)
                    if string_match:
                        event_type = f"STRING:{string_match.group(1)}"
                    else:
                        # Try positional first argument (old style)
                        pos_match = re.search(r'observability\.observe\(\s*observability\.(SystemEvents|ConversationEvents|ErrorEvents|ServerEvents|APIEvents)\.(\w+)', full_call)
                        if pos_match:
                            event_type = f"{pos_match.group(1)}.{pos_match.group(2)}"
                        else:
                            event_type = "MALFORMED"
                
                # Extract level
                level_match = re.search(r'level=observability\.EventLevel\.(\w+)', full_call)
                if not level_match:
                    # Try positional second argument
                    level_match = re.search(r'observability\.observe\([^,]+,\s*observability\.EventLevel\.(\w+)', full_call)
                level = level_match.group(1) if level_match else "MALFORMED"
                
                # Extract description (might be in 'description' field or 'data.description')
                desc_match = re.search(r'description["\s]*[:=]["\s]*[rf]?"([^"]+)"', full_call)
                if not desc_match:
                    desc_match = re.search(r'"description":\s*f?"([^"]+)"', full_call)
                description = desc_match.group(1) if desc_match else "NO DESCRIPTION"
                
                # Get relative file path
                try:
                    rel_path = str(file_path.relative_to(Path.cwd() / 'src'))
                    rel_path = f"src/{rel_path}"
                except:
                    rel_path = str(file_path)
                
                # Get line number
                line_num = i + 1
                
                # Determine trigger/context
                trigger = f"{rel_path}:{line_num}"
                
                events.append({
                    'event_type': event_type,
                    'level': level,
                    'trigger': trigger,
                    'description': description,
                    'file': rel_path,
                    'line': line_num
                })
                
                i = j
            else:
                i += 1
                
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
    
    return events


def main():
    """Main audit function."""
    src_dir = Path('src').resolve()
    all_events = []
    
    # Find all Python files with observability.observe calls
    for py_file in src_dir.rglob('*.py'):
        try:
            rel_path = py_file.relative_to(src_dir.parent)
            events = extract_observe_calls(py_file)
            all_events.extend(events)
        except Exception as e:
            print(f"Skipping {py_file}: {e}")
    
    # Sort by event type, then level
    all_events.sort(key=lambda x: (x['event_type'], x['level'], x['file']))
    
    # Write to CSV
    output_file = 'observability_events_audit.csv'
    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['event_type', 'level', 'trigger', 'description', 'file', 'line'])
        writer.writeheader()
        writer.writerows(all_events)
    
    # Print summary statistics
    print(f"\n{'='*80}")
    print(f"OBSERVABILITY EVENTS AUDIT")
    print(f"{'='*80}")
    print(f"\nTotal events found: {len(all_events)}")
    print(f"Output file: {output_file}")
    
    # Count by event category
    event_categories = {}
    for event in all_events:
        category = event['event_type'].split('.')[0]
        event_categories[category] = event_categories.get(category, 0) + 1
    
    print(f"\nBy Category:")
    for category, count in sorted(event_categories.items()):
        print(f"  {category}: {count}")
    
    # Count by level
    level_counts = {}
    for event in all_events:
        level = event['level']
        level_counts[level] = level_counts.get(level, 0) + 1
    
    print(f"\nBy Level:")
    for level, count in sorted(level_counts.items()):
        print(f"  {level}: {count}")
    
    # Top 10 most frequent event types
    event_type_counts = {}
    for event in all_events:
        et = event['event_type']
        event_type_counts[et] = event_type_counts.get(et, 0) + 1
    
    print(f"\nTop 10 Most Frequent Event Types:")
    for et, count in sorted(event_type_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {et}: {count}")
    
    print(f"\n{'='*80}\n")


if __name__ == '__main__':
    main()
