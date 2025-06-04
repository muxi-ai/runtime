#!/usr/bin/env python3
"""
Test New A2A Schema Format

This test verifies that the new a2a.server.* schema format works correctly
after updating from the old allow_external format.
"""

import asyncio
import sys

# Add the runtime directory to Python path
sys.path.insert(0, '../runtime')

from muxi.runtime.overlord import Overlord  # noqa: E402
from muxi.runtime.llm import LLM  # noqa: E402


async def test_new_schema_format():
    """Test the new a2a.server schema format"""

    print("🧪 Testing New A2A Schema Format")
    print("=" * 50)

    # Test 1: Server enabled
    print("\n✅ Test 1: Server enabled = True")
    formation_config_enabled = {
        "name": "test-formation",
        "a2a": {
            "registries": ["http://localhost:9090"],
            "server": {
                "enabled": True,
                "port": 8181,
                "trusted_endpoints": ["localhost"],
                "mode": "none"
            }
        }
    }

    model = LLM(
        model="gpt-4o-mini",
        api_key="test-key",
        temperature=0.7
    )

    overlord_enabled = Overlord(formation_config=formation_config_enabled)
    print(
        f"  - External registry client created: "
        f"{overlord_enabled.external_registry_client is not None}"
    )

    # Test 2: Server disabled
    print("\n❌ Test 2: Server enabled = False")
    formation_config_disabled = {
        "name": "test-formation",
        "a2a": {
            "registries": ["http://localhost:9090"],
            "server": {
                "enabled": False,
                "port": 8181,
                "trusted_endpoints": ["localhost"],
                "mode": "none"
            }
        }
    }

    overlord_disabled = Overlord(formation_config=formation_config_disabled)
    print(
        f"  - External registry client created: "
        f"{overlord_disabled.external_registry_client is not None}"
    )

    # Test 3: Default behavior (no server config)
    print("\n🔄 Test 3: No server config (default)")
    formation_config_default = {
        "name": "test-formation",
        "a2a": {
            "registries": ["http://localhost:9090"]
        }
    }

    overlord_default = Overlord(formation_config=formation_config_default)
    print(
        f"  - External registry client created: "
        f"{overlord_default.external_registry_client is not None}"
    )

    # Test 4: Agent creation with new schema
    print("\n👤 Test 4: Agent creation behavior")
    if overlord_enabled.external_registry_client:
        agent = overlord_enabled.create_agent(
            agent_id="test-agent",
            model=model,
            system_message="Test agent for new schema",
            a2a_external=True
        )
        print(f"  - Agent created: {agent.agent_id}")
        print("  - Agent would be registered (if registry server running)")

    print("\n🎯 Schema Format Tests Complete!")
    print(f"  ✅ Enabled config: {'✓' if overlord_enabled.external_registry_client else '✗'}")
    print(f"  ❌ Disabled config: {'✗' if not overlord_disabled.external_registry_client else '✓'}")
    print(f"  🔄 Default config: {'✗' if not overlord_default.external_registry_client else '✓'}")


if __name__ == "__main__":
    asyncio.run(test_new_schema_format())
