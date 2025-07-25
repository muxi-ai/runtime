import sys
import asyncio
sys.path.append('.')

from src.muxi.overlord import Overlord
from src.muxi.llm import LLM

async def test():
    config = {
        'a2a': {
            'enabled': True,
            'outbound': {
                'enabled': True,
                'registries': ['http://localhost:9090']
            },
            'inbound': {
                'enabled': True,
                'registries': ['http://localhost:9090'],
                'port': 8181
            }
        }
    }

    overlord = Overlord(formation_config=config)
    model = LLM(model='openai/gpt-4o-mini')
    overlord.create_agent(
        agent_id='muxi-test-agent',
        model=model,
        description='MUXI test agent for A2A registration testing',
        a2a_external=True
    )

    print('=== A2A Registration Test ===')

    # Test agent registration
    print('Testing agent registration...')
    try:
        success = await overlord.register_agent_with_external_registry('muxi-test-agent')
        print(f'✅ Registration: {"SUCCESS" if success else "FAILED"}')
    except Exception as e:
        print(f'❌ Registration error: {e}')

    # Verify registration by discovering agents again
    print('\nVerifying registration by discovering agents...')
    agents = await overlord.discover_external_agents()
    print(f'Total agents found: {len(agents)}')

    # Look for our registered agent
    our_agent = None
    for agent in agents:
        if 'muxi-test-agent' in agent.name or 'MUXI test agent' in agent.description:
            our_agent = agent
            break

    if our_agent:
        print(f'✅ Found our registered agent: {our_agent.name}')
        print(f'   Description: {our_agent.description}')
        print(f'   URL: {our_agent.url}')
    else:
        print('❌ Our agent not found in discovery results')

if __name__ == '__main__':
    asyncio.run(test())
