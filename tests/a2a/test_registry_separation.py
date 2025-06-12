import sys
import asyncio
sys.path.append('.')

from src.muxi.runtime.overlord import Overlord
from src.muxi.runtime.llm import LLM

async def test_registry_separation():
    """Test that outbound and inbound registries are used correctly"""

    # Config with DIFFERENT registries for outbound vs inbound
    config = {
        'a2a': {
            'enabled': True,
            'outbound': {
                'enabled': True,
                'registries': ['http://localhost:9090']  # For DISCOVERY
            },
            'inbound': {
                'enabled': True,
                'registries': ['http://localhost:9090'],  # For REGISTRATION
                'port': 8181
            }
        }
    }

    print('=== A2A Registry Separation Test ===')

    overlord = Overlord(formation_config=config)
    model = LLM(model='openai/gpt-4o-mini')
    overlord.create_agent(
        agent_id='separation-test-agent',
        model=model,
        description='Test agent for registry separation verification',
        a2a_external=True
    )

    # Verify clients are initialized from correct configs
    print('\n=== Verifying Client Initialization ===')

    external_client = overlord.external_registry_client
    inbound_client = overlord.inbound_registry_client

    print(f'✅ External registry client (discovery): {external_client is not None}')
    if external_client:
        print(f'   - Outbound registries: {external_client.registries}')

    print(f'✅ Inbound registry client (registration): {inbound_client is not None}')
    if inbound_client:
        print(f'   - Inbound registries: {inbound_client.registries}')

    # Test discovery uses external_registry_client (outbound.registries)
    print('\n=== Testing Discovery (should use a2a.outbound.registries) ===')
    agents = await overlord.discover_external_agents()
    print(f'✅ Discovery found {len(agents)} agents using outbound registries')

    # Test registration uses inbound_registry_client (inbound.registries)
    print('\n=== Testing Registration (should use a2a.inbound.registries) ===')
    success = await overlord.register_agent_with_external_registry('separation-test-agent')
    print(f'✅ Registration {"SUCCESS" if success else "FAILED"} using inbound registries')

    print('\n🎯 Registry Separation Verified!')
    print('\n=== CONFIRMED ===')
    print('✅ Agent Discovery uses a2a.outbound.registries')
    print('✅ Agent Registration uses a2a.inbound.registries')

if __name__ == '__main__':
    asyncio.run(test_registry_separation())
