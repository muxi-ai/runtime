#!/usr/bin/env python3
"""
Validate all observability events against the enum.
Create CSV showing which events are missing and recommendations.
"""

import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Set

REPO_ROOT = Path(__file__).resolve().parents[1]
ENUM_CANDIDATES = [
    REPO_ROOT / "src/muxi/runtime/datatypes/observability.py",
    REPO_ROOT / "src/muxi/datatypes/observability.py",
]


def load_enum_events() -> Dict[str, Set[str]]:
    """Load all events defined in the observability enum."""
    enum_file = next((path for path in ENUM_CANDIDATES if path.exists()), ENUM_CANDIDATES[0])

    enums = {
        "SystemEvents": set(),
        "ConversationEvents": set(),
        "ErrorEvents": set(),
        "ServerEvents": set(),
        "APIEvents": set(),
    }

    content = enum_file.read_text()

    # Parse each enum class
    for enum_name in enums.keys():
        # Find the enum class definition
        pattern = rf"class {enum_name}\(Enum\):.*?(?=class |$)"
        match = re.search(pattern, content, re.DOTALL)

        if match:
            enum_content = match.group(0)
            # Find all event definitions (EVENT_NAME = "event.value")
            # Note: Include digits in pattern to match events like A2A_*
            event_pattern = r'^\s+([A-Z0-9_]+)\s*=\s*["\']([^"\']+)["\']'
            for line in enum_content.split("\n"):
                event_match = re.match(event_pattern, line)
                if event_match:
                    event_name = event_match.group(1)
                    # Skip if it's a comment line or a "# REMOVED:" comment
                    if not line.strip().startswith("#") and "# REMOVED:" not in line:
                        enums[enum_name].add(event_name)

    return enums


def extract_observe_calls(file_path: Path) -> List[Dict[str, Any]]:
    """Extract all observability.observe() calls from a Python file."""
    events = []

    try:
        content = file_path.read_text()
        lines = content.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i]

            # Look for observability.observe( calls
            if "observability.observe(" in line or "observability.emit(" in line:
                # Extract the full call (might span multiple lines)
                call_lines = [line]
                paren_count = line.count("(") - line.count(")")
                j = i + 1

                while paren_count > 0 and j < len(lines):
                    call_lines.append(lines[j])
                    paren_count += lines[j].count("(") - lines[j].count(")")
                    j += 1

                full_call = "\n".join(call_lines)

                # Extract event_type
                event_type = None
                event_enum = None

                # Pattern 1: event_type=observability.SystemEvents.EVENT_NAME
                match = re.search(
                    r"event_type\s*=\s*observability\.(SystemEvents|ConversationEvents|ErrorEvents|ServerEvents|APIEvents)\.(\w+)",
                    full_call,
                )
                if match:
                    event_enum = match.group(1)
                    event_type = match.group(2)
                else:
                    # Pattern 2: Positional first argument
                    match = re.search(
                        r"observability\.observe\(\s*observability\.(SystemEvents|ConversationEvents|ErrorEvents|ServerEvents|APIEvents)\.(\w+)",
                        full_call,
                    )
                    if match:
                        event_enum = match.group(1)
                        event_type = match.group(2)

                if event_type and event_enum:
                    # Get relative file path
                    try:
                        rel_path = str(file_path.relative_to(REPO_ROOT / "src"))
                        rel_path = f"src/{rel_path}"
                    except ValueError:
                        rel_path = str(file_path)

                    events.append(
                        {
                            "event_name": event_type,
                            "event_enum": event_enum,
                            "file": rel_path,
                            "line": i + 1,
                            "context": call_lines[0].strip()[:100],
                        }
                    )

                i = j
            else:
                i += 1

    except Exception as e:
        print(f"Error processing {file_path}: {e}")

    return events


def get_recommendation(event_name: str, event_enum: str, context: str) -> str:
    """Get recommendation for missing event."""

    # Init-related events
    init_events = {
        "AGENT_INITIALIZED": "Remove - init phase, replaced by InitEventFormatter",
        "OVERLORD_INITIALIZING": "Remove - init phase, replaced by InitEventFormatter",
        "OVERLORD_STARTED": "Remove - init phase, replaced by InitEventFormatter",
        "A2A_SERVER_STARTED": "Remove - init phase, replaced by InitEventFormatter",
        "MCP_SERVER_REGISTRATION_STARTED": "Remove - init phase, replaced by InitEventFormatter",
        "MCP_SERVER_REGISTRATION_COMPLETED": "Remove - init phase, replaced by InitEventFormatter",
        "SERVICE_INITIALIZED": "Remove or use appropriate existing event",
    }

    if event_name in init_events:
        return init_events[event_name]

    # SERVICE_STARTED - depends on context
    if event_name == "SERVICE_STARTED":
        if "workflow" in context.lower():
            return "Use OPERATION_COMPLETED or create WORKFLOW_STATE_UPDATED"
        elif "mcp" in context.lower():
            return "Remove - init phase"
        elif "agent" in context.lower():
            return "Remove - init phase"
        else:
            return "Context-dependent: use OPERATION_COMPLETED or appropriate domain event"

    # MCP events
    mcp_events = {
        "MCP_TOOL_CALL_STARTED": "Already exists - check spelling or import",
        "MCP_SERVER_CONNECTED": "Remove - init phase",
        "MCP_SERVER_CONNECTING": "Remove - init phase",
    }

    if event_name in mcp_events:
        return mcp_events[event_name]

    # Workflow events
    workflow_events = {
        "WORKFLOW_EXECUTION_STARTED": "Check if exists, may need to add",
        "AGENT_PLANNING_STARTED": "Check if exists as SystemEvents.AGENT_PLANNING_STARTED",
    }

    if event_name in workflow_events:
        return workflow_events[event_name]

    # Generic catch-all
    return f"Review: Check if similar event exists or add to {event_enum}"


def main():
    """Main validation function."""
    print("Loading enum definitions...")
    enums = load_enum_events()

    print("Found events in enums:")
    for enum_name, events in enums.items():
        print(f"  {enum_name}: {len(events)} events")

    print("\nScanning codebase for observe() calls...")
    src_dir = REPO_ROOT / "src"
    all_events = []

    for py_file in src_dir.rglob("*.py"):
        events = extract_observe_calls(py_file)
        all_events.extend(events)

    print(f"Found {len(all_events)} observe() calls")

    # Check each event against enum
    results = []
    for event in all_events:
        event_name = event["event_name"]
        event_enum = event["event_enum"]

        # Check if exists in enum
        exists = event_name in enums.get(event_enum, set())

        result = {
            "event_name": event_name,
            "enum_category": event_enum,
            "file": event["file"],
            "line": event["line"],
            "exists_in_enum": "YES" if exists else "NO",
            "recommendation": (
                "" if exists else get_recommendation(event_name, event_enum, event["context"])
            ),
            "context": event["context"],
        }
        results.append(result)

    # Sort by exists (NO first), then by event name
    results.sort(key=lambda x: (x["exists_in_enum"], x["event_name"], x["file"]))

    # Write to CSV
    output_file = "event_validation_report.csv"
    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "event_name",
                "enum_category",
                "exists_in_enum",
                "recommendation",
                "file",
                "line",
                "context",
            ],
        )
        writer.writeheader()
        writer.writerows(results)

    # Print summary
    missing = [r for r in results if r["exists_in_enum"] == "NO"]
    existing = [r for r in results if r["exists_in_enum"] == "YES"]

    print(f"\n{'='*80}")
    print("EVENT VALIDATION REPORT")
    print(f"{'='*80}")
    print(f"\nTotal observe() calls: {len(results)}")
    print(f"Events exist in enum: {len(existing)} ({len(existing)*100//len(results)}%)")
    print(f"Events MISSING from enum: {len(missing)} ({len(missing)*100//len(results)}%)")

    print("\nMissing events by type:")
    missing_by_name = {}
    for r in missing:
        name = r["event_name"]
        missing_by_name[name] = missing_by_name.get(name, 0) + 1

    for name, count in sorted(missing_by_name.items(), key=lambda x: -x[1]):
        print(f"  {name}: {count} locations")

    print(f"\nOutput file: {output_file}")
    print(f"{'='*80}\n")

    return len(missing)


if __name__ == "__main__":
    missing_count = main()
    exit(0 if missing_count == 0 else 1)
