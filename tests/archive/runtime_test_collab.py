#!/usr/bin/env python3
"""Simple test for real agent-to-agent collaboration"""

import asyncio
import os
import sys

# Add parent directory to path for imports
sys.path.append('..')

from muxi.runtime.overlord import Overlord  # noqa: E402
from muxi.runtime.llm import LLM  # noqa: E402


async def test_real_collaboration():
    if not os.getenv('OPENAI_API_KEY'):
        print('❌ OPENAI_API_KEY not found - cannot test real collaboration')
        return False

    print('🤖 Testing REAL Agent-to-Agent Collaboration...')
    print('=' * 60)

    try:
        # Create overlord first
        overlord = Overlord()

        # Create real OpenAI models using the same pattern as working tests
        research_model = LLM(
            model="openai/gpt-4o",
            api_key=os.getenv('OPENAI_API_KEY'),
            temperature=0.7,
            max_tokens=300
        )

        analyst_model = LLM(
            model="openai/gpt-4o",
            api_key=os.getenv('OPENAI_API_KEY'),
            temperature=0.3,
            max_tokens=300
        )

        # Create specialized agents
        overlord.create_agent(
            agent_id='researcher',
            model=research_model,
            description='Research specialist',
            system_message='You are a research expert who provides comprehensive analysis.',
            a2a_internal=True
        )

        overlord.create_agent(
            agent_id='analyst',
            model=analyst_model,
            description='Data analyst',
            system_message='You are a data analyst who provides statistical insights.',
            a2a_internal=True
        )

        # Get agents
        researcher = overlord.get_agent('researcher')

        print('\n📚 Testing: Researcher asking analyst for expertise...')

        # Test real consultation between agents with actual LLM reasoning
        consultation = await researcher.request_consultation(
            target_agent_id='analyst',
            topic='productivity analysis',
            context={
                'data': 'Team A: 50 tasks/week, Team B: 45 tasks/week, Team C: 38 tasks/week',
                'question': 'Analyze this productivity variation and provide insights'
            },
            timeout=30
        )

        if consultation and consultation.get('status') == 'success':
            response = consultation['response']
            print('✓ Collaboration successful!')
            print(f'✓ Expert response ({len(response)} chars)')
            print(f'Response preview: {response[:300]}...')

            # Check for analytical content indicating true reasoning
            analytical_terms = ['analysis', 'data', 'variation', 'productivity', 'insight', 'team']
            found_terms = [
                term for term in analytical_terms
                if term.lower() in response.lower()
            ]

            print(f'✓ Contains analytical terms: {found_terms}')

            if len(found_terms) >= 2:
                print('🎉 REAL COLLABORATION CONFIRMED!')
                return True
            else:
                print('⚠️  Limited collaboration depth')
                return False
        else:
            print(f'❌ Collaboration failed: {consultation}')
            return False

    except Exception as e:
        print(f'❌ Test failed with error: {e}')
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    result = asyncio.run(test_real_collaboration())
    if result:
        print('\n✅ TRUE COLLABORATION TEST PASSED')
    else:
        print('\n❌ TRUE COLLABORATION TEST FAILED')
