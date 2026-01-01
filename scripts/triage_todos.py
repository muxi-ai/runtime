#!/usr/bin/env python3
"""
Quick triage: Stale vs Real TODO observability comments.

Stale = observe() call exists within 5 lines before TODO
Real = No observe() call, needs implementation
"""

import re
from pathlib import Path
from collections import defaultdict

def is_stale_todo(lines, todo_line_idx):
    """Check if TODO is stale (observe already exists)."""
    # Check 10 lines before the TODO for observe() pattern
    start = max(0, todo_line_idx - 10)
    context_lines = lines[start:todo_line_idx]
    context = '\n'.join(context_lines)
    
    # Look for observe() call in context
    if 'observability.observe(' in context or '.observe(' in context:
        return True
    
    # Also check if previous line is just a closing ) after observe call
    if todo_line_idx > 0:
        prev_line = lines[todo_line_idx - 1].strip()
        if prev_line == ')' and todo_line_idx > 1:
            # Check line before that for observe pattern
            context_before = '\n'.join(lines[max(0, todo_line_idx - 10):todo_line_idx - 1])
            if 'observe(' in context_before:
                return True
    
    return False

def extract_event_level(comment):
    """Extract event level from TODO comment."""
    comment_lower = comment.lower()
    
    # Check for explicit level hints
    if 'error' in comment_lower:
        return 'ERROR'
    elif 'warning' in comment_lower or 'warn' in comment_lower:
        return 'WARNING'
    elif 'debug' in comment_lower:
        return 'DEBUG'
    elif 'info' in comment_lower:
        return 'INFO'
    else:
        # Default based on context
        return 'UNKNOWN'

def triage_file(file_path):
    """Triage all TODOs in a file."""
    try:
        lines = file_path.read_text().split('\n')
    except:
        return [], []
    
    stale = []
    real = []
    
    for i, line in enumerate(lines):
        if re.search(r'#.*TODO.*observability', line, re.IGNORECASE):
            level = extract_event_level(line)
            if is_stale_todo(lines, i):
                stale.append((file_path, i+1, line.strip(), level))
            else:
                real.append((file_path, i+1, line.strip(), level))
    
    return stale, real

def get_component(file_path):
    """Extract component from file path."""
    path_str = str(file_path).lower()
    
    components = {
        'mcp': 'MCP',
        'a2a': 'A2A',
        'database': 'Database',
        'db.py': 'Database',
        'memory': 'Memory',
        'scheduler': 'Scheduler',
        'webhook': 'Webhook',
        'resilience': 'Resilience',
        'workflow': 'Workflow',
        'documents': 'Document Processing',
        'clarification': 'Clarification',
        'overlord': 'Overlord',
        'agent': 'Agent',
    }
    
    for key, component in components.items():
        if key in path_str:
            return component
    return 'Other'

def main():
    src_dir = Path('src/muxi')
    
    if not src_dir.exists():
        print("Error: Run from runtime directory")
        return
    
    # Triage all files
    all_stale = []
    all_real = []
    component_stats = defaultdict(lambda: {'stale': 0, 'real': 0})
    level_stats = defaultdict(int)
    
    print("🔍 Triaging TODOs...")
    print()
    
    for py_file in src_dir.rglob("*.py"):
        stale, real = triage_file(py_file)
        all_stale.extend(stale)
        all_real.extend(real)
        
        # Track by component
        component = get_component(py_file)
        component_stats[component]['stale'] += len(stale)
        component_stats[component]['real'] += len(real)
        
        # Track by level (real TODOs only)
        for item in real:
            level = item[3]  # level is 4th element
            level_stats[level] += 1
    
    # Print summary
    total = len(all_stale) + len(all_real)
    stale_pct = len(all_stale) / total * 100 if total > 0 else 0
    
    print("="*60)
    print("TRIAGE RESULTS")
    print("="*60)
    print(f"\nTotal TODOs: {total}")
    print(f"  STALE (observe exists): {len(all_stale)} ({stale_pct:.1f}%)")
    print(f"  REAL (need implementation): {len(all_real)} ({100-stale_pct:.1f}%)")
    print()
    
    # By component
    print("By Component:")
    print(f"{'Component':<20} {'Stale':>6} {'Real':>6} {'Total':>6} {'Stale %':>8}")
    print("-" * 60)
    
    for component in sorted(component_stats.keys()):
        stats = component_stats[component]
        total_comp = stats['stale'] + stats['real']
        stale_pct_comp = stats['stale'] / total_comp * 100 if total_comp > 0 else 0
        
        print(f"{component:<20} {stats['stale']:>6} {stats['real']:>6} {total_comp:>6} {stale_pct_comp:>7.1f}%")
    
    print()
    # By event level
    print()
    print("By Event Level (real TODOs):")
    for level in ['ERROR', 'WARNING', 'INFO', 'DEBUG', 'UNKNOWN']:
        count = level_stats.get(level, 0)
        if count > 0:
            print(f"  {level:<10} {count:>3} TODOs")
    
    print()
    print("="*60)
    print(f"\n💡 ACTUAL WORK: {len(all_real)} TODOs need implementation")
    print(f"🗑️  CLEANUP: {len(all_stale)} stale TODO comments to delete")
    print()
    
    # Show sample stale TODOs
    if all_stale:
        print("\n📋 Sample STALE TODOs (first 10):")
        for file_path, line_num, comment, level in all_stale[:10]:
            rel_path = str(file_path).replace('src/muxi/', '')
            print(f"  {rel_path}:{line_num}")
        if len(all_stale) > 10:
            print(f"  ... and {len(all_stale) - 10} more")
    
    # Show sample real TODOs by level
    if all_real:
        print("\n⚠️  Sample REAL TODOs by level:")
        for level in ['ERROR', 'WARNING', 'INFO', 'DEBUG']:
            level_todos = [t for t in all_real if t[3] == level][:3]
            if level_todos:
                print(f"\n  {level}:")
                for file_path, line_num, comment, _ in level_todos:
                    rel_path = str(file_path).replace('src/muxi/', '')
                    print(f"    {rel_path}:{line_num}")

if __name__ == "__main__":
    main()
