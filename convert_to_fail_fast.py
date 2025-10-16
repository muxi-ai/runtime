#!/usr/bin/env python3
"""
Convert init-phase error events to fail-fast exceptions.

These events currently log errors and continue, causing silent failures.
We'll replace them with proper exceptions that fail during initialization.
"""

from pathlib import Path
from typing import List, Tuple

# Events that should fail fast during init
FAIL_FAST_EVENTS = {
    'AGENT_INITIALIZATION_ERROR',  # Knowledge must work if configured
    'BUILTIN_MCP_INITIALIZATION_FAILED',  # MCP must work if configured
    'COMPONENT_INITIALIZATION_FAILED',  # A2A filtering must work if configured
}

def analyze_init_errors():
    """Analyze init error events to convert to fail-fast."""
    
    files_to_fix = [
        ('src/muxi/formation/agents/agent.py', 'AGENT_INITIALIZATION_ERROR', 300),
        ('src/muxi/formation/overlord/overlord.py', 'BUILTIN_MCP_INITIALIZATION_FAILED', 9650),
        ('src/muxi/formation/overlord/a2a_coordinator.py', 'COMPONENT_INITIALIZATION_FAILED', 77),
    ]
    
    print('Init Error Events to Convert to Fail-Fast:')
    print('='*80)
    
    for file, event, line in files_to_fix:
        file_path = Path(file)
        if file_path.exists():
            content = file_path.read_text()
            lines = content.split('\n')
            
            print(f'\n{event} ({file}:{line})')
            
            # Show context
            start = max(0, line - 5)
            end = min(len(lines), line + 10)
            
            print('  Current code:')
            for i in range(start, end):
                marker = '→' if i == line - 1 else ' '
                print(f'    {marker} {i+1}: {lines[i][:80]}')
    
    print('\n' + '='*80)
    print('\nRecommendation:')
    print('  1. Remove observability.observe() calls')
    print('  2. Replace with raise RuntimeError(...) from e')
    print('  3. Let InitEventFormatter show the error')
    print('  4. Formation fails cleanly during init')

if __name__ == '__main__':
    analyze_init_errors()
