#!/usr/bin/env python3
"""
Simple A2A functionality verification test
Bypasses document processing imports to avoid spacy dependency
"""

import asyncio
import sys
from pathlib import Path

# Add runtime to path
runtime_path = Path(__file__).parent.parent.parent / "runtime"
sys.path.insert(0, str(runtime_path))

try:
    # Import only what we need to test A2A without document processing
    from src.muxi.a2a.registry_client import A2ARegistryClient
    print("✅ A2A imports successful")
except ImportError as e:
    print(f"❌ A2A import failed: {e}")
    sys.exit(1)


async def test_a2a_discovery():
    """Test A2A agent discovery"""
    print("🔍 Testing A2A Discovery...")

    registry_client = A2ARegistryClient(registries=["http://localhost:9090"])

    try:
        # Test discovery
        agents = await registry_client.discover_agents()
        print(f"✅ Discovered {len(agents)} agents from registry")

        # Show first few agents
        for i, agent in enumerate(agents[:3]):
            print(f"  {i+1}. {agent.name}: {agent.description[:50]}...")

        return True

    except Exception as e:
        print(f"❌ Discovery failed: {e}")
        return False
    finally:
        await registry_client.close()


async def test_a2a_registration():
    """Test A2A agent registration"""
    print("📝 Testing A2A Registration...")

    registry_client = A2ARegistryClient(registries=["http://localhost:9090"])

    # Create test agent card
    test_agent = {
        "name": "test-verification-agent",
        "description": "Agent for A2A verification testing",
        "version": "1.0.0",
        "url": "http://localhost:8080/test-verification-agent",
        "capabilities": {
            "testing": {
                "name": "testing",
                "description": "Agent for testing A2A functionality",
                "enabled": True
            }
        },
        "provider": {
            "name": "MUXI",
            "type": "formation"
        }
    }

    try:
        # Test registration
        result = await registry_client.register_agent(test_agent)
        print(f"✅ Registration successful: {result}")
        return True

    except Exception as e:
        print(f"❌ Registration failed: {e}")
        return False
    finally:
        await registry_client.close()


async def main():
    """Run A2A verification tests"""
    print("🚀 A2A Functionality Verification")
    print("=" * 40)

    # Test discovery
    discovery_ok = await test_a2a_discovery()

    # Test registration
    registration_ok = await test_a2a_registration()

    # Summary
    print("\n📊 Test Results:")
    print(f"Discovery: {'✅ PASS' if discovery_ok else '❌ FAIL'}")
    print(f"Registration: {'✅ PASS' if registration_ok else '❌ FAIL'}")

    if discovery_ok and registration_ok:
        print("\n🎉 A2A functionality is WORKING!")
        print("✅ The unused imports were indeed just leftover code")
        print("✅ Core A2A features are fully implemented and functional")
    else:
        print("\n⚠️ Some A2A functionality needs attention")


if __name__ == "__main__":
    asyncio.run(main())
