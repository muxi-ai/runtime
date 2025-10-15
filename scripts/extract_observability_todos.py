#!/usr/bin/env python3
"""
Extract and categorize observability TODO comments from the MUXI Runtime codebase.

This script finds all "TODO: add observability" or "TODO.*observability" comments,
extracts context, and categorizes them into System/Error vs Conversation events.
"""

import re
import os
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict
import json
import csv


@dataclass
class ObservabilityTODO:
    """Represents a single TODO observability comment."""
    file_path: str
    line_number: int
    comment: str
    context_before: List[str]
    context_after: List[str]
    category: str = "UNCATEGORIZED"  # System/Error, Conversation, or UNCATEGORIZED
    priority: str = "MEDIUM"  # HIGH, MEDIUM, LOW
    component: str = ""  # MCP, A2A, Database, Memory, etc.


class TODOExtractor:
    """Extract and categorize observability TODOs."""

    # Patterns to identify System/Error events (infrastructure, not user-request related)
    SYSTEM_ERROR_PATTERNS = [
        r'auth',  # Authentication
        r'credential',  # Credentials
        r'connection',  # Network connections
        r'disconnect',  # Disconnections
        r'timeout',  # Timeouts
        r'failure',  # Failures
        r'error',  # Generic errors
        r'retry',  # Retry logic
        r'fallback',  # Fallback handling
        r'circuit.*breaker',  # Circuit breaker
        r'health.*check',  # Health checks
        r'resource',  # Resource management
        r'limit',  # Rate limiting, resource limits
        r'webhook.*fail',  # Webhook failures
        r'scheduler.*fail',  # Scheduler failures
        r'database.*fail',  # Database failures
        r'mcp.*fail',  # MCP failures
        r'a2a.*fail',  # A2A failures
    ]

    # Patterns to identify Conversation events (request lifecycle)
    CONVERSATION_PATTERNS = [
        r'request.*received',  # Request ingestion
        r'clarification',  # Clarification system
        r'agent.*select',  # Agent selection
        r'workflow.*decomp',  # Workflow decomposition
        r'response.*gen',  # Response generation
        r'memory.*update',  # Memory updates
        r'memory.*extract',  # Memory extraction
        r'persona.*appl',  # Persona application
        r'routing',  # Request routing
        r'processing.*start',  # Processing started
        r'processing.*complete',  # Processing completed
    ]

    # Component mappings from file paths
    COMPONENT_MAP = {
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

    def __init__(self, src_dir: Path):
        self.src_dir = src_dir
        self.todos: List[ObservabilityTODO] = []

    def extract_todos(self) -> List[ObservabilityTODO]:
        """Extract all observability TODOs from Python files."""
        print(f"Scanning {self.src_dir} for observability TODOs...")

        for py_file in self.src_dir.rglob("*.py"):
            self._extract_from_file(py_file)

        print(f"Found {len(self.todos)} observability TODOs")
        return self.todos

    def _extract_from_file(self, file_path: Path):
        """Extract TODOs from a single file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            for i, line in enumerate(lines):
                # Look for TODO comments with "observability"
                if re.search(r'#.*TODO.*observability', line, re.IGNORECASE):
                    # Extract context (3 lines before/after)
                    context_before = lines[max(0, i-3):i]
                    context_after = lines[i+1:min(len(lines), i+4)]

                    todo = ObservabilityTODO(
                        file_path=str(file_path.relative_to(self.src_dir.parent)),
                        line_number=i + 1,
                        comment=line.strip(),
                        context_before=[l.strip() for l in context_before],
                        context_after=[l.strip() for l in context_after],
                    )

                    # Categorize
                    self._categorize_todo(todo)
                    self.todos.append(todo)

        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    def _categorize_todo(self, todo: ObservabilityTODO):
        """Categorize TODO as System/Error or Conversation."""
        # Combine comment and context for analysis
        text = (
            todo.comment + " " +
            " ".join(todo.context_before) + " " +
            " ".join(todo.context_after)
        ).lower()

        # Check for System/Error patterns
        system_score = sum(
            1 for pattern in self.SYSTEM_ERROR_PATTERNS
            if re.search(pattern, text, re.IGNORECASE)
        )

        # Check for Conversation patterns
        conversation_score = sum(
            1 for pattern in self.CONVERSATION_PATTERNS
            if re.search(pattern, text, re.IGNORECASE)
        )

        # Categorize based on scores
        if system_score > conversation_score:
            todo.category = "System/Error"
        elif conversation_score > system_score:
            todo.category = "Conversation"
        else:
            todo.category = "UNCATEGORIZED"

        # Determine component
        for key, component in self.COMPONENT_MAP.items():
            if key in todo.file_path.lower():
                todo.component = component
                break

        # Prioritize auth and infrastructure failures
        if any(pattern in text for pattern in ['auth', 'credential', 'connection.*fail', 'disconnect']):
            todo.priority = "HIGH"
        elif any(pattern in text for pattern in ['timeout', 'retry', 'fallback']):
            todo.priority = "MEDIUM"
        else:
            todo.priority = "LOW"

    def export_to_json(self, output_file: Path):
        """Export TODOs to JSON."""
        data = {
            "total": len(self.todos),
            "by_category": self._count_by_category(),
            "by_component": self._count_by_component(),
            "by_priority": self._count_by_priority(),
            "todos": [asdict(todo) for todo in self.todos]
        }

        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"Exported to {output_file}")

    def export_to_csv(self, output_file: Path):
        """Export TODOs to CSV for manual review."""
        with open(output_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'file_path', 'line_number', 'component', 'category',
                'priority', 'comment'
            ])
            writer.writeheader()

            for todo in self.todos:
                writer.writerow({
                    'file_path': todo.file_path,
                    'line_number': todo.line_number,
                    'component': todo.component,
                    'category': todo.category,
                    'priority': todo.priority,
                    'comment': todo.comment[:100],  # Truncate long comments
                })

        print(f"Exported to {output_file}")

    def print_summary(self):
        """Print summary statistics."""
        print("\n" + "="*60)
        print("OBSERVABILITY TODO SUMMARY")
        print("="*60)

        print(f"\nTotal TODOs: {len(self.todos)}")

        print("\nBy Category:")
        for category, count in sorted(self._count_by_category().items()):
            print(f"  {category}: {count}")

        print("\nBy Component:")
        for component, count in sorted(self._count_by_component().items(), key=lambda x: -x[1]):
            print(f"  {component}: {count}")

        print("\nBy Priority:")
        for priority, count in sorted(self._count_by_priority().items()):
            print(f"  {priority}: {count}")

        print("\n" + "="*60)

    def _count_by_category(self) -> Dict[str, int]:
        """Count TODOs by category."""
        counts = {}
        for todo in self.todos:
            counts[todo.category] = counts.get(todo.category, 0) + 1
        return counts

    def _count_by_component(self) -> Dict[str, int]:
        """Count TODOs by component."""
        counts = {}
        for todo in self.todos:
            component = todo.component or "Unknown"
            counts[component] = counts.get(component, 0) + 1
        return counts

    def _count_by_priority(self) -> Dict[str, int]:
        """Count TODOs by priority."""
        counts = {}
        for todo in self.todos:
            counts[todo.priority] = counts.get(todo.priority, 0) + 1
        return counts


def main():
    """Main entry point."""
    # Get runtime directory
    script_dir = Path(__file__).parent
    runtime_dir = script_dir.parent
    src_dir = runtime_dir / "src" / "muxi"

    if not src_dir.exists():
        print(f"Error: Source directory not found: {src_dir}")
        return

    # Extract TODOs
    extractor = TODOExtractor(src_dir)
    todos = extractor.extract_todos()

    # Print summary
    extractor.print_summary()

    # Export results
    output_dir = runtime_dir
    extractor.export_to_json(output_dir / "observability_todos.json")
    extractor.export_to_csv(output_dir / "observability_todos.csv")

    print("\n✅ TODO extraction complete!")
    print(f"   - JSON: {output_dir / 'observability_todos.json'}")
    print(f"   - CSV: {output_dir / 'observability_todos.csv'}")


if __name__ == "__main__":
    main()
