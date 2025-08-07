#!/usr/bin/env python3
"""
Day 7C Test: SOP Template System
Tests the SOP system's ability to load, index, and convert SOPs to workflows.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from muxi.formation.overlord.sops import SOPSystem  # noqa: E402


async def test_sop_templates():
    """Test SOP template system functionality."""
    print("🧪 Day 7C: Testing SOP Template System")
    print("=" * 60)

    # Use test formation with SOPs
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multi-agent"

    # Create SOP system
    sop_system = SOPSystem(formation_path)

    # Test 1: SOP Loading
    print("\n✅ Test 1: SOP Loading")
    assert sop_system.enabled, "SOP system should be enabled"
    assert len(sop_system.sops) == 3, f"Expected 3 SOPs, found {len(sop_system.sops)}"
    print(f"  ✓ Loaded {len(sop_system.sops)} SOPs")

    # Test 2: Resource Map
    print("\n✅ Test 2: Resource Map")
    assert len(sop_system.resource_map) > 0, "Resource map should not be empty"
    print(f"  ✓ Mapped {len(sop_system.resource_map)} resources")

    # Test 3: Directive Extraction
    print("\n✅ Test 3: Directive Extraction")
    incident_sop = sop_system.sops.get('incident-response')
    assert incident_sop, "Should have incident-response SOP"
    assert len(incident_sop['steps']) == 5, f"Expected 5 steps, found {len(incident_sop['steps'])}"

    # Check directives in first step
    first_step = incident_sop['steps'][0]
    assert first_step['agent'] == 'monitoring-specialist', "First step should have monitoring-specialist agent"
    assert 'datadog' in first_step['mcp_tools'], "First step should have datadog MCP tool"
    assert 'references/severity-matrix.md' in first_step['resources'], "First step should have severity-matrix resource"
    print("  ✓ Directives extracted correctly")

    # Test 4: Resource Resolution
    print("\n✅ Test 4: Resource Resolution")
    test_refs = [
        'templates/incident-report.md',
        'references/severity-matrix.md',
        'escalation-tree.md'
    ]

    for ref in test_refs:
        path = sop_system.resolve_resource(ref)
        assert path is not None, f"Should resolve {ref}"
        assert path.exists(), f"Resolved path should exist: {path}"
    print("  ✓ All resources resolved correctly")

    # Test 5: Workflow Template Conversion
    print("\n✅ Test 5: Workflow Template Conversion")
    workflow_tasks = sop_system.to_workflow_template(incident_sop)
    assert len(workflow_tasks) == 5, f"Expected 5 workflow tasks, got {len(workflow_tasks)}"

    # Check first task
    first_task = workflow_tasks[0]
    assert first_task['preferred_agent'] == 'monitoring-specialist'
    assert 'datadog' in first_task['required_tools']
    assert len(first_task['resources']) > 0
    print("  ✓ SOP converted to workflow template")

    # Test 6: Tag-based Search
    print("\n✅ Test 6: Tag-based Search")
    results = sop_system._find_by_tags("production incident critical", top_k=2)
    assert len(results) > 0, "Should find SOPs with matching tags"
    assert results[0]['id'] == 'incident-response', "First result should be incident-response"
    print(f"  ✓ Found {len(results)} SOPs via tag search")

    # Test 7: Guide Mode SOP
    print("\n✅ Test 7: Guide Mode SOP")
    review_sop = sop_system.sops.get('code-review')
    assert review_sop, "Should have code-review SOP"
    assert review_sop['mode'] == 'guide', "Code review should be in guide mode"

    # Format as guidance
    guidance = sop_system.format_as_guidance(review_sop)
    assert "Standard Operating Procedure" in guidance
    assert "senior-developer" in guidance
    print("  ✓ Guide mode SOP formatted correctly")

    # Test 8: Resource Content Loading (mock)
    print("\n✅ Test 8: Resource Content Loading")
    content = await sop_system.get_resource_content('templates/incident-report.md')
    assert content is not None, "Should load resource content"
    assert "Incident Report Template" in content
    print("  ✓ Resource content loaded successfully")

    print("\n" + "=" * 60)
    print("✅ All Day 7C tests passed!")
    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_sop_templates())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
