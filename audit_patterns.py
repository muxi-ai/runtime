#!/usr/bin/env python3
"""
Fresh Observability Audit using Map-Reduce Pattern

Based on patterns identified in Chunks 2-3, scan entire codebase for:
1. RETRY_ATTEMPTED misnomers (not in retry callbacks)
2. INTERNAL_ERROR generic (where specific types exist)
3. SERVER_STARTED debug traces
4. ANTI_PATTERN warnings (where specific types exist)
5. Missing descriptions
6. Wrong event levels
"""

import os
import re
from collections import defaultdict
from typing import Dict, List, Tuple

# Known specific error types that should be used instead of generic
SPECIFIC_ERROR_TYPES = {
    'AUTHENTICATION_FAILED', 'AUTHORIZATION_FAILED', 'VALIDATION_ERROR',
    'NETWORK_ERROR', 'SERVICE_UNAVAILABLE', 'RESOURCE_NOT_FOUND',
    'RESOURCE_EXHAUSTED', 'SERIALIZATION_ERROR', 'MEMORY_OPERATION_FAILED',
    'MEMORY_RETRIEVAL_FAILED', 'MEMORY_CLEAR_FAILED', 'EMBEDDINGS_GENERATION_FAILED',
    'THUMBNAIL_GENERATION_FAILED', 'KNOWLEDGE_SEARCH_FAILED', 'LLM_INITIALIZATION_FAILED',
}

# Files where RETRY_ATTEMPTED is legitimate (actual retry callbacks)
LEGITIMATE_RETRY_FILES = {
    'retry_manager.py',
    'reconnection.py',
}

# Patterns for map phase
PATTERNS = {
    'retry_attempted': re.compile(r'ErrorEvents\.RETRY_ATTEMPTED'),
    'internal_error': re.compile(r'ErrorEvents\.INTERNAL_ERROR'),
    'server_started': re.compile(r'ServerEvents\.SERVER_STARTED'),
    'anti_pattern': re.compile(r'ErrorEvents\.(?:WARNING|ANTI_PATTERN)'),
    'observe_call': re.compile(r'observability\.observe\s*\('),
}

class ObservabilityIssue:
    def __init__(self, file_path: str, line_num: int, issue_type: str, 
                 description: str, context: str = ""):
        self.file_path = file_path
        self.line_num = line_num
        self.issue_type = issue_type
        self.description = description
        self.context = context
    
    def __repr__(self):
        return f"{self.file_path}:{self.line_num} [{self.issue_type}] {self.description}"

def scan_file(file_path: str) -> List[ObservabilityIssue]:
    """Map function: Scan a single file for observability issues."""
    issues = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')
    except Exception as e:
        return issues
    
    # Check if this is a legitimate retry file
    is_retry_file = any(filename in file_path for filename in LEGITIMATE_RETRY_FILES)
    
    for i, line in enumerate(lines, 1):
        # Pattern 1: RETRY_ATTEMPTED misnomers
        if PATTERNS['retry_attempted'].search(line) and not is_retry_file:
            # Look for context - is this actually a retry?
            context_start = max(0, i - 10)
            context_end = min(len(lines), i + 5)
            context = '\n'.join(lines[context_start:context_end])
            
            # Heuristics for actual retry
            is_actual_retry = any(keyword in context.lower() for keyword in [
                'retry', 'attempt', 'backoff', 'max_retries', 'retry_count'
            ])
            
            if not is_actual_retry:
                issues.append(ObservabilityIssue(
                    file_path, i, 'RETRY_ATTEMPTED_MISNOMER',
                    'RETRY_ATTEMPTED used but no retry happening',
                    context=line.strip()
                ))
        
        # Pattern 2: Generic INTERNAL_ERROR
        if PATTERNS['internal_error'].search(line):
            # Look ahead for context
            context_start = max(0, i - 5)
            context_end = min(len(lines), i + 10)
            context = '\n'.join(lines[context_start:context_end])
            
            # Check for keywords that suggest specific error types
            suggestions = []
            context_lower = context.lower()
            
            if any(kw in context_lower for kw in ['auth', 'credential', 'token', 'login']):
                suggestions.append('AUTHENTICATION_FAILED')
            if any(kw in context_lower for kw in ['network', 'connection', 'timeout', 'http']):
                suggestions.append('NETWORK_ERROR')
            if any(kw in context_lower for kw in ['service', 'unavailable', 'external', 'api']):
                suggestions.append('SERVICE_UNAVAILABLE')
            if any(kw in context_lower for kw in ['not found', 'missing', 'does not exist']):
                suggestions.append('RESOURCE_NOT_FOUND')
            if any(kw in context_lower for kw in ['memory', 'retrieval', 'memobase', 'buffer']):
                suggestions.extend(['MEMORY_OPERATION_FAILED', 'MEMORY_RETRIEVAL_FAILED'])
            if any(kw in context_lower for kw in ['json', 'parse', 'deserialize', 'yaml']):
                suggestions.append('SERIALIZATION_ERROR')
            if any(kw in context_lower for kw in ['size', 'limit', 'quota', 'capacity']):
                suggestions.append('RESOURCE_EXHAUSTED')
            if any(kw in context_lower for kw in ['validate', 'invalid', 'malformed']):
                suggestions.append('VALIDATION_ERROR')
            
            if suggestions:
                issues.append(ObservabilityIssue(
                    file_path, i, 'INTERNAL_ERROR_GENERIC',
                    f'Generic INTERNAL_ERROR, consider: {", ".join(set(suggestions))}',
                    context=line.strip()
                ))
        
        # Pattern 3: SERVER_STARTED debug traces
        if PATTERNS['server_started'].search(line):
            context_start = max(0, i - 3)
            context_end = min(len(lines), i + 3)
            context = '\n'.join(lines[context_start:context_end])
            
            # Check if this looks like a debug trace vs legitimate startup
            is_debug_trace = any(keyword in context.lower() for keyword in [
                'debug', 'entry point', 'breadcrumb', 'trace', 'logging'
            ])
            
            if is_debug_trace:
                issues.append(ObservabilityIssue(
                    file_path, i, 'SERVER_STARTED_DEBUG',
                    'SERVER_STARTED used as debug trace',
                    context=line.strip()
                ))
        
        # Pattern 4: Missing descriptions
        if PATTERNS['observe_call'].search(line):
            # Look ahead for description parameter
            context_start = i - 1
            context_end = min(len(lines), i + 15)
            block = '\n'.join(lines[context_start:context_end])
            
            # Check if description= is present
            if 'description=' not in block:
                # Check if this might be a valid reason (e.g., only data parameter)
                has_data = 'data=' in block
                has_level = 'level=' in block
                
                issues.append(ObservabilityIssue(
                    file_path, i, 'MISSING_DESCRIPTION',
                    'observability.observe() call without description parameter',
                    context=line.strip()
                ))
    
    return issues

def reduce_issues(all_issues: List[ObservabilityIssue]) -> Dict[str, List[ObservabilityIssue]]:
    """Reduce function: Group and prioritize issues."""
    grouped = defaultdict(list)
    
    for issue in all_issues:
        grouped[issue.issue_type].append(issue)
    
    return dict(grouped)

def scan_codebase(root_dir: str = 'src/muxi') -> Tuple[Dict[str, List[ObservabilityIssue]], int]:
    """Main map-reduce orchestration."""
    all_issues = []
    files_scanned = 0
    
    # Map phase: Scan all Python files
    for root, dirs, files in os.walk(root_dir):
        # Skip test directories and cache
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'tests']]
        
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                files_scanned += 1
                issues = scan_file(file_path)
                all_issues.extend(issues)
    
    # Reduce phase: Group by type
    grouped_issues = reduce_issues(all_issues)
    
    return grouped_issues, files_scanned

def print_report(grouped_issues: Dict[str, List[ObservabilityIssue]], files_scanned: int):
    """Print formatted audit report."""
    print("=" * 80)
    print("FRESH OBSERVABILITY AUDIT - Map-Reduce Results")
    print("=" * 80)
    print(f"\nFiles scanned: {files_scanned}")
    print(f"Total issues found: {sum(len(issues) for issues in grouped_issues.values())}")
    print()
    
    # Sort by priority
    priority_order = [
        'RETRY_ATTEMPTED_MISNOMER',
        'INTERNAL_ERROR_GENERIC',
        'SERVER_STARTED_DEBUG',
        'MISSING_DESCRIPTION',
    ]
    
    for issue_type in priority_order:
        if issue_type not in grouped_issues:
            continue
        
        issues = grouped_issues[issue_type]
        print(f"\n{issue_type}: {len(issues)} issues")
        print("-" * 80)
        
        # Group by file for easier review
        by_file = defaultdict(list)
        for issue in issues:
            by_file[issue.file_path].append(issue)
        
        for file_path in sorted(by_file.keys()):
            file_issues = by_file[file_path]
            print(f"\n  {file_path} ({len(file_issues)} issues)")
            for issue in file_issues[:5]:  # Show first 5 per file
                print(f"    Line {issue.line_num}: {issue.description}")
                if issue.context:
                    print(f"      {issue.context[:80]}")
            if len(file_issues) > 5:
                print(f"    ... and {len(file_issues) - 5} more")
    
    print("\n" + "=" * 80)
    print("SUMMARY BY PRIORITY")
    print("=" * 80)
    for issue_type in priority_order:
        count = len(grouped_issues.get(issue_type, []))
        priority = "HIGH" if issue_type in ['RETRY_ATTEMPTED_MISNOMER', 'INTERNAL_ERROR_GENERIC'] else "MEDIUM"
        print(f"[{priority}] {issue_type}: {count} issues")

if __name__ == '__main__':
    print("Starting fresh observability audit...")
    print("Using patterns from Chunks 2-3 analysis\n")
    
    grouped_issues, files_scanned = scan_codebase()
    print_report(grouped_issues, files_scanned)
    
    # Export to file for further analysis
    with open('FRESH_AUDIT_RESULTS.txt', 'w') as f:
        f.write("Fresh Observability Audit Results\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Files scanned: {files_scanned}\n")
        f.write(f"Total issues: {sum(len(issues) for issues in grouped_issues.values())}\n\n")
        
        for issue_type, issues in grouped_issues.items():
            f.write(f"\n{issue_type}: {len(issues)} issues\n")
            f.write("-" * 80 + "\n")
            for issue in issues:
                f.write(f"{issue}\n")
    
    print(f"\nDetailed results exported to: FRESH_AUDIT_RESULTS.txt")
