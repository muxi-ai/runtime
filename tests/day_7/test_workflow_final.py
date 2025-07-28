#\!/usr/bin/env python3
"""
Final workflow test - check all conditions.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from muxi.formation.formation import Formation


async def test_workflow_final():
    """Final workflow test."""
    print("\nFinal Workflow Test")
    print("="*50)
    
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multi-agent"
    
    # Load formation
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    
    # Check all settings
    print("\nSettings check:")
    print(f"  auto_decomposition: {overlord.auto_decomposition}")
    print(f"  complexity_threshold: {overlord.complexity_threshold}")
    print(f"  workflow_config.complexity_threshold: {overlord.workflow_config.complexity_threshold}")
    print(f"  request_analyzer exists: {hasattr(overlord, 'request_analyzer')}")
    print(f"  request_analyzer.llm: {overlord.request_analyzer.llm is not None if hasattr(overlord, 'request_analyzer') else 'N/A'}")
    print(f"  request_analyzer.complexity_method: {overlord.request_analyzer.complexity_method if hasattr(overlord, 'request_analyzer') else 'N/A'}")
    
    # Test the Day 7a prompt
    prompt = 'research "ran aroussi funding gap" and write a short summary about it. save the summary as a linear issue'
    
    print(f"\nTesting prompt: '{prompt}'")
    
    # Test analyzer directly first
    if hasattr(overlord, 'request_analyzer'):
        analysis = await overlord.request_analyzer.analyze_request(prompt)
        print(f"\nDirect analysis:")
        print(f"  Complexity score: {analysis.complexity_score}")
        print(f"  Requires decomposition: {analysis.requires_decomposition}")
        print(f"  Would trigger (>= {overlord.workflow_config.complexity_threshold}): {analysis.complexity_score >= overlord.workflow_config.complexity_threshold}")
    
    # Now test the full chat
    print("\nSending chat request...")
    response = await overlord.chat(
        prompt,
        user_id="test_user",
        session_id="test_final",
        stream=False
    )
    
    # Check result
    has_workflow = hasattr(response, 'metadata') and response.metadata and 'workflow_id' in response.metadata
    print(f"\nResult:")
    print(f"  Workflow triggered: {has_workflow}")
    if has_workflow:
        print(f"  Workflow ID: {response.metadata['workflow_id']}")
    
    # Check response
    content = response.content if hasattr(response, 'content') else str(response)
    print(f"  Response length: {len(content)}")
    print(f"  Mentions 'ran aroussi': {'ran aroussi' in content.lower()}")
    print(f"  Mentions 'funding gap': {'funding gap' in content.lower()}")
    print(f"  Mentions 'linear': {'linear' in content.lower()}")
    
    # Cleanup
    await formation.stop_overlord()
    print("\n✓ Test complete")


if __name__ == "__main__":
    asyncio.run(test_workflow_final())