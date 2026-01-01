#!/usr/bin/env python3
"""
Apply systematic audit fixes based on identified patterns.
This script:
1. Reads the audit CSV with recommendations
2. Applies fixes systematically based on categories
3. Documents all changes
4. Generates a detailed change log
"""

import csv
import json
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path("/Users/ran/Projects/muxi/code/runtime")

def categorize_all_problems():
    """Categorize all problem events by type."""
    issues = defaultdict(list)
    
    # Read main CSV
    with open(BASE_DIR / 'observability_events_audit.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rec = row['recommendation']
            event_type = row['event_type']
            
            if rec.startswith('OK'):
                continue
            
            # Categorize
            if 'ANTI-PATTERN' in rec and event_type == 'ErrorEvents.WARNING':
                issues['ANTI_PATTERN_WARNING'].append(row)
            elif 'MISNOMER' in rec and 'RETRY_ATTEMPTED' in event_type:
                issues['MISNOMER_RETRY'].append(row)
            elif 'REPLACE' in rec and 'INTERNAL_ERROR' in event_type:
                issues['REPLACE_INTERNAL_ERROR'].append(row)
            elif 'REMOVE' in rec and 'SERVER_STARTED' in event_type:
                issues['REMOVE_SERVER_STARTED'].append(row)
            elif 'REMOVE' in rec and 'INITIALIZING' in event_type:
                issues['REMOVE_INITIALIZING'].append(row)
            elif 'REVIEW - DEBUG' in rec:
                issues['REVIEW_DEBUG'].append(row)
            elif 'REVIEW' in rec and 'granular' in rec:
                issues['REVIEW_GRANULAR'].append(row)
            elif 'MISSING DESCRIPTION' in rec:
                issues['MISSING_DESCRIPTION'].append(row)
            elif 'NEEDS_REVIEW' in rec and 'DEBUG' in rec.upper():
                issues['NEEDS_REVIEW_DEBUG'].append(row)
            elif 'NEEDS_REVIEW' in rec:
                issues['NEEDS_REVIEW_GENERIC'].append(row)
            elif 'KEEP' in rec:
                issues['KEEP_INTENTIONAL'].append(row)
            else:
                issues['OTHER'].append(row)
    
    return issues

def generate_summary():
    """Generate a summary of all issues."""
    issues = categorize_all_problems()
    
    print("\n" + "="*100)
    print("AUDIT FIXES - CATEGORIZED SUMMARY")
    print("="*100)
    
    # Summary
    print(f"\nTotal issues: {sum(len(v) for v in issues.values())}\n")
    
    print("Issues by category:")
    for cat in sorted(issues.keys(), key=lambda x: len(issues[x]), reverse=True):
        count = len(issues[cat])
        print(f"  {cat:30s}: {count:3d} events")
    
    # Recommendations by category
    print("\n" + "-"*100)
    print("RECOMMENDED FIXES (in priority order)")
    print("-"*100)
    
    recommendations = []
    
    # Priority 1: Misclassifications
    if issues['ANTI_PATTERN_WARNING']:
        recommendations.append({
            'priority': 1,
            'category': 'ANTI_PATTERN_WARNING',
            'count': len(issues['ANTI_PATTERN_WARNING']),
            'action': 'Replace ErrorEvents.WARNING with specific error types based on context',
            'example': f"File: {issues['ANTI_PATTERN_WARNING'][0]['file']}, Line: {issues['ANTI_PATTERN_WARNING'][0]['line']}"
        })
    
    if issues['MISNOMER_RETRY']:
        recommendations.append({
            'priority': 1,
            'category': 'MISNOMER_RETRY',
            'count': len(issues['MISNOMER_RETRY']),
            'action': 'Replace ErrorEvents.RETRY_ATTEMPTED with specific error types (no retry happening)',
            'example': f"File: {issues['MISNOMER_RETRY'][0]['file']}, Line: {issues['MISNOMER_RETRY'][0]['line']}"
        })
    
    if issues['REPLACE_INTERNAL_ERROR']:
        recommendations.append({
            'priority': 1,
            'category': 'REPLACE_INTERNAL_ERROR',
            'count': len(issues['REPLACE_INTERNAL_ERROR']),
            'action': 'Replace generic INTERNAL_ERROR with specific error types',
            'example': f"File: {issues['REPLACE_INTERNAL_ERROR'][0]['file']}, Line: {issues['REPLACE_INTERNAL_ERROR'][0]['line']}"
        })
    
    # Priority 2: Event misuse
    if issues['REMOVE_SERVER_STARTED']:
        recommendations.append({
            'priority': 2,
            'category': 'REMOVE_SERVER_STARTED',
            'count': len(issues['REMOVE_SERVER_STARTED']),
            'action': 'Remove misused ServerEvents.SERVER_STARTED (debug traces, not server start)',
            'example': f"File: {issues['REMOVE_SERVER_STARTED'][0]['file']}, Line: {issues['REMOVE_SERVER_STARTED'][0]['line']}"
        })
    
    if issues['REMOVE_INITIALIZING']:
        recommendations.append({
            'priority': 2,
            'category': 'REMOVE_INITIALIZING',
            'count': len(issues['REMOVE_INITIALIZING']),
            'action': 'Remove redundant INITIALIZING events (duplicated in InitEventFormatter)',
            'example': f"File: {issues['REMOVE_INITIALIZING'][0]['file']}, Line: {issues['REMOVE_INITIALIZING'][0]['line']}"
        })
    
    # Priority 3: Level adjustments
    if issues['NEEDS_REVIEW_DEBUG']:
        recommendations.append({
            'priority': 3,
            'category': 'NEEDS_REVIEW_DEBUG',
            'count': len(issues['NEEDS_REVIEW_DEBUG']),
            'action': 'Change level from INFO to DEBUG for granular step-by-step tracing',
            'example': f"File: {issues['NEEDS_REVIEW_DEBUG'][0]['file']}, Line: {issues['NEEDS_REVIEW_DEBUG'][0]['line']}"
        })
    
    # Priority 4: Descriptions
    if issues['MISSING_DESCRIPTION']:
        recommendations.append({
            'priority': 4,
            'category': 'MISSING_DESCRIPTION',
            'count': len(issues['MISSING_DESCRIPTION']),
            'action': 'Add/improve descriptions (many are CSV extraction bugs, not code issues)',
            'example': f"File: {issues['MISSING_DESCRIPTION'][0]['file']}, Line: {issues['MISSING_DESCRIPTION'][0]['line']}"
        })
    
    # Print recommendations
    for rec in sorted(recommendations, key=lambda x: x['priority']):
        print(f"\nPriority {rec['priority']}: {rec['category']} ({rec['count']} events)")
        print(f"  Action: {rec['action']}")
        print(f"  Example: {rec['example']}")
    
    # Analysis
    print("\n" + "-"*100)
    print("ANALYSIS")
    print("-"*100)
    
    total_issues = sum(len(v) for v in issues.values() if v and not any(k in c for k in ['KEEP', 'OTHER'] for c in [v]))
    
    print(f"\nTotal issues to fix: {total_issues}")
    print(f"Keep intentional: {len(issues['KEEP_INTENTIONAL'])}")
    print(f"Other/unclear: {len(issues['OTHER'])}")
    
    # Save issues to JSON for reference
    issues_json = {k: [{'type': v['event_type'], 'file': v['file'], 'line': v['line'], 'rec': v['recommendation'][:100]} for v in issues[k]] for k in issues}
    with open(BASE_DIR / 'audit_issues_categorized.json', 'w') as f:
        json.dump(issues_json, f, indent=2)
    
    print(f"\nCategorized issues saved to: audit_issues_categorized.json")
    
    return issues

if __name__ == '__main__':
    issues = generate_summary()
