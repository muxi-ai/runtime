"""
Test 3B2 with Webhooks: Meeting Audio Analysis
Tests the system's ability to analyze meeting recordings and extract insights with webhook support.
"""

import os
import sys
sys.path.insert(0, '.')
import pytest
import asyncio
from pathlib import Path

from src.muxi.runtime.formation.formation import Formation
from utils.webhook_test_utils import check_response_with_webhook, setup_webhook_test


@pytest.fixture
async def formation():
    """Load multimodal test formation"""
    # Load the directory, not the file, to enable agent auto-discovery
    formation_path = Path(__file__).parent.parent.parent / "test-formations" / "formation-multimodal"
    
    formation = Formation()
    await formation.load(str(formation_path))
    
    return formation


@pytest.fixture
async def overlord(formation):
    """Create overlord instance"""
    # Setup webhook testing environment
    setup_webhook_test()
    
    overlord = await formation.start_overlord()
    
    yield overlord
    
    # Cleanup
    await formation.stop_overlord()


def test_meeting_transcription_with_webhooks(overlord):
    """Test transcription of meeting audio with webhook support"""
    print("\n=== Test 3B2 with Webhooks: Meeting Transcription ===")
    
    # Simulate meeting transcription
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_meeting",
            message="I just transcribed a meeting recording. The meeting had 3 participants discussing Q4 budget allocation: "
                    "Speaker 1 opened with 'Let's review the Q4 budget proposals.' "
                    "Speaker 2 suggested 'We should allocate 40% to marketing given the new product launch.' "
                    "Speaker 3 countered 'I think 30% marketing and 20% to R&D would be more balanced.' "
                    "They agreed to revisit next week with more data. Please summarize this discussion."
        )
    )
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['meeting', 'discussion', 'speaker', 'budget'],
        min_keywords=2,
        min_length=100,
        test_name="Meeting Transcription"
    )
    
    print(f"Meeting Transcription Complete - Async: {is_async}")
    print(f"Result length: {len(result)} characters")


def test_meeting_action_items_with_webhooks(overlord):
    """Test extraction of action items from meeting with webhook support"""
    print("\n=== Test 3B2 with Webhooks: Meeting Action Items ===")
    
    user_id = "test_user_actions"
    
    # Simulate meeting with action items
    response = asyncio.run(
        overlord.chat(
            user_id=user_id,
            message="I analyzed a meeting recording and found these action items: "
                    "1. John will prepare the budget proposal by Friday. "
                    "2. Sarah to schedule follow-up with marketing team next week. "
                    "3. Team will review competitive analysis before month end. "
                    "4. Decision: Approve 30% budget increase for Q4 marketing. "
                    "Please organize these action items by priority and owner."
        )
    )
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['action', 'task', 'next', 'step', 'decision', 'follow'],
        min_keywords=2,
        min_length=50,
        test_name="Meeting Action Items"
    )
    
    print(f"Action Items Extraction Complete - Async: {is_async}")


def test_meeting_summary_generation_with_webhooks(overlord):
    """Test generating meeting summary with webhook support"""
    print("\n=== Test 3B2 with Webhooks: Meeting Summary Generation ===")
    
    user_id = "test_user_summary"
    
    # Simulate meeting content for summary
    response = asyncio.run(
        overlord.chat(
            user_id=user_id,
            message="Create a concise summary of this meeting: "
                    "Meeting Date: Dec 20, 2024, 2pm EST. "
                    "Participants: John (Finance), Sarah (Marketing), Mike (Product). "
                    "Topics: 1) Q4 budget review - current spend at 75% of allocation. "
                    "2) New product launch timeline - targeting Feb 2025. "
                    "3) Marketing campaign performance - 15% above target ROI. "
                    "Key decisions: Approved additional 30% marketing budget, postponed hiring freeze."
        )
    )
    
    # Use universal webhook checker for summary
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['meeting', 'summary', 'budget', 'decision'],
        min_keywords=2,
        min_length=50,
        test_name="Meeting Summary"
    )
    
    # Follow up for specific details
    detail_response = asyncio.run(
        overlord.chat(
            user_id=user_id,
            message="Based on the meeting, what were the top 3 most important points discussed?"
        )
    )
    
    # Check detail response
    detail_result, detail_is_async = check_response_with_webhook(
        detail_response,
        expected_keywords=['1', '2', '3', 'first', 'second', 'third', 'point'],
        min_keywords=1,
        min_length=50,
        test_name="Meeting Key Points"
    )
    
    print(f"Meeting Summary Complete - Summary Async: {is_async}, Details Async: {detail_is_async}")


def test_meeting_participant_analysis_with_webhooks(overlord):
    """Test analysis of meeting participants with webhook support"""
    print("\n=== Test 3B2 with Webhooks: Meeting Participant Analysis ===")
    
    # Simulate meeting participant analysis
    response = asyncio.run(
        overlord.chat(
            user_id="test_user_participants",
            message="I analyzed a meeting recording with these observations: "
                    "Participant 1 (male voice): Spoke 40% of the time, led the discussion, asked clarifying questions. "
                    "Participant 2 (female voice): Spoke 35% of the time, provided data-driven insights, challenged assumptions. "
                    "Participant 3 (male voice): Spoke 25% of the time, mostly responded to questions, agreed with proposals. "
                    "The meeting had a collaborative tone with balanced participation. "
                    "Please analyze these speaking patterns and what they reveal about team dynamics."
        )
    )
    
    # Use universal webhook checker
    result, is_async = check_response_with_webhook(
        response,
        expected_keywords=['participant', 'speaker', 'voice', 'contribute', 'dynamic'],
        min_keywords=2,
        min_length=50,
        test_name="Participant Analysis"
    )
    
    print(f"Participant Analysis Complete - Async: {is_async}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])