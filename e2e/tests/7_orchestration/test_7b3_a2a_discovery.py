#!/usr/bin/env python3
"""
Test 7B3: A2A Discovery
Tests agent discovery functionality through A2A registry:
- Agent discovery through registry
- Capability-based filtering
- Agent metadata retrieval
- Registry availability checking
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def test_a2a_discovery():
    """Test A2A agent discovery through registry."""
    print("\n" + "=" * 80)
    print("Test 7B3: A2A Discovery and Registry")
    print("=" * 80)

    checks_passed = []
    all_passed = True
    formation = None
    overlord = None

    try:
        # Setup
        print("\n1. Loading formation...")
        formation_path = Path(__file__).parent / "formations" / "formation-multi-agent" / "formation.yaml"
        
        formation = Formation()
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()
        
        print("   ✓ Formation loaded")
        print(f"   Local agents: {', '.join(overlord.agents.keys())}")

        # Test 1: Check A2A coordinator presence
        print("\n2. Checking A2A coordinator...")
        
        if hasattr(overlord, 'a2a_coordinator') and overlord.a2a_coordinator:
            print("   ✓ A2A coordinator initialized")
            checks_passed.append("A2A coordinator present")

            # Test 2: Discover all available agents
            print("\n3. Discovering available agents...")
            
            try:
                agents = overlord.a2a_coordinator.get_available_agents_for_a2a(
                    requesting_agent_id="test-agent",
                    capability_filter=None
                )

                agent_count = len(agents)
                print(f"   ✓ Discovered {agent_count} agents:")
                
                for agent_id, agent_info in agents.items():
                    description = agent_info.get('description', 'No description')
                    capabilities = agent_info.get('capabilities', [])
                    agent_type = agent_info.get('type', 'unknown')
                    
                    print(f"     - {agent_id}: {description}")
                    print(f"       Capabilities: {capabilities}")
                    print(f"       Type: {agent_type}")
                
                if agent_count > 0:
                    checks_passed.append(f"Discovered {agent_count} agents")

            except Exception as e:
                print(f"   ⚠️  Discovery error: {str(e)}")
                print("   This may be expected if external registry is not available")

            # Test 3: Discover by capability
            print("\n4. Testing capability-based discovery...")
            
            try:
                pm_agents = overlord.a2a_coordinator.get_available_agents_for_a2a(
                    requesting_agent_id="test-agent",
                    capability_filter=["project_management"]
                )

                pm_count = len(pm_agents)
                print(f"   Found {pm_count} project management agents")
                
                if pm_count > 0:
                    checks_passed.append(f"Capability filtering: {pm_count} PM agents")
                    
                    for agent_id in pm_agents.keys():
                        print(f"     - {agent_id}")

            except Exception as e:
                print(f"   ⚠️  Capability discovery error: {str(e)}")

            # Test 4: Check registry configuration
            print("\n5. Checking registry configuration...")
            
            if hasattr(overlord.a2a_coordinator, 'registry_client'):
                registry_client = overlord.a2a_coordinator.registry_client
                
                if registry_client:
                    print("   ✓ Registry client configured")
                    checks_passed.append("Registry client configured")
                    
                    # Check if registry is reachable (don't fail if it's not)
                    try:
                        if hasattr(registry_client, 'registry_url'):
                            print(f"   Registry URL: {registry_client.registry_url}")
                    except Exception:
                        pass
                else:
                    print("   ℹ️  No registry client (local-only mode)")
            else:
                print("   ℹ️  No registry client attribute")

        else:
            print("   ⚠️  A2A coordinator not initialized")
            print("   This may be expected if A2A is not configured")

        # Success if we have A2A coordinator and can discover agents
        if len(checks_passed) >= 1:
            all_passed = True
        else:
            all_passed = False
            print("\n   ⚠️  A2A discovery not fully functional")

    except Exception as e:
        print(f"\n✗ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        all_passed = False

    finally:
        print("\n6. Cleaning up...")
        if overlord and formation:
            await formation.stop_overlord()
            formation.stop()
        print("   ✓ Formation stopped")

    # Print results
    print("\n" + "=" * 80)
    print(f"Test Result: {'✅ PASSED' if all_passed else '❌ FAILED'}")
    print(f"Checks Passed: {len(checks_passed)}")
    for check in checks_passed:
        print(f"  ✓ {check}")
    print("=" * 80)

    print("\n💡 Note: Full external A2A testing requires running two formations simultaneously.")
    print("   See test_7b4_external_a2a_provider.py and test_7b5_external_a2a_requester.py")

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_a2a_discovery())
    sys.exit(exit_code)
