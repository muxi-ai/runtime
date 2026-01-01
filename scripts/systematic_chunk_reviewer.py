#!/usr/bin/env python3
"""
Systematic Chunk Reviewer - Analyzes any chunk and generates detailed findings.
"""

import csv
import os
import sys
from pathlib import Path

BASE_DIR = Path("/Users/ran/Projects/muxi/code/runtime")

def read_code_context(file_path, line_num, context_lines=5):
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

def analyze_chunk(chunk_num):
    """Analyze a chunk and generate findings."""
    chunk_file = BASE_DIR / f'scripts/chunk_{chunk_num}_events.csv'
    
    if not chunk_file.exists():
        print(f"Chunk {chunk_num} file not found: {chunk_file}")
        return None
    
    with open(chunk_file, 'r') as f:
        reader = csv.DictReader(f)
        events = list(reader)
    
    # Categorize events
    ok_events = [e for e in events if e['recommendation'].startswith('OK')]
    problem_events = [e for e in events if not e['recommendation'].startswith('OK')]
    
    # Categorize problems
    categories = {}
    for event in problem_events:
        rec = event['recommendation']
        
        if 'MISSING DESCRIPTION' in rec:
            cat = 'MISSING_DESCRIPTION'
        elif 'REVIEW - DEBUG' in rec:
            cat = 'REVIEW_DEBUG_GRANULAR'
        elif 'ANTI-PATTERN' in rec:
            cat = 'ANTI_PATTERN'
        elif 'MISNOMER' in rec:
            cat = 'MISNOMER'
        elif 'REPLACE' in rec:
            cat = 'REPLACE_GENERIC'
        elif 'REMOVE' in rec:
            cat = 'REMOVE'
        elif 'REVIEW' in rec:
            cat = 'NEEDS_REVIEW'
        elif 'KEEP' in rec:
            cat = 'KEEP_INTENTIONAL'
        else:
            cat = 'OTHER'
        
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(event)
    
    # Generate summary report
    report = []
    report.append(f"{'='*100}")
    report.append(f"CHUNK {chunk_num} ANALYSIS SUMMARY")
    report.append(f"{'='*100}")
    report.append(f"\nTotal events: {len(events)}")
    report.append(f"OK events: {len(ok_events)} ({100*len(ok_events)/len(events):.1f}%)")
    report.append(f"Problematic events: {len(problem_events)} ({100*len(problem_events)/len(events):.1f}%)")
    
    report.append(f"\nIssues by category:")
    for cat in sorted(categories.keys()):
        count = len(categories[cat])
        report.append(f"  {cat:30s}: {count:3d} events")
    
    # Level distribution
    levels = {}
    for event in events:
        level = event['level']
        if level not in levels:
            levels[level] = 0
        levels[level] += 1
    
    report.append(f"\nLevel distribution:")
    for level in ['DEBUG', 'INFO', 'WARNING', 'ERROR']:
        if level in levels:
            count = levels[level]
            report.append(f"  {level:8s}: {count:3d} events ({100*count/len(events):5.1f}%)")
    
    # Sample problematic events
    report.append(f"\nSample problematic events (first 5 from each category):")
    for cat in sorted(categories.keys()):
        report.append(f"\n{cat}:")
        for i, event in enumerate(categories[cat][:5], 1):
            report.append(f"  {i}. {event['event_type']} [{event['level']}]")
            report.append(f"     Location: {event['file']}:{event['line']}")
            report.append(f"     Issue: {event['recommendation'][:60]}")
        if len(categories[cat]) > 5:
            report.append(f"  ... and {len(categories[cat]) - 5} more")
    
    return {
        'chunk_num': chunk_num,
        'total_events': len(events),
        'ok_events': len(ok_events),
        'problem_events': len(problem_events),
        'categories': categories,
        'levels': levels,
        'events': events,
        'report': '\n'.join(report)
    }

def main():
    if len(sys.argv) > 1:
        chunk_num = int(sys.argv[1])
        results = [analyze_chunk(chunk_num)]
    else:
        # Analyze all chunks
        results = []
        for chunk_num in range(1, 6):
            result = analyze_chunk(chunk_num)
            if result:
                results.append(result)
    
    # Print summary for all chunks
    print("\n" + "="*100)
    print("COMPREHENSIVE CHUNK ANALYSIS SUMMARY")
    print("="*100)
    
    total_events = sum(r['total_events'] for r in results)
    total_ok = sum(r['ok_events'] for r in results)
    total_problem = sum(r['problem_events'] for r in results)
    
    print(f"\nOverall statistics:")
    print(f"  Total events across all chunks: {total_events}")
    print(f"  OK events: {total_ok} ({100*total_ok/total_events:.1f}%)")
    print(f"  Problem events: {total_problem} ({100*total_problem/total_events:.1f}%)")
    
    print(f"\nPer-chunk summary:")
    for result in results:
        chunk_num = result['chunk_num']
        total = result['total_events']
        ok = result['ok_events']
        prob = result['problem_events']
        print(f"  Chunk {chunk_num}: {total:3d} events ({ok:3d} OK, {prob:3d} problems)")
    
    # Aggregate categories
    all_categories = {}
    for result in results:
        for cat, events in result['categories'].items():
            if cat not in all_categories:
                all_categories[cat] = 0
            all_categories[cat] += len(events)
    
    print(f"\nAggregated issues across all chunks:")
    for cat in sorted(all_categories.keys(), key=lambda x: all_categories[x], reverse=True):
        count = all_categories[cat]
        print(f"  {cat:30s}: {count:3d} events")
    
    # Print individual chunk reports
    for result in results:
        print("\n" + result['report'])
    
    # Save full analysis
    output_file = BASE_DIR / 'CHUNKS_ANALYSIS_SUMMARY.md'
    with open(output_file, 'w') as f:
        f.write("# Comprehensive Chunks Analysis\n\n")
        for result in results:
            f.write(result['report'])
            f.write("\n\n")
    
    print(f"\n✓ Full analysis saved to: {output_file}")

if __name__ == '__main__':
    main()
