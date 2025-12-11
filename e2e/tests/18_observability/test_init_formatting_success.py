"""
Test init formatting for successful formation initialization.

Tests the Linux-style init event formatting across various formation types.
All output is captured to files for visual inspection.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation

# Test formations from various e2e test suites
TEST_FORMATIONS = [
    {
        "name": "1_foundation_basic",
        "path": "e2e/tests/1_foundation/formations/formation-base/formation.afs",
        "description": "Basic foundation with single agent",
    },
    {
        "name": "2_memory_persistent",
        "path": "e2e/tests/2_memory/formations/formation-postgres/formation.afs",
        "description": "PostgreSQL persistent memory",
    },
    {
        "name": "7_multi_agent_mcp",
        "path": "e2e/tests/7_orchestration/formations/formation-multi-agent-segregated/formation.afs",
        "description": "Multi-agent with MCP servers",
    },
    {
        "name": "12_scheduling",
        "path": "e2e/tests/12_scheduling/formation-scheduling/formation.afs",
        "description": "Scheduler service enabled",
    },
]


async def test_formation_init(name: str, path: str, description: str, output_dir: Path):
    """Test a single formation initialization and capture output."""
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
            await formation.load(path)
            overlord = await formation.start_overlord()

            # Immediately stop (we only care about init)
            await formation.stop_overlord()

        # Write captured output to file
        output_content = captured_output.getvalue()
        output_file.write_text(output_content)

        print(f"✅ {name} - Success")
        print(f"   Output saved to: {output_file}")

        # Show first few lines as preview
        lines = output_content.split('\n')
        print(f"   Preview (first 10 lines):")
        for line in lines[:10]:
            if line.strip():
                print(f"     {line}")

        return True

    except Exception as e:
        print(f"❌ {name} - Failed: {e}")

        # Still write output to file if we have any
        output_content = captured_output.getvalue()
        if output_content:
            output_file.write_text(output_content)
            print(f"   Partial output saved to: {output_file}")

        import traceback
        error_file = output_dir / f"{name}_error.log"
        error_file.write_text(traceback.format_exc())
        print(f"   Error details saved to: {error_file}")

        return False


async def main():
    """Run all formation init tests."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("e2e/results") / timestamp / "18_observability_init_success"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "="*70)
    print("MUXI Init Formatting Tests - Success Scenarios")
    print(f"Output directory: {output_dir}")
    print("="*70)

    results = []
    for formation in TEST_FORMATIONS:
        success = await test_formation_init(
            formation["name"],
            formation["path"],
            formation["description"],
            output_dir
        )
        results.append((formation["name"], success))

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

    print(f"\nResults: {passed}/{total} formations initialized successfully")
    print(f"All outputs saved to: {output_dir}")
    print("="*70 + "\n")

    # Create summary file
    summary_file = output_dir / "summary.txt"
    with open(summary_file, 'w') as f:
        f.write("MUXI Init Formatting Tests - Success Scenarios\n")
        f.write("="*70 + "\n\n")
        for name, success in results:
            status = "PASS" if success else "FAIL"
            f.write(f"{status}: {name}\n")
        f.write(f"\nTotal: {passed}/{total} passed\n")

    return 0 if passed == total else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
