#!/usr/bin/env python3
"""
Demo script showing FormationLoader integration with Overlord.

This script demonstrates:
1. Formation validation using both direct FormationValidator and through Overlord
2. Formation loading with automatic agent and MCP server creation (mocked)
3. Integration between all components with proper logging
"""

import asyncio
import os
import sys
import tempfile
import yaml
from pathlib import Path

# Add runtime to Python path
current_dir = Path(__file__).parent.absolute()
runtime_dir = current_dir.parent
sys.path.insert(0, str(runtime_dir))

from src.muxi.runtime.overlord import Overlord  # noqa: E402
from src.muxi.runtime.config.validation import validate_formation  # noqa: E402


def create_sample_formation():
    """Create a sample formation configuration for demonstration."""
    return {
        'name': 'demo-formation',
        'version': '1.0.0',
        'description': 'Demonstration formation for integration testing',
        'agents': [
            {
                'agent_id': 'assistant',
                'model': {
                    'provider': 'openai',
                    'model': 'gpt-4',
                    'temperature': 0.7
                },
                'system_message': 'You are a helpful AI assistant.',
                'description': 'General purpose assistant'
            }
        ],
        'mcp': {
            'servers': [
                {
                    'id': 'web-search',
                    'url': 'http://localhost:8001/mcp'
                }
            ]
        }
    }


async def demo_validation():
    """Demonstrate formation validation capabilities."""
    print("🔍 FORMATION VALIDATION DEMO")
    print("=" * 50)

    formation_config = create_sample_formation()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(formation_config, f, default_flow_style=False)
        formation_path = f.name

    try:
        print(f"📄 Created sample formation: {formation_path}")

        # Validate using the validation module directly
        print("\n1. Direct validation using FormationValidator:")
        validation_result = validate_formation(formation_path)
        print(f"   Status: {validation_result.summary()}")

        # Validate using Overlord
        print("\n2. Validation through Overlord:")
        overlord = Overlord()
        overlord_validation = await overlord.validate_formation(formation_path)
        print(f"   Status: {overlord_validation['summary']}")

        print("\n✅ Validation demo completed successfully!")

    finally:
        os.unlink(formation_path)


async def demo_formation_loading():
    """Demonstrate formation loading capabilities."""
    print("\n🚀 FORMATION LOADING DEMO")
    print("=" * 50)

    formation_config = create_sample_formation()

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(formation_config, f, default_flow_style=False)
        formation_path = f.name

    try:
        print(f"📄 Created formation: {formation_path}")

        overlord = Overlord()

        # Mock the actual agent/MCP creation to avoid API calls
        def mock_create_agent(*args, **kwargs):
            agent_id = kwargs.get('agent_id', args[0] if args else 'unknown')
            print(f"     🤖 Would create agent: {agent_id}")
            return None

        async def mock_register_mcp(*args, **kwargs):
            server_id = kwargs.get('server_id', args[0] if args else 'unknown')
            print(f"     🔧 Would register MCP server: {server_id}")
            return server_id

        overlord.create_agent = mock_create_agent
        overlord.register_mcp_server = mock_register_mcp

        config = await overlord.load_formation_from_path(formation_path)
        print(f"     ✅ Loaded formation: {config['name']} v{config['version']}")
        print(f"     📊 Agents: {len(config.get('agents', []))}")
        print(f"     📊 MCP Servers: {len(config.get('mcp', {}).get('servers', []))}")

        print("\n✅ Formation loading demo completed successfully!")

    finally:
        os.unlink(formation_path)


async def main():
    """Run all demonstrations."""
    print("🎯 FORMATION INTEGRATION DEMONSTRATION")
    print("=" * 60)
    print("This demo shows the integration between FormationLoader,")
    print("validation tools, and the Overlord.")
    print("=" * 60)

    try:
        await demo_validation()
        await demo_formation_loading()

        print("\n🎉 ALL DEMONSTRATIONS COMPLETED SUCCESSFULLY!")
        print("\nKey Features Demonstrated:")
        print("✅ Formation validation (both direct and through Overlord)")
        print("✅ Formation loading with validation")
        print("✅ Integration between all components")

    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
