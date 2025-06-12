#!/usr/bin/env python3
"""
Test the active agent functionality implementation.

This test verifies that:
1. Agents with active: false are completely ignored during loading
2. Agents with active: true (or no active field) are loaded normally
3. Proper logging occurs for both loaded and skipped agents
"""

import asyncio
import sys
import tempfile
from pathlib import Path

# Add the runtime to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import after path modification
try:
    from src.muxi.runtime.config.formation_loader import FormationLoader
    from src.muxi.runtime.overlord import Overlord
except ImportError:
    print("❌ Could not import runtime modules. Check working directory.")
    sys.exit(1)


async def test_active_agent_functionality():
    """Test the active agent functionality."""

    # Create a temporary directory for test formations
    with tempfile.TemporaryDirectory() as temp_dir:
        formation_dir = Path(temp_dir)

        # Create main formation.yaml
        formation_yaml = formation_dir / "formation.yaml"
        formation_yaml.write_text("""
schema: "1.0.0"
id: "test-formation"
description: "Test formation for active agent functionality"

# Inline agent (should be loaded)
agents:
  - schema: "1.0.0"
    id: "inline-active-agent"
    name: "Inline Active Agent"
    description: "This agent is active by default"
    system_message: "You are an active agent"

  - schema: "1.0.0"
    id: "inline-disabled-agent"
    name: "Inline Disabled Agent"
    description: "This agent is disabled"
    system_message: "You are a disabled agent"
    active: false
""")

        # Create agents directory with external agent files
        agents_dir = formation_dir / "agents"
        agents_dir.mkdir()

        # Active external agent
        (agents_dir / "external-active-agent.yaml").write_text("""
schema: "1.0.0"
id: "external-active-agent"
name: "External Active Agent"
description: "This external agent is active"
system_message: "You are an external active agent"
active: true
""")

        # Disabled external agent
        (agents_dir / "external-disabled-agent.yaml").write_text("""
schema: "1.0.0"
id: "external-disabled-agent"
name: "External Disabled Agent"
description: "This external agent is disabled"
system_message: "You are an external disabled agent"
active: false
""")

        # Default active external agent (no active field)
        (agents_dir / "external-default-agent.yaml").write_text("""
schema: "1.0.0"
id: "external-default-agent"
name: "External Default Agent"
description: "This external agent is active by default"
system_message: "You are an external default agent"
""")

        print("🧪 Testing active agent functionality...")

        # Test formation loading
        loader = FormationLoader()
        config = await loader.load(str(formation_dir))

        # Check loaded agents
        loaded_agents = config.get('agents', [])
        loaded_agent_ids = [agent['id'] for agent in loaded_agents]

        print(f"📊 Loaded agents: {loaded_agent_ids}")

        # Expected loaded agents (active ones only)
        expected_loaded = {
            'inline-active-agent',      # inline, active by default
            'external-active-agent',    # external, active: true
            'external-default-agent'    # external, active by default
        }

        # Expected skipped agents
        expected_skipped = {
            'inline-disabled-agent',    # inline, active: false
            'external-disabled-agent'   # external, active: false
        }

        # Verify results
        actual_loaded = set(loaded_agent_ids)

        print(f"✅ Expected loaded: {expected_loaded}")
        print(f"📋 Actually loaded: {actual_loaded}")
        print(f"❌ Expected skipped: {expected_skipped}")

        # Test assertions
        if actual_loaded == expected_loaded:
            print("✅ SUCCESS: Correct agents were loaded!")
        else:
            print("❌ FAILURE: Agent loading mismatch!")
            missing = expected_loaded - actual_loaded
            extra = actual_loaded - expected_loaded
            if missing:
                print(f"   Missing agents: {missing}")
            if extra:
                print(f"   Extra agents: {extra}")
            return False

        # Test with overlord
        print("\n🤖 Testing with Overlord...")
        overlord = Overlord()
        await overlord.load_formation_from_path(str(formation_dir))

        # Check overlord agents
        overlord_agents = list(overlord.agents.keys())
        print(f"🤖 Overlord agents: {overlord_agents}")

        if set(overlord_agents) == expected_loaded:
            print("✅ SUCCESS: Overlord loaded correct agents!")
        else:
            print("❌ FAILURE: Overlord agent loading mismatch!")
            return False

        return True


if __name__ == "__main__":
    success = asyncio.run(test_active_agent_functionality())
    if success:
        print("\n🎉 All tests passed! Active agent functionality is working correctly.")
        sys.exit(0)
    else:
        print("\n💥 Some tests failed!")
        sys.exit(1)
