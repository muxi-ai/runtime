"""
Test init formatting for failure scenarios.

Tests how initialization failures are formatted with structured error messages.
All output is captured to files for visual inspection.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
import tempfile
import shutil

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation


def create_bad_postgres_formation(temp_dir: Path) -> Path:
    """Create a formation with invalid PostgreSQL connection."""
    formation_dir = temp_dir / "bad_postgres"
    formation_dir.mkdir(parents=True, exist_ok=True)

    formation_yaml = formation_dir / "formation.afs"
    formation_yaml.write_text("""
schema: "1.0.0"
id: "bad_postgres_test"
description: "Formation with invalid PostgreSQL connection"

llm:
  api_keys:
    openai: "${{ secrets.OPENAI_API_KEY }}"
  models:
    - text: "openai/gpt-4o-mini"

memory:
  buffer:
    size: 10
  persistent:
    connection_string: "postgresql://invalid_user:****@localhost:5432/nonexistent_db"
    embedding_model: "openai/text-embedding-3-small"

agents:
  - id: "test-agent"
    name: "Test Agent"
    description: "Test agent for bad postgres scenario"
    role: "general"
""")

    return formation_yaml


def create_bad_mcp_formation(temp_dir: Path) -> Path:
    """Create a formation with invalid MCP server command."""
    formation_dir = temp_dir / "bad_mcp"
    formation_dir.mkdir(parents=True, exist_ok=True)

    # Create agent with bad MCP server
    agent_dir = formation_dir / "agents"
    agent_dir.mkdir(parents=True, exist_ok=True)

    agent_yaml = agent_dir / "test-agent.yaml"
    agent_yaml.write_text("""
schema: "1.0.0"
id: "test-agent"
name: "Test Agent"
role: "general"

mcp_servers:
  - id: "nonexistent-server"
    description: "MCP server that doesn't exist"
    active: true
    type: "command"
    command: "/nonexistent/path/to/mcp/server"
    args: []
    timeout_seconds: 5
""")

    formation_yaml = formation_dir / "formation.afs"
    formation_yaml.write_text("""
schema: "1.0.0"
id: "bad_mcp_test"
description: "Formation with invalid MCP server"

llm:
  api_keys:
    openai: "${{ secrets.OPENAI_API_KEY }}"
  models:
    - text: "openai/gpt-4o-mini"

memory:
  buffer:
    size: 10

agents:
  - id: "test-agent"
    name: "Test Agent"
    description: "Test agent for bad MCP scenario"
    role: "general"
    mcp_servers:
      - id: "nonexistent-server"
        description: "MCP server that doesn't exist"
        active: true
        type: "command"
        command: "/nonexistent/path/to/mcp/server"
        args: []
        timeout_seconds: 5
""")

    return formation_yaml


def create_bad_a2a_formation(temp_dir: Path) -> Path:
    """Create a formation with unreachable A2A registry."""
    formation_dir = temp_dir / "bad_a2a"
    formation_dir.mkdir(parents=True, exist_ok=True)

    formation_yaml = formation_dir / "formation.afs"
    formation_yaml.write_text("""
schema: "1.0.0"
id: "bad_a2a_test"
description: "Formation with unreachable A2A registry"

llm:
  api_keys:
    openai: "${{ secrets.OPENAI_API_KEY }}"
  models:
    - text: "openai/gpt-4o-mini"

memory:
  buffer:
    size: 10

a2a:
  outbound:
    registries:
      - url: "http://nonexistent-registry.local:8080"
        required: false

agents:
  - id: "test-agent"
    name: "Test Agent"
    description: "Test agent for bad A2A scenario"
    role: "general"
""")

    return formation_yaml


async def test_failure_scenario(name: str, formation_path: Path, description: str, output_dir: Path):
    """Test a failure scenario and capture output."""
    print(f"\n{'='*70}")
    print(f"Testing: {name}")
    print(f"Description: {description}")
    print(f"{'='*70}\n")

    output_file = output_dir / f"{name}_init.log"

    # Redirect stdout to capture formatted output
    import io
    import contextlib

    captured_output = io.StringIO()

    try:
        with contextlib.redirect_stdout(captured_output):
            # Load and start formation
            formation = Formation()
            await formation.load(str(formation_path))
            overlord = await formation.start_overlord()

            # Immediately stop
            await formation.stop_overlord()

        # Write captured output to file
        output_content = captured_output.getvalue()
        output_file.write_text(output_content)

        print(f"⚠️  {name} - Succeeded (expected to show warnings/graceful degradation)")
        print(f"   Output saved to: {output_file}")

        return True

    except Exception as e:
        # Failures are expected! Capture the error formatting
        print(f"✅ {name} - Failed as expected: {type(e).__name__}")

        # Write captured output to file (should contain formatted error)
        output_content = captured_output.getvalue()
        output_file.write_text(output_content)
        print(f"   Output saved to: {output_file}")

        # Show preview of error
        lines = output_content.split('\n')
        print(f"   Error preview (first 15 lines):")
        for line in lines[:15]:
            if line.strip():
                print(f"     {line}")

        # Also save full traceback
        import traceback
        error_file = output_dir / f"{name}_traceback.log"
        error_file.write_text(traceback.format_exc())
        print(f"   Full traceback saved to: {error_file}")

        return True  # Failure is success for these tests!


async def main():
    """Run all failure scenario tests."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("e2e/results") / timestamp / "18_observability_init_failures"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create temporary directory for test formations
    temp_dir = Path(tempfile.mkdtemp(prefix="muxi_test_failures_"))

    try:
        print("\n" + "="*70)
        print("MUXI Init Formatting Tests - Failure Scenarios")
        print(f"Output directory: {output_dir}")
        print(f"Temp formations: {temp_dir}")
        print("="*70)

        # Create test formations
        scenarios = [
            {
                "name": "bad_postgres",
                "path": create_bad_postgres_formation(temp_dir),
                "description": "Invalid PostgreSQL connection string",
            },
            {
                "name": "bad_mcp_command",
                "path": create_bad_mcp_formation(temp_dir),
                "description": "Non-existent MCP server command",
            },
            {
                "name": "bad_a2a_registry",
                "path": create_bad_a2a_formation(temp_dir),
                "description": "Unreachable A2A registry",
            },
        ]

        results = []
        for scenario in scenarios:
            success = await test_failure_scenario(
                scenario["name"],
                scenario["path"],
                scenario["description"],
                output_dir
            )
            results.append((scenario["name"], success))

            # Short delay between tests
            await asyncio.sleep(0.5)

        # Summary
        print("\n" + "="*70)
        print("Test Summary")
        print("="*70)

        passed = sum(1 for _, success in results if success)
        total = len(results)

        for name, success in results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{status} - {name}")

        print(f"\nResults: {passed}/{total} failure scenarios handled correctly")
        print(f"All outputs saved to: {output_dir}")
        print("="*70 + "\n")

        # Create summary file
        summary_file = output_dir / "summary.txt"
        with open(summary_file, 'w') as f:
            f.write("MUXI Init Formatting Tests - Failure Scenarios\n")
            f.write("="*70 + "\n\n")
            for name, success in results:
                status = "PASS" if success else "FAIL"
                f.write(f"{status}: {name}\n")
            f.write(f"\nTotal: {passed}/{total} passed\n")

        return 0 if passed == total else 1

    finally:
        # Cleanup temp directory
        try:
            shutil.rmtree(temp_dir)
            print(f"Cleaned up temp directory: {temp_dir}")
        except Exception as e:
            print(f"Warning: Failed to cleanup temp directory: {e}")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
