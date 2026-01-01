#!/usr/bin/env python3
"""
Helper script to add descriptions to observability.observe() calls.

Usage:
    python scripts/add_descriptions_helper.py <file> [--start-line LINE] [--auto]

This script:
1. Finds all observe() calls missing descriptions
2. Extracts context (event type, data, surrounding code)
3. Suggests descriptions based on patterns
4. Optionally applies them automatically
"""

import re
import ast
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional

class ObserveCallAnalyzer:
    """Analyze observe() calls and suggest descriptions."""
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        with open(self.file_path, 'r', encoding='utf-8') as f:
            self.content = f.read()
        self.lines = self.content.split('\n')
    
    def find_missing_descriptions(self) -> List[Dict]:
        """Find all observe() calls without description parameter."""
        pattern = r'observability\.observe\('
        results = []
        
        for match in re.finditer(pattern, self.content):
            start_pos = match.start()
            line_no = self.content[:start_pos].count('\n') + 1
            
            # Extract the full call (handle multi-line)
            call_start = start_pos
            paren_count = 0
            call_end = call_start
            in_call = False
            
            for i in range(call_start, len(self.content)):
                char = self.content[i]
                if char == '(':
                    paren_count += 1
                    in_call = True
                elif char == ')':
                    paren_count -= 1
                    if paren_count == 0 and in_call:
                        call_end = i + 1
                        break
            
            call_text = self.content[call_start:call_end]
            
            # Check if description is missing
            if 'description' not in call_text:
                context = self._extract_context(line_no, call_text)
                results.append({
                    'line': line_no,
                    'call': call_text,
                    **context
                })
        
        return results
    
    def _extract_context(self, line_no: int, call_text: str) -> Dict:
        """Extract context from the observe() call."""
        context = {
            'event_type': None,
            'level': None,
            'data_keys': [],
            'function': None,
            'before_context': [],
            'after_context': []
        }
        
        # Extract event_type
        event_match = re.search(r'event_type=observability\.(\w+)\.(\w+)', call_text)
        if event_match:
            context['event_type'] = f"{event_match.group(1)}.{event_match.group(2)}"
        
        # Extract level
        level_match = re.search(r'level=observability\.EventLevel\.(\w+)', call_text)
        if level_match:
            context['level'] = level_match.group(1)
        
        # Extract data keys
        data_match = re.search(r'data=\{([^}]+)\}', call_text, re.DOTALL)
        if data_match:
            data_content = data_match.group(1)
            # Simple extraction of keys
            for match in re.finditer(r'"([^"]+)":', data_content):
                context['data_keys'].append(match.group(1))
        
        # Find containing function
        for i in range(line_no - 1, max(0, line_no - 100), -1):
            line = self.lines[i]
            if line.strip().startswith('def ') or line.strip().startswith('async def '):
                func_match = re.search(r'def\s+(\w+)', line)
                if func_match:
                    context['function'] = func_match.group(1)
                    break
        
        # Get surrounding lines for context
        context['before_context'] = [
            self.lines[i].strip() 
            for i in range(max(0, line_no - 6), line_no - 1)
            if self.lines[i].strip() and not self.lines[i].strip().startswith('#')
        ][-3:]  # Last 3 non-empty, non-comment lines
        
        return context
    
    def suggest_description(self, event_info: Dict) -> str:
        """Suggest a description based on event context."""
        event_type = event_info.get('event_type', '')
        level = event_info.get('level', '')
        data_keys = event_info.get('data_keys', [])
        function = event_info.get('function', '')
        before = event_info.get('before_context', [])
        
        # Pattern matching for suggestions
        suggestions = []
        
        # ErrorEvents patterns
        if 'ErrorEvents' in event_type:
            if 'FAILED' in event_type or 'ERROR' in event_type:
                if any('error' in k for k in data_keys):
                    suggestions.append(f"{{operation}} failed: {{error}}")
                else:
                    suggestions.append(f"{{operation}} failed")
            elif 'TIMEOUT' in event_type:
                suggestions.append(f"{{operation}} timed out after {{timeout}}s")
            elif 'VALIDATION' in event_type:
                suggestions.append(f"Validation failed: {{reason}}")
            elif 'CONFIGURATION' in event_type:
                suggestions.append(f"Configuration error: {{error}}")
        
        # SystemEvents patterns
        elif 'SystemEvents' in event_type:
            if 'COMPLETED' in event_type:
                suggestions.append(f"{{operation}} completed successfully")
            elif 'STARTED' in event_type or 'INITIALIZED' in event_type:
                suggestions.append(f"{{operation}} started/initialized")
            elif 'FAILED' in event_type:
                suggestions.append(f"{{operation}} failed")
        
        # Add function context
        if function:
            suggestions.append(f"# Function: {function}()")
        
        # Add data context
        if data_keys:
            key_str = ', '.join(data_keys[:3])
            suggestions.append(f"# Data keys: {key_str}")
        
        # Add before context
        if before:
            suggestions.append(f"# Context: {' | '.join(before[-2:])}")
        
        return '\n'.join(suggestions) if suggestions else "# No suggestion available"
    
    def generate_report(self) -> str:
        """Generate a report of all missing descriptions with suggestions."""
        missing = self.find_missing_descriptions()
        
        if not missing:
            return f"✅ No missing descriptions in {self.file_path}\n"
        
        report = []
        report.append(f"\n{'='*80}")
        report.append(f"File: {self.file_path}")
        report.append(f"Missing descriptions: {len(missing)}")
        report.append(f"{'='*80}\n")
        
        for i, event in enumerate(missing, 1):
            report.append(f"\n--- Event {i}/{len(missing)} ---")
            report.append(f"Line: {event['line']}")
            report.append(f"Event: {event['event_type']}")
            report.append(f"Level: {event['level']}")
            report.append(f"Function: {event.get('function', 'Unknown')}")
            
            if event['data_keys']:
                report.append(f"Data keys: {', '.join(event['data_keys'])}")
            
            if event['before_context']:
                report.append("\nContext:")
                for line in event['before_context']:
                    report.append(f"  {line}")
            
            report.append("\nSuggested description:")
            report.append(self.suggest_description(event))
            report.append("-" * 80)
        
        return '\n'.join(report)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python scripts/add_descriptions_helper.py <file> [--start-line LINE]")
        print("\nExample:")
        print("  python scripts/add_descriptions_helper.py src/muxi/formation/overlord/overlord.py")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    if not Path(file_path).exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    
    analyzer = ObserveCallAnalyzer(file_path)
    report = analyzer.generate_report()
    print(report)


if __name__ == '__main__':
    main()
