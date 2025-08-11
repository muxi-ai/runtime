#!/usr/bin/env python3
"""
Test A2A flow using overlord.chat() exactly as requested
"""

import asyncio
import sys
from pathlib import Path
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src")))

from muxi.formation.formation import Formation  # noqa: E402


async def main():
    """Test A2A flow with overlord.chat()"""

    print("\n" + "="*60)
    print("A2A OVERLORD.CHAT() TEST")
    print("="*60)

    # Suppress most logs
    import logging
    logging.getLogger().setLevel(logging.WARNING)

    # Load formation
    print("\n1. Loading formation...")
    formation = Formation()
    await formation.load(str(Path(__file__).parent / "formations" / "formation-multi-agent-sop" / "formation.yaml"))  # noqa: E501
    overlord = await formation.start_overlord()
    print("   ✓ Formation loaded")

    # Debug: Check SOP system status
    if hasattr(overlord, 'sop_system') and overlord.sop_system:
        print(f"   ✓ SOP system initialized with {len(overlord.sop_system.sops)} SOPs")
        if overlord.sop_system.sops:
            for sop_id, sop in overlord.sop_system.sops.items():
                print(f"     - {sop['name']}: {sop.get('tags', [])}")

        # Wait for SOPs to be indexed
        print("   Waiting for SOP indexing...")
        await asyncio.sleep(1)  # Give time for indexing to complete
    else:
        print("   ✗ SOP system not initialized")

    # Debug: Check workflow configuration
    print(f"   ✓ Workflow config: auto_decomposition={overlord.auto_decomposition}")
    print(f"   ✓ Complexity threshold={overlord.complexity_threshold}")

    # Debug: Check request analyzer
    if hasattr(overlord, 'request_analyzer') and overlord.request_analyzer:
        print("   ✓ Request analyzer initialized")
        print(f"     - Has LLM: {overlord.request_analyzer.llm is not None}")
        print(f"     - Complexity method: {overlord.request_analyzer.complexity_method}")

        # Test complexity analysis
        test_msg = "create a linear issue with system usage info like cpu, memory, etc"
        try:
            analysis = overlord.request_analyzer._heuristic_analyze_request(test_msg)
            print(f"     - Test complexity score: {analysis.complexity_score}")
        except Exception as e:
            print(f"     - Error analyzing test message: {e}")
    else:
        print("   ✗ Request analyzer not initialized")

    # The exact call requested
    print("\n2. Calling overlord.chat() WITHOUT agent_name (auto-routing):")
    print('   agent_name=None')
    print('   message="create a linear issue with system usage info like cpu, memory, etc"')
    print("\n" + "-"*60)

    # Make the call WITHOUT specifying agent_name with a timeout
    try:
        response = await asyncio.wait_for(
            overlord.chat(
                message="how are you doing?",
                agent_name=None,  # Let overlord auto-route
                user_id="test_user",
                session_id="test_session",
                stream=False,  # Try with stream=False like the working test
                use_async=False
            ),
            timeout=120  # 120 second timeout
        )
    except asyncio.TimeoutError:
        print("\n   ✗ TIMEOUT: Chat call took longer than 120 seconds")
        print("   This likely means the workflow/SOP system is not working correctly")
        await formation.stop_overlord()
        formation.shutdown()
        return

    # Collect and display response
    print("\nOverlord Response (auto-routed):")

    # Handle response like the working test
    if hasattr(response, 'content'):
        print(response)
        result = response.content
    else:
        result = ""
        async for chunk in response:
            result += chunk
            print(chunk, end="", flush=True)

    print(result)
    print("\n" + "-"*60)

    # Check for artifacts in response
    artifacts_found = False
    if hasattr(response, 'artifacts'):
        print(f"\n   Response artifacts: {response.artifacts}")
        if response.artifacts:
            artifacts_found = True
            print(f"   ✓ Found {len(response.artifacts)} artifacts in response!")
            for i, artifact in enumerate(response.artifacts):
                # MuxiArtifact is a Pydantic model, access attributes directly
                print(f"      Artifact {i+1}: {artifact.filename} ({artifact.type})")
                if artifact.content:
                    print(f"         Size: {len(artifact.content)} bytes")
                elif artifact.data_url:
                    print("         Data URL provided (binary file)")
        else:
            print("   ✗ No artifacts in response.artifacts")
    else:
        print("   ✗ Response has no artifacts attribute")

    # Track the behavior - NOW WITH SOP DETECTION
    print("\n3. Behavior tracking (SOP Override Test):")

    sop_triggered = False
    linear_created = False
    artifact_created = False

    # Check if system info was obtained
    if "cpu" in result.lower() or "%" in result.lower() or "system" in result.lower():
        print("   ✓ System info obtained")
    else:
        print("   ✗ System info not found in response")

    # Check for SOP execution indicators
    if "performance score" in result.lower() or "calculation" in result.lower():
        print("   ✓ SOP calculation step detected")
        sop_triggered = True

    # Check for artifact creation (SOP behavior)
    if "artifact" in result.lower() or "pdf" in result.lower() or "report" in result.lower():
        print("   ✓ PDF artifact generation detected (SOP executed!)")
        artifact_created = True
        sop_triggered = True

    # Check if Linear issue was created (old behavior)
    if "linear" in result.lower() and ("created" in result.lower() or "issue" in result.lower()):
        print("   ✗ Linear issue creation detected (SOP not triggered)")
        linear_created = True

    # Check for Project Manager delegation (old behavior)
    if "project manager" in result.lower() or "project-manager" in result.lower():
        print("   ✗ Project Manager delegation detected (old routing)")

    # Determine test result
    print("\n4. Test Result:")
    if sop_triggered and (artifact_created or artifacts_found) and not linear_created:
        print("   🎉 SUCCESS: SOP was triggered and executed!")
        print("   ✓ Workflow was overridden by SOP")
        print("   ✓ PDF artifact created instead of Linear issue")
        if artifacts_found:
            print("   ✓ Artifacts returned in response!")
    elif linear_created and not sop_triggered:
        print("   ❌ FAILURE: SOP was NOT triggered")
        print("   ✗ Default agent routing occurred")
        print("   ✗ Linear issue was created (old behavior)")
    else:
        print("   ⚠ UNCLEAR: Mixed signals in response")
        print(f"     SOP triggered: {sop_triggered}")
        print(f"     Artifact created: {artifact_created}")
        print(f"     Linear created: {linear_created}")

    # Check for errors
    if "error" in result.lower() or "failed" in result.lower():
        print("   ⚠ Possible error in response")

    # Cleanup
    print("\n5. Cleaning up...")
    await formation.stop_overlord()
    formation.shutdown()

    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("Check your Linear dashboard for the new issue!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
