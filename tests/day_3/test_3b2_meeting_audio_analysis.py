"""
Test 3B2: Meeting Audio Analysis
Tests the system's ability to analyze meeting recordings and extract insights.
"""

import os
import sys
sys.path.insert(0, '.')
import pytest
import asyncio
from pathlib import Path

from src.muxi.runtime.formation.formation import Formation


def get_response(coro):
    """Helper to get response from async chat"""
    result = asyncio.run(coro)
    
    # Handle async generators
    if hasattr(result, "__aiter__"):
        async def collect():
            chunks = []
            async for chunk in result:
                chunks.append(chunk)
            return "".join(chunks)
        return asyncio.run(collect())
    
    return result


@pytest.fixture
def formation():
    """Load multimodal test formation"""
    # Load the directory, not the file, to enable agent auto-discovery
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    
    formation = Formation()
    formation.load(str(formation_path))
    
    return formation


@pytest.fixture
def overlord(formation):
    """Create overlord instance"""
    overlord = formation.start_overlord()
    
    yield overlord
    
    # Cleanup
    formation.stop_overlord()


def test_meeting_transcription(overlord):
    """Test transcription of meeting audio"""
    print("\n=== Test 3B2: Meeting Transcription ===")
    
    # Simulate meeting transcription
    upload_response = get_response(
        overlord.chat(
            user_id="test_user_meeting",
            message="I just transcribed a meeting recording. The meeting had 3 participants discussing Q4 budget allocation: "
                    "Speaker 1 opened with 'Let's review the Q4 budget proposals.' "
                    "Speaker 2 suggested 'We should allocate 40% to marketing given the new product launch.' "
                    "Speaker 3 countered 'I think 30% marketing and 20% to R&D would be more balanced.' "
                    "They agreed to revisit next week with more data. Please summarize this discussion.",
            use_async=False
        )
    )
    
    print(f"Meeting Transcription Response: {upload_response}")
    
    # Verify response
    assert upload_response, "Should receive a response"
    assert len(upload_response) > 100, "Response should contain detailed transcription"
    
    # Response should mention meeting elements
    response_lower = upload_response.lower()
    meeting_words = ['meeting', 'discussion', 'speaker', 'topic', 'point', 'agenda', 'budget']
    matches = sum(1 for word in meeting_words if word in response_lower)
    assert matches >= 2, f"Response should mention meeting elements, found {matches}"


def test_meeting_action_items(overlord):
    """Test extraction of action items from meeting"""
    print("\n=== Test 3B2: Meeting Action Items ===")
    
    user_id = "test_user_actions"
    
    # Simulate meeting with action items
    upload_response = get_response(
        overlord.chat(
            user_id=user_id,
            message="I analyzed a meeting recording and found these action items: "
                    "1. John will prepare the budget proposal by Friday. "
                    "2. Sarah to schedule follow-up with marketing team next week. "
                    "3. Team will review competitive analysis before month end. "
                    "4. Decision: Approve 30% budget increase for Q4 marketing. "
                    "Please organize these action items by priority and owner.",
            use_async=False
        )
    )
    
    print(f"Action Items Response: {upload_response}")
    
    # Verify action item extraction
    assert upload_response, "Should receive a response"
    response_lower = upload_response.lower()
    action_words = ['action', 'task', 'next', 'step', 'decision', 'follow', 'will', 'should']
    matches = sum(1 for word in action_words if word in response_lower)
    assert matches >= 2, f"Response should extract action items, found {matches}"


def test_meeting_summary_generation(overlord):
    """Test generating meeting summary"""
    print("\n=== Test 3B2: Meeting Summary Generation ===")
    
    user_id = "test_user_summary"
    
    # Simulate meeting content for summary
    upload_response = get_response(
        overlord.chat(
            user_id=user_id,
            message="Create a concise summary of this meeting: "
                    "Meeting Date: Dec 20, 2024, 2pm EST. "
                    "Participants: John (Finance), Sarah (Marketing), Mike (Product). "
                    "Topics: 1) Q4 budget review - current spend at 75% of allocation. "
                    "2) New product launch timeline - targeting Feb 2025. "
                    "3) Marketing campaign performance - 15% above target ROI. "
                    "Key decisions: Approved additional 30% marketing budget, postponed hiring freeze.",
            use_async=False
        )
    )
    
    print(f"Meeting Summary Response: {upload_response}")
    
    # Follow up for specific details
    detail_response = get_response(
        overlord.chat(
            user_id=user_id,
            message="Based on the meeting, what were the top 3 most important points discussed?",
            use_async=False
        )
    )
    
    print(f"Key Points Response: {detail_response}")
    
    # Verify summary quality
    assert upload_response, "Should receive summary response"
    assert detail_response, "Should receive key points response"
    assert len(detail_response) > 50, "Response should contain key points"
    assert any(word in detail_response.lower() for word in ['1', '2', '3', 'first', 'second', 'third']), \
        "Should enumerate key points"


def test_meeting_participant_analysis(overlord):
    """Test analysis of meeting participants"""
    print("\n=== Test 3B2: Meeting Participant Analysis ===")
    
    # Simulate meeting participant analysis
    upload_response = get_response(
        overlord.chat(
            user_id="test_user_participants",
            message="I analyzed a meeting recording with these observations: "
                    "Participant 1 (male voice): Spoke 40% of the time, led the discussion, asked clarifying questions. "
                    "Participant 2 (female voice): Spoke 35% of the time, provided data-driven insights, challenged assumptions. "
                    "Participant 3 (male voice): Spoke 25% of the time, mostly responded to questions, agreed with proposals. "
                    "The meeting had a collaborative tone with balanced participation. "
                    "Please analyze these speaking patterns and what they reveal about team dynamics.",
            use_async=False
        )
    )
    
    print(f"Participant Analysis Response: {upload_response}")
    
    # Verify participant analysis
    assert upload_response, "Should receive a response"
    response_lower = upload_response.lower()
    participant_words = ['participant', 'speaker', 'person', 'voice', 'contribute', 'speak']
    matches = sum(1 for word in participant_words if word in response_lower)
    assert matches >= 2, f"Response should analyze participants, found {matches}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])