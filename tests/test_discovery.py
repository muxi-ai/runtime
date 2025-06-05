import sys
import asyncio
sys.path.append('.')

from runtime.muxi.runtime.overlord import Overlord
from runtime.muxi.runtime.llm import LLM

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
        agent_id='test-agent',
        model=model,
        description='Test agent for A2A operations',
        a2a_external=True
    )

    print('=== A2A Discovery Test ===')
    agents = await overlord.discover_external_agents()
    print(f'✅ Discovered {len(agents)} external agents:')

    for i, agent in enumerate(agents[:5], 1):
        print(f'  {i}. {agent.name}: {agent.description[:60]}...')

    if len(agents) > 5:
        print(f'  ... and {len(agents)-5} more agents')

if __name__ == '__main__':
    asyncio.run(test())
