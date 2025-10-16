#!/usr/bin/env python3
"""
Remove init-phase observability.observe() calls that were replaced by InitEventFormatter.
"""

import re
from pathlib import Path
from typing import List, Tuple

# Events to remove (init phase - replaced by InitEventFormatter)
EVENTS_TO_REMOVE = {
    'AGENT_INITIALIZED',
    'MCP_SERVER_REGISTRATION_COMPLETED',
    'SCHEDULER_PARSER_INITIALIZED',
    'MCP_TRANSPORT_DETECTED',
    'A2A_SERVER_STARTED',
    'MCP_SERVER_REGISTRATION_STARTED',
    'A2A_CONFIG_LOAD_COMPLETED',
    'DATABASE_TABLES_CREATED',
    'MCP_SERVER_CONNECTED',
    'A2A_CONFIG_LOAD_STARTED',
    'MCP_SERVER_CONNECTING',
    'MCP_TOOL_DISCOVERY_COMPLETED',
    'SCHEDULER_MANAGER_INITIALIZED',
    'A2A_DISCOVERY_INITIALIZED',
    'DATABASE_MANAGER_INITIALIZED',
    'SCHEDULER_SERVICE_INITIALIZED',
    'SERVICE_INITIALIZED',
}

def find_observe_calls_to_remove(file_path: Path) -> List[Tuple[int, int]]:
    """Find line ranges of observe() calls that reference init events."""
    content = file_path.read_text()
    lines = content.split('\n')
    
    ranges_to_remove = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Look for observability.observe( calls
        if 'observability.observe(' in line:
            start_line = i
            
            # Extract the full call (might span multiple lines)
            call_lines = [line]
            paren_count = line.count('(') - line.count(')')
            j = i + 1
            
            while paren_count > 0 and j < len(lines):
                call_lines.append(lines[j])
                paren_count += lines[j].count('(') - lines[j].count(')')
                j += 1
            
            full_call = '\n'.join(call_lines)
            
            # Check if this call references an init event
            for event in EVENTS_TO_REMOVE:
                pattern = rf'event_type\s*=\s*observability\.\w+\.{event}'
                if re.search(pattern, full_call):
                    # Mark this range for removal
                    ranges_to_remove.append((start_line, j))
                    break
            
            i = j
        else:
            i += 1
    
    return ranges_to_remove


def remove_observe_calls(file_path: Path, dry_run: bool = False) -> int:
    """Remove observe() calls for init events from file."""
    ranges = find_observe_calls_to_remove(file_path)
    
    if not ranges:
        return 0
    
    content = file_path.read_text()
    lines = content.split('\n')
    
    # Replace observe() calls with pass to maintain structure
    lines_to_remove = set()
    for start, end in ranges:
        # Get the indentation of the observe call
        indent = len(lines[start]) - len(lines[start].lstrip())
        
        # Replace the first line with a pass statement
        lines[start] = ' ' * indent + 'pass  # REMOVED: init-phase observe() call'
        
        # Mark remaining lines for removal
        for line_idx in range(start + 1, end):
            lines_to_remove.add(line_idx)
    
    # Rebuild without removed lines
    new_lines = [lines[i] for i in range(len(lines)) if i not in lines_to_remove]
    
    if not dry_run:
        file_path.write_text('\n'.join(new_lines))
    
    return len(ranges)


def main():
    """Remove init-phase observe() calls from all Python files."""
    total_removed = 0
    files_modified = []
    
    # Find all Python files
    for py_file in Path('src').rglob('*.py'):
        count = remove_observe_calls(py_file, dry_run=False)
        if count > 0:
            total_removed += count
            files_modified.append((str(py_file), count))
            print(f'✓ {py_file}: removed {count} init-phase observe() calls')
    
    print(f'\nTotal: {total_removed} observe() calls removed from {len(files_modified)} files')
    
    if files_modified:
        print('\nFiles modified:')
        for file, count in sorted(files_modified, key=lambda x: -x[1]):
            print(f'  {file}: {count} calls')


if __name__ == '__main__':
    main()
