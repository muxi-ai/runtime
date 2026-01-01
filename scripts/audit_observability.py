#!/usr/bin/env python3
"""
Observability Event Audit Script

Generates a comprehensive audit of all observability events:
- Lists all events with their categories
- Checks usage across codebase
- Identifies never-used events
- Suggests consolidations
- Outputs CSV for review

Usage:
    python scripts/audit_observability.py > observability_audit.csv
"""

import re
import subprocess
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set


def extract_events_from_file(file_path: Path) -> Dict[str, List[str]]:
    """Extract all event enum values from observability.py."""
    events_by_category = defaultdict(list)
    current_category = None

    with open(file_path) as f:
        content = f.read()

    # Find all enum classes
    enum_pattern = r'class (\w+Events)\(Enum\):'
    event_pattern = r'^\s+([A-Z_]+)\s*=\s*"([^"]+)"'

    lines = content.split('\n')
    for line in lines:
        # Check for enum class
        enum_match = re.match(enum_pattern, line)
        if enum_match:
            current_category = enum_match.group(1)
            continue

        # Check for event definition
        if current_category:
            event_match = re.match(event_pattern, line)
            if event_match:
                event_name = event_match.group(1)
                event_value = event_match.group(2)
                events_by_category[current_category].append({
                    'name': event_name,
                    'value': event_value
                })

    return events_by_category


def count_event_usage(event_name: str, src_dir: Path) -> int:
    """Count how many times an event is used in the codebase."""
    try:
        result = subprocess.run(
            ['grep', '-r', f'{event_name}', str(src_dir),
             '--include=*.py', '--exclude-dir=__pycache__'],
            capture_output=True,
            text=True
        )
        # Subtract 1 for the definition itself
        return max(0, len(result.stdout.strip().split('\n')) - 1 if result.stdout else 0)
    except Exception:
        return 0


def identify_duplicates(events_by_category: Dict) -> List[tuple]:
    """Identify potential duplicate or redundant events."""
    duplicates = []

    for category, events in events_by_category.items():
        for i, event1 in enumerate(events):
            for event2 in events[i+1:]:
                # Check for similar patterns
                name1 = event1['name']
                name2 = event2['name']

                # Same base, different suffix (STARTED/COMPLETED/FAILED)
                base1 = re.sub(r'_(STARTED|COMPLETED|FAILED)$', '', name1)
                base2 = re.sub(r'_(STARTED|COMPLETED|FAILED)$', '', name2)

                if base1 == base2 and base1 != name1:
                    duplicates.append((category, base1, [name1, name2]))

    return duplicates


def suggest_consolidation(event_name: str, event_value: str) -> str:
    """Suggest consolidation strategy for an event."""
    # Lifecycle events (STARTED/COMPLETED/FAILED)
    if any(suffix in event_name for suffix in ['_STARTED', '_COMPLETED', '_FAILED']):
        base = re.sub(r'_(STARTED|COMPLETED|FAILED)$', '', event_name)
        return f"Merge lifecycle: {base} with status field"

    # Connection state events
    if any(word in event_name for word in ['CONNECTING', 'CONNECTED', 'DISCONNECTED', 'RECONNECTING']):
        return "Merge into CONNECTION_STATE with state field"

    # Message events (too granular)
    if 'MESSAGE_SENT' in event_name or 'MESSAGE_RECEIVED' in event_name:
        return "Move to DEBUG level or remove"

    # Registration events
    if 'REGISTRATION' in event_name:
        return "Merge lifecycle: REGISTRATION with status"

    return ""


def main():
    """Generate observability audit report."""
    project_root = Path(__file__).parent.parent
    observability_file = project_root / 'src/muxi/datatypes/observability.py'
    src_dir = project_root / 'src'

    # Extract all events
    events_by_category = extract_events_from_file(observability_file)

    # Print CSV header
    print("Category,Event Name,Event Value,Usage Count,Suggestion,Keep/Review/Delete")

    total_events = 0
    never_used = 0
    rarely_used = 0

    # Analyze each event
    for category, events in sorted(events_by_category.items()):
        for event in events:
            name = event['name']
            value = event['value']

            # Count usage
            usage = count_event_usage(name, src_dir)
            total_events += 1

            # Categorize
            if usage == 0:
                never_used += 1
                action = "DELETE"
            elif usage < 5:
                rarely_used += 1
                action = "REVIEW"
            else:
                action = "KEEP"

            # Get suggestion
            suggestion = suggest_consolidation(name, value)
            if suggestion and action == "KEEP":
                action = "REVIEW"

            # Output CSV row
            print(f'{category},{name},{value},{usage},"{suggestion}",{action}')

    # Print summary to stderr so it doesn't pollute CSV
    import sys
    print(f"\nSummary:", file=sys.stderr)
    print(f"  Total events: {total_events}", file=sys.stderr)
    print(f"  Never used: {never_used} ({never_used/total_events*100:.1f}%)", file=sys.stderr)
    print(f"  Rarely used (<5): {rarely_used} ({rarely_used/total_events*100:.1f}%)", file=sys.stderr)
    print(f"  Candidates for removal: {never_used + rarely_used}", file=sys.stderr)


if __name__ == '__main__':
    main()
