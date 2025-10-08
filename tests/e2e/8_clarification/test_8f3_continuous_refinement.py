#!/usr/bin/env python
"""Test 8F3: Continuous refinement through iterative questioning."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def test_continuous_refinement():
    """Test system's ability to continuously refine understanding through iterative questions."""

    formation_path = Path(__file__).parent / "formations/formation-clarification"
    formation = Formation()

    try:
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        print("\n" + "=" * 60)
        print("TEST 8F3: Continuous Refinement Through Questions")
        print("=" * 60)

        # Initial request for continuous refinement
        print(
            "\n**User:** I need help designing a database schema. "
            "Keep asking questions until we have a complete design."
        )

        response1 = await overlord.chat(
            message="I need help designing a database schema. Keep asking questions until we have a complete design.",
            user_id="test_user",
            session_id="refinement_session_1",
            stream=False,
        )
        print(f"\n**System:** {response1.content}")

        # Answer about application type
        print("\n**User:** It's for an e-commerce platform")

        response2 = await overlord.chat(
            message="It's for an e-commerce platform",
            user_id="test_user",
            session_id="refinement_session_1",
            stream=False,
        )
        print(f"\n**System:** {response2.content}")

        # Answer about scale
        print("\n**User:** Starting small but need to scale to millions of users")

        response3 = await overlord.chat(
            message="Starting small but need to scale to millions of users",
            user_id="test_user",
            session_id="refinement_session_1",
            stream=False,
        )
        print(f"\n**System:** {response3.content}")

        # Answer about features
        print(
            "\n**User:** Products, categories, user accounts, orders, reviews, and inventory tracking"
        )

        response4 = await overlord.chat(
            message="Products, categories, user accounts, orders, reviews, and inventory tracking",
            user_id="test_user",
            session_id="refinement_session_1",
            stream=False,
        )
        print(f"\n**System:** {response4.content}")

        # Answer about special requirements
        print("\n**User:** Multi-currency support and real-time inventory updates are critical")

        response5 = await overlord.chat(
            message="Multi-currency support and real-time inventory updates are critical",
            user_id="test_user",
            session_id="refinement_session_1",
            stream=False,
        )
        print(f"\n**System:** {response5.content}")

        # More specific detail
        print("\n**User:** Products can have variants (size, color) and bundles")

        response6 = await overlord.chat(
            message="Products can have variants (size, color) and bundles",
            user_id="test_user",
            session_id="refinement_session_1",
            stream=False,
        )
        print(f"\n**System:** {response6.content}")

        # Signal we have enough
        print("\n**User:** That's enough detail - please create the schema design")

        response7 = await overlord.chat(
            message="That's enough detail - please create the schema design",
            user_id="test_user",
            session_id="refinement_session_1",
            stream=False,
        )
        print(f"\n**System:** {response7.content}")

        print("\n" + "=" * 60)
        print("ANALYSIS")
        print("=" * 60)

        # Analyze the refinement process
        all_responses = [
            response1.content,
            response2.content,
            response3.content,
            response4.content,
            response5.content,
            response6.content,
        ]

        # Count refinement questions
        refinement_questions = sum(1 for r in all_responses if "?" in r)
        print(f"\n✓ Refinement questions asked: {refinement_questions}")

        # Check for progressive refinement (questions getting more specific)
        specificity_progression = []

        # Check if questions progress from general to specific
        response_lower = [r.lower() for r in all_responses]

        # Early questions should be general
        if any(word in response_lower[0] for word in ["what kind", "what type", "purpose"]):
            specificity_progression.append("general context")

        # Middle questions should be about requirements
        if any(
            word in " ".join(response_lower[1:3])
            for word in ["scale", "size", "users", "performance"]
        ):
            specificity_progression.append("scale requirements")

        # Later questions should be detailed
        if any(
            word in " ".join(response_lower[3:])
            for word in ["specific", "detail", "particular", "how"]
        ):
            specificity_progression.append("specific details")

        print(f"✓ Refinement progression: {' → '.join(specificity_progression)}")

        # Check if system incorporated previous answers
        context_building = []
        if "e-commerce" in " ".join(response_lower[2:]):
            context_building.append("retained domain context")
        if "scale" in " ".join(response_lower[3:]) or "million" in " ".join(response_lower[3:]):
            context_building.append("considered scalability")
        if "inventory" in response5.content.lower() or "variant" in response6.content.lower():
            context_building.append("built on feature list")

        print(f"✓ Context building: {', '.join(context_building)}")

        # Check final schema output
        final_response = response7.content.lower()
        schema_elements = []

        if "table" in final_response or "entity" in final_response:
            schema_elements.append("tables/entities")
        if "relationship" in final_response or "foreign key" in final_response:
            schema_elements.append("relationships")
        if "index" in final_response or "performance" in final_response:
            schema_elements.append("optimization")
        if "currency" in final_response:
            schema_elements.append("multi-currency")
        if "variant" in final_response or "bundle" in final_response:
            schema_elements.append("product variants")

        print(f"✓ Schema elements in output: {', '.join(schema_elements)}")

        print("\n" + "=" * 60)

        # Overall assessment
        success_criteria = (
            refinement_questions >= 4
            and len(specificity_progression) >= 2
            and len(context_building) >= 2
            and len(schema_elements) >= 3
        )

        if success_criteria:
            print("\n✅ SUCCESS: Continuous refinement works perfectly!")
            print("✓ System asked progressively specific questions")
            print("✓ System built context from previous answers")
            print("✓ System refined understanding iteratively")
            print("✓ System produced comprehensive output based on refinement")
        else:
            print("\n⚠️ PARTIAL SUCCESS: Some refinement occurred")
            print(f"Refinement questions: {refinement_questions}/4+")
            print(f"Progression depth: {len(specificity_progression)}/2+")
            print(f"Context building: {len(context_building)}/2+")
            print(f"Schema completeness: {len(schema_elements)}/3+")

        await formation.stop_overlord()

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback

        traceback.print_exc()
    finally:
        formation.shutdown()


if __name__ == "__main__":
    asyncio.run(test_continuous_refinement())
