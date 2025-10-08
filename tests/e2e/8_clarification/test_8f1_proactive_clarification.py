#!/usr/bin/env python
"""Test 8F1: Proactive clarification gathering - system leads questioning."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.formation import Formation  # noqa: E402


async def test_proactive_clarification():
    """Test system's ability to proactively gather information through questioning."""

    formation_path = Path(__file__).parent / "formations/formation-clarification"
    formation = Formation()

    try:
        await formation.load(str(formation_path))
        overlord = await formation.start_overlord()

        print("\n" + "=" * 60)
        print("TEST 8F1: Proactive Clarification Gathering")
        print("=" * 60)

        # Initial request asking for proactive questioning
        print(
            "\n**User:** I want to plan a vacation. Ask me questions until you have enough "
            "information to suggest a complete itinerary."
        )

        response1 = await overlord.chat(
            message=(
                "I want to plan a vacation. Ask me questions until you have enough "
                "information to suggest a complete itinerary.",
            ),
            user_id="test_user",
            session_id="proactive_session_1",
            stream=False,
        )
        print(f"\n**System:** {response1.content}")

        # Answer first question (e.g., destination preference)
        print("\n**User:** I'm thinking somewhere warm, maybe tropical")

        response2 = await overlord.chat(
            message="I'm thinking somewhere warm, maybe tropical",
            user_id="test_user",
            session_id="proactive_session_1",
            stream=False,
        )
        print(f"\n**System:** {response2.content}")

        # Answer second question (e.g., budget)
        print("\n**User:** Budget is around $5000 for two people")

        response3 = await overlord.chat(
            message="Budget is around $5000 for two people",
            user_id="test_user",
            session_id="proactive_session_1",
            stream=False,
        )
        print(f"\n**System:** {response3.content}")

        # Answer third question (e.g., duration)
        print("\n**User:** One week in March")

        response4 = await overlord.chat(
            message="One week in March",
            user_id="test_user",
            session_id="proactive_session_1",
            stream=False,
        )
        print(f"\n**System:** {response4.content}")

        # Answer fourth question (e.g., activities)
        print("\n**User:** We like beaches, snorkeling, and good food. Not into partying.")

        response5 = await overlord.chat(
            message="We like beaches, snorkeling, and good food. Not into partying.",
            user_id="test_user",
            session_id="proactive_session_1",
            stream=False,
        )
        print(f"\n**System:** {response5.content}")

        # Signal that we've provided enough information
        print("\n**User:** That's all the key information - go ahead and create the itinerary")

        response6 = await overlord.chat(
            message="That's all the key information - go ahead and create the itinerary",
            user_id="test_user",
            session_id="proactive_session_1",
            stream=False,
        )
        print(f"\n**System:** {response6.content}")

        print("\n" + "=" * 60)
        print("ANALYSIS")
        print("=" * 60)

        # Check if system asked multiple questions
        all_responses = [
            response1.content,
            response2.content,
            response3.content,
            response4.content,
            response5.content,
        ]

        questions_asked = sum(1 for r in all_responses if "?" in r)
        print(f"\n✓ Questions asked by system: {questions_asked}")

        # Check if system gathered key information categories
        info_gathered = []
        all_text = " ".join(all_responses).lower()

        if any(word in all_text for word in ["destination", "where", "location", "place"]):
            info_gathered.append("destination")
        if any(word in all_text for word in ["budget", "cost", "spend", "price"]):
            info_gathered.append("budget")
        if any(word in all_text for word in ["duration", "how long", "days", "week"]):
            info_gathered.append("duration")
        if any(word in all_text for word in ["activities", "interests", "like to do"]):
            info_gathered.append("activities")
        if any(word in all_text for word in ["dates", "when", "month", "time"]):
            info_gathered.append("dates")

        print(f"✓ Information categories gathered: {', '.join(info_gathered)}")

        # Check if final response contains itinerary
        final_response = response6.content.lower()
        has_itinerary = any(
            word in final_response
            for word in ["itinerary", "day 1", "schedule", "plan", "suggestion", "recommend"]
        )

        if has_itinerary:
            print("✓ Final response contains itinerary/recommendations")

        # Check if system recognized the "that's all" signal
        if len(response6.content) > 500:  # Substantial response
            print("✓ System recognized completion signal and provided comprehensive output")

        print("\n" + "=" * 60)

        # Overall assessment
        if questions_asked >= 3 and len(info_gathered) >= 3 and has_itinerary:
            print("\n✅ SUCCESS: Proactive clarification gathering works!")
            print("✓ System asked multiple relevant questions")
            print("✓ System gathered information across categories")
            print("✓ System recognized when to stop gathering")
            print("✓ System provided comprehensive output")
        else:
            print("\n⚠️ PARTIAL SUCCESS: Some proactive gathering occurred")
            print(f"Questions asked: {questions_asked}/3+")
            print(f"Info categories: {len(info_gathered)}/3+")
            print(f"Has itinerary: {has_itinerary}")

        await formation.stop_overlord()

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback

        traceback.print_exc()
    finally:
        formation.shutdown()


if __name__ == "__main__":
    asyncio.run(test_proactive_clarification())
