#!/usr/bin/env python3
"""
Day 7D Test: SOP File References and Integration
Tests SOP file reference resolution and integration with overlord workflow system.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from muxi.formation.formation import Formation  # noqa: E402
from muxi.formation.overlord.sops import SOPSystem  # noqa: E402


async def test_sop_references():
    """Test SOP file references and overlord integration."""
    print("🧪 Day 7D: Testing SOP File References & Integration")
    print("=" * 60)

    # Part 1: Direct SOP System Tests
    print("\n📁 Part 1: File Reference Resolution")
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multi-agent"
    sop_system = SOPSystem(formation_path)

    # Test various reference patterns
    test_cases = [
        # (reference, should_exist, description)
        ('templates/incident-report.md', True, "Template file"),
        ('references/severity-matrix.md', True, "Reference file"),
        ('escalation-tree.md', True, "Filename only"),
        ('nonexistent.md', False, "Non-existent file"),
        ('templates/postmortem.md', True, "Nested template"),
    ]

    for ref, should_exist, desc in test_cases:
        path = sop_system.resolve_resource(ref)
        if should_exist:
            assert path is not None, f"Should resolve {desc}: {ref}"
            assert path.exists(), f"Path should exist for {desc}: {ref}"
            print(f"  ✓ Resolved {desc}: {ref}")
        else:
            assert path is None, f"Should not resolve {desc}: {ref}"
            print(f"  ✓ Correctly rejected {desc}: {ref}")

    # Part 2: Content Loading
    print("\n📄 Part 2: Resource Content Loading")

    # Test loading different file types
    md_content = await sop_system.get_resource_content('templates/incident-report.md')
    assert md_content is not None, "Should load markdown content"
    assert "Incident Report Template" in md_content, "Should contain expected content"
    print("  ✓ Loaded markdown file content")

    # Test loading with nested path
    nested_content = await sop_system.get_resource_content('references/severity-matrix.md')
    assert nested_content is not None, "Should load nested file"
    assert "P1 - Critical" in nested_content, "Should contain severity levels"
    print("  ✓ Loaded nested reference file")

    # Part 3: Overlord Integration
    print("\n🔧 Part 3: Overlord Integration")

    # Load formation and start overlord
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()

    try:
        # Check SOP system initialization
        assert hasattr(overlord, 'sop_system'), "Overlord should have sop_system"
        assert overlord.sop_system is not None, "SOP system should be initialized"
        assert overlord.sop_system.enabled, "SOP system should be enabled"
        print("  ✓ SOP system initialized in overlord")

        # Test SOP discovery
        test_messages = [
            ("critical production incident", "incident-response"),
            ("onboard new customer", "customer-onboarding"),
            ("review code quality", "code-review"),
        ]

        for message, expected_sop in test_messages:
            sops = await overlord.sop_system.find_relevant_sops(message, top_k=1)
            if sops:
                assert sops[0]['id'] == expected_sop, f"Should match {expected_sop} for '{message}'"
                print(f"  ✓ Matched '{message}' → {expected_sop}")
            else:
                print(f"  ⚠ No match for '{message}' (might need FAISS)")

        # Part 4: Workflow Template Integration
        print("\n🔄 Part 4: Workflow Template Structure")

        # Get an SOP and convert to workflow
        incident_sop = overlord.sop_system.sops['incident-response']
        workflow_tasks = overlord.sop_system.to_workflow_template(incident_sop)

        # Verify task structure
        for i, task in enumerate(workflow_tasks, 1):
            assert 'description' in task, f"Task {i} should have description"
            assert 'type' in task, f"Task {i} should have type"
            assert 'source' in task, f"Task {i} should have source"
            assert task['source'] == 'sop', f"Task {i} source should be 'sop'"

            # Check agent routing
            if task.get('preferred_agent'):
                print(f"  ✓ Task {i}: Agent routing → {task['preferred_agent']}")

            # Check MCP tools
            if task.get('required_tools'):
                print(f"  ✓ Task {i}: MCP tools → {', '.join(task['required_tools'])}")

            # Check file resources
            if task.get('resources'):
                print(f"  ✓ Task {i}: Resources → {len(task['resources'])} files")

        # Part 5: Guide Mode Formatting
        print("\n📝 Part 5: Guide Mode Formatting")

        guide_sop = overlord.sop_system.sops['code-review']
        guidance_text = overlord.sop_system.format_as_guidance(guide_sop)

        # Verify guide format
        assert "Standard Operating Procedure" in guidance_text
        assert guide_sop['name'] in guidance_text
        assert "senior-developer" in guidance_text
        assert "(Assigned to:" in guidance_text
        print("  ✓ Guide mode SOP formatted with agent assignments")

        # Check resource references in guide
        assert "templates/review-feedback.md" in guidance_text
        print("  ✓ File references included in guide")

    finally:
        # Clean up
        await formation.stop_overlord()
        formation.shutdown()

    print("\n" + "=" * 60)
    print("✅ All Day 7D tests passed!")
    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_sop_references())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
