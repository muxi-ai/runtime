#!/usr/bin/env python3
"""Simple test for real agent-to-agent collaboration"""

import asyncio
import os
import sys

# Add parent directory to path for imports
sys.path.append('..')

from src.muxi.overlord import Overlord  # noqa: E402
from src.muxi.models.providers.openai import OpenAIModel  # noqa: E402


async def test_real_collaboration():
    if not os.getenv('OPENAI_API_KEY'):
        print('❌ OPENAI_API_KEY not found - cannot test real collaboration')
        return

    print('🤖 Testing REAL Agent-to-Agent Collaboration...')
    print('=' * 60)

    # Create real OpenAI models
    research_model = OpenAIModel(model='gpt-4o-mini', temperature=0.7, max_tokens=500)
    analyst_model = OpenAIModel(model='gpt-4o-mini', temperature=0.3, max_tokens=500)

    overlord = Overlord()

    # Create specialized agents
    overlord.create_agent(
        agent_id='researcher',
        model=research_model,
        description='Research specialist',
        system_message=(
            'You are a research expert. Provide comprehensive research on any topic.'
        ),
        a2a_internal=True
    )

    overlord.create_agent(
        agent_id='analyst',
        model=analyst_model,
        description='Data analysis expert',
        system_message=(
            'You are a data analyst. Analyze information and provide statistical insights.'
        ),
        a2a_internal=True
    )

    # Test real collaboration
    researcher = overlord.get_agent('researcher')

    print('\n📚 Step 1: Researcher asking analyst for expertise...')
    consultation = await researcher.request_consultation(
        target_agent_id='analyst',
        topic='analyze productivity data',
        context={
            'data': 'Team A: 50 tasks/week, Team B: 45 tasks/week, Team C: 38 tasks/week',
            'question': 'What insights can you provide about this productivity variation?'
        },
        timeout=30
    )

    if consultation['status'] == 'success':
        expert_response = consultation['response']
        print('✓ Collaboration successful!')
        print(f'✓ Expert response ({len(expert_response)} chars): {expert_response[:200]}...')

        # Verify it contains analytical language
        analytical_words = ['analysis', 'data', 'variation', 'productivity', 'team', 'performance']
        found_words = [w for w in analytical_words if w.lower() in expert_response.lower()]
        print(f'✓ Contains analytical language: {found_words}')

        if len(found_words) >= 3:
            print('🎉 REAL COLLABORATION CONFIRMED - Agents are working together intelligently!')
            return True
        else:
            print('⚠️  Collaboration may be limited - response lacks depth')
            return False
    else:
        print(f'❌ Collaboration failed: {consultation}')
        return False


if __name__ == "__main__":
    result = asyncio.run(test_real_collaboration())
    if result:
        print('\n✅ TRUE COLLABORATION TEST PASSED')
    else:
        print('\n❌ TRUE COLLABORATION TEST FAILED')
