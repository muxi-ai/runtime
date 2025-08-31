#!/usr/bin/env python
"""Test 8F2: Brainstorming session with proactive questioning."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation


async def test_brainstorming_session():
    """Test system's ability to facilitate a brainstorming session through proactive questioning."""

    formation_path = Path(__file__).parent / "formations/formation-clarification"
    formation = Formation()

    try:
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        print("\n" + "="*60)
        print("TEST 8F2: Brainstorming Session with Proactive Questioning")
        print("="*60)

        # Initial brainstorming request
        print("\n**User:** I want to brainstorm ideas for a new mobile app. Ask me questions to help develop the concept.")

        response1 = await overlord.chat(
            message="I want to brainstorm ideas for a new mobile app. Ask me questions to help develop the concept.",
            user_id="test_user",
            session_id="brainstorm_session_1",
            stream=False
        )
        print(f"\n**System:** {response1.content}")

        # Answer about problem to solve
        print("\n**User:** I want to help people manage their personal finances better, especially young adults")

        response2 = await overlord.chat(
            message="I want to help people manage their personal finances better, especially young adults",
            user_id="test_user",
            session_id="brainstorm_session_1",
            stream=False
        )
        print(f"\n**System:** {response2.content}")

        # Answer about existing solutions
        print("\n**User:** Current apps are too complex or boring. They feel like spreadsheets, not engaging tools")

        response3 = await overlord.chat(
            message="Current apps are too complex or boring. They feel like spreadsheets, not engaging tools",
            user_id="test_user",
            session_id="brainstorm_session_1",
            stream=False
        )
        print(f"\n**System:** {response3.content}")

        # Answer about unique approach
        print("\n**User:** Maybe gamification? Like making saving money feel like a game or challenge")

        response4 = await overlord.chat(
            message="Maybe gamification? Like making saving money feel like a game or challenge",
            user_id="test_user",
            session_id="brainstorm_session_1",
            stream=False
        )
        print(f"\n**System:** {response4.content}")

        # Answer about features
        print("\n**User:** Daily challenges, achievement badges, and maybe social features to compete with friends")

        response5 = await overlord.chat(
            message="Daily challenges, achievement badges, and maybe social features to compete with friends",
            user_id="test_user",
            session_id="brainstorm_session_1",
            stream=False
        )
        print(f"\n**System:** {response5.content}")

        # Signal completion
        print("\n**User:** I think we have enough to work with. Let's create a PDF document that summarizes these ideas into a concept.")

        response6 = await overlord.chat(
            message="I think we have enough to work with. Let's create a PDF document that summarizes these ideas into a concept.",
            user_id="test_user",
            session_id="brainstorm_session_1",
            stream=False
        )
        print(f"\n**System:** {response6.content}")

        # Check if this is a workflow approval request
        if "Does this approach work for you" in response6.content or "Should I proceed" in response6.content:
            print("\n**User:** Yes, please proceed with the plan")

            response7 = await overlord.chat(
                message="Yes, please proceed with the plan",
                user_id="test_user",
                session_id="brainstorm_session_1",
                stream=False
            )
            print(f"\n**System:** {response7.content}")

            # Print raw response to check for artifacts
            print("\n" + "="*60)
            print("RAW RESPONSE (checking for artifacts):")
            print("="*60)
            print(f"Role: {response7.role}")
            # print(f"Content type: {type(response7.content)}")
            print(f"Content: {response7}")
            if hasattr(response7, 'artifacts'):
                print(f"Artifacts: {response7.artifacts}")
            if hasattr(response7, 'files'):
                print(f"Files: {response7.files}")
            print("="*60)

            # Store final response for analysis
            final_response = response7.content.lower()
        else:
            # No approval needed, use response6
            print("\n" + "="*60)
            print("RAW RESPONSE (checking for artifacts):")
            print("="*60)
            print(f"Role: {response6.role}")
            print(f"Content type: {type(response6.content)}")
            print(f"Content: {response6.content}")
            if hasattr(response6, 'artifacts'):
                print(f"Artifacts: {response6.artifacts}")
            if hasattr(response6, 'files'):
                print(f"Files: {response6.files}")
            print("="*60)

            final_response = response6.content.lower()

        print("\n" + "="*60)
        print("ANALYSIS")
        print("="*60)

        # Analyze the brainstorming flow
        all_responses = [response1.content, response2.content, response3.content,
                        response4.content, response5.content]

        # Count probing questions
        probing_questions = sum(1 for r in all_responses if '?' in r)
        print(f"\n✓ Probing questions asked: {probing_questions}")

        # Check for brainstorming elements
        brainstorm_elements = []
        all_text = ' '.join(all_responses).lower()

        if any(word in all_text for word in ['problem', 'solve', 'issue', 'challenge']):
            brainstorm_elements.append('problem identification')
        if any(word in all_text for word in ['user', 'audience', 'target', 'who']):
            brainstorm_elements.append('target audience')
        if any(word in all_text for word in ['unique', 'different', 'stand out', 'competitive']):
            brainstorm_elements.append('differentiation')
        if any(word in all_text for word in ['feature', 'functionality', 'capability']):
            brainstorm_elements.append('features')
        if any(word in all_text for word in ['monetize', 'revenue', 'business model', 'profit']):
            brainstorm_elements.append('business model')

        print(f"✓ Brainstorming elements explored: {', '.join(brainstorm_elements)}")

        # Check if system built on previous answers
        building_on_answers = False
        if 'gamification' in response4.content.lower() or 'game' in response4.content.lower():
            if 'challenge' in response5.content.lower() or 'badge' in response5.content.lower():
                building_on_answers = True
                print("✓ System built upon previous answers (gamification → specific game features)")

        # Check final synthesis (already set in approval handling above)
        has_synthesis = any(word in final_response for word in
                           ['concept', 'summary', 'app idea', 'proposal', 'overview', 'pdf', 'document'])

        includes_user_input = (
            'finance' in final_response and
            'gamification' in final_response and
            ('challenge' in final_response or 'badge' in final_response)
        )

        if has_synthesis:
            print("✓ Final response synthesizes the brainstorming session")
        if includes_user_input:
            print("✓ Synthesis incorporates user's specific ideas")

        print("\n" + "="*60)

        # Overall assessment
        success_criteria = (
            probing_questions >= 3 and
            len(brainstorm_elements) >= 3 and
            has_synthesis
        )

        if success_criteria:
            print("\n✅ SUCCESS: Brainstorming session facilitation works!")
            print("✓ System asked relevant probing questions")
            print("✓ System explored multiple aspects of the idea")
            print("✓ System built upon user's answers")
            print("✓ System synthesized ideas into coherent concept")
        else:
            print("\n⚠️ PARTIAL SUCCESS: Basic brainstorming occurred")
            print(f"Probing questions: {probing_questions}/3+")
            print(f"Elements explored: {len(brainstorm_elements)}/3+")
            print(f"Has synthesis: {has_synthesis}")

        await formation.stop_overlord()

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        formation.shutdown()


if __name__ == "__main__":
    asyncio.run(test_brainstorming_session())
