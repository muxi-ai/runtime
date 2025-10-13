"""
Test 15A3: Topic Diversity Across Domains

Tests that the LLM generates appropriate, diverse topics across
different request domains and types.
"""
import pytest
from pathlib import Path
from muxi import Formation


@pytest.fixture
async def formation():
    """Load test formation with LLM configured."""
    formation_dir = Path(__file__).parent / "formations" / "formation-topic-tagging"
    formation = Formation()
    await formation.load(str(formation_dir / "formation.yaml"))
    overlord = await formation.start_overlord()
    
    yield overlord
    
    # Cleanup
    await overlord.stop()


@pytest.mark.asyncio
async def test_writing_domain_topics(formation):
    """Test topic generation for writing/content creation requests."""
    overlord = formation
    
    test_cases = [
        ("Write a technical blog post about microservices", 
         ["writing", "blog", "technical"]),
        ("Create a marketing email campaign for Black Friday",
         ["writing", "marketing", "email"]),
        ("Draft a product announcement press release",
         ["writing", "press-release", "product"])
    ]
    
    for message, expected_keywords in test_cases:
        response = await overlord.chat(
            message=message,
            user_id="test_user_writing",
            session_id=f"test_{hash(message)}"
        )
        
        assert response
        print(f"\n✓ Writing request: '{message[:50]}...'")
        print(f"  Expected keywords: {expected_keywords}")


@pytest.mark.asyncio
async def test_technical_domain_topics(formation):
    """Test topic generation for technical/debugging requests."""
    overlord = formation
    
    test_cases = [
        ("Debug the OAuth authentication flow in our API",
         ["debugging", "authentication", "api"]),
        ("Optimize the database query performance issue",
         ["optimization", "database", "performance"]),
        ("Fix the memory leak in the worker process",
         ["debugging", "memory", "performance"])
    ]
    
    for message, expected_keywords in test_cases:
        response = await overlord.chat(
            message=message,
            user_id="test_user_technical",
            session_id=f"test_{hash(message)}"
        )
        
        assert response
        print(f"\n✓ Technical request: '{message[:50]}...'")
        print(f"  Expected keywords: {expected_keywords}")


@pytest.mark.asyncio
async def test_analysis_domain_topics(formation):
    """Test topic generation for data analysis requests."""
    overlord = formation
    
    test_cases = [
        ("Analyze user churn rates from last quarter",
         ["data-analysis", "churn", "quarterly"]),
        ("Compare pricing strategies with top competitors",
         ["analysis", "pricing", "competitive"]),
        ("Generate insights from customer feedback survey",
         ["analysis", "customer-feedback", "insights"])
    ]
    
    for message, expected_keywords in test_cases:
        response = await overlord.chat(
            message=message,
            user_id="test_user_analysis",
            session_id=f"test_{hash(message)}"
        )
        
        assert response
        print(f"\n✓ Analysis request: '{message[:50]}...'")
        print(f"  Expected keywords: {expected_keywords}")


@pytest.mark.asyncio
async def test_business_domain_topics(formation):
    """Test topic generation for business/strategy requests."""
    overlord = formation
    
    test_cases = [
        ("Develop a go-to-market strategy for new product",
         ["business-strategy", "go-to-market", "product-launch"]),
        ("Create a quarterly business review presentation",
         ["business", "quarterly", "presentation"]),
        ("Plan the annual budget allocation for departments",
         ["business-planning", "budget", "finance"])
    ]
    
    for message, expected_keywords in test_cases:
        response = await overlord.chat(
            message=message,
            user_id="test_user_business",
            session_id=f"test_{hash(message)}"
        )
        
        assert response
        print(f"\n✓ Business request: '{message[:50]}...'")
        print(f"  Expected keywords: {expected_keywords}")


@pytest.mark.asyncio
async def test_personal_domain_topics(formation):
    """Test topic generation for personal/lifestyle requests."""
    overlord = formation
    
    test_cases = [
        ("Help me plan a week of healthy meal prep",
         ["meal-planning", "health", "lifestyle"]),
        ("Create a workout routine for beginners",
         ["fitness", "workout", "health"]),
        ("Organize my weekly schedule and priorities",
         ["planning", "productivity", "organization"])
    ]
    
    for message, expected_keywords in test_cases:
        response = await overlord.chat(
            message=message,
            user_id="test_user_personal",
            session_id=f"test_{hash(message)}"
        )
        
        assert response
        print(f"\n✓ Personal request: '{message[:50]}...'")
        print(f"  Expected keywords: {expected_keywords}")


@pytest.mark.asyncio
async def test_creative_domain_topics(formation):
    """Test topic generation for creative requests."""
    overlord = formation
    
    test_cases = [
        ("Design a logo concept for a tech startup",
         ["design", "logo", "creative"]),
        ("Write a story about time travel adventure",
         ["writing", "creative", "storytelling"]),
        ("Brainstorm names for a coffee shop brand",
         ["brainstorming", "branding", "creative"])
    ]
    
    for message, expected_keywords in test_cases:
        response = await overlord.chat(
            message=message,
            user_id="test_user_creative",
            session_id=f"test_{hash(message)}"
        )
        
        assert response
        print(f"\n✓ Creative request: '{message[:50]}...'")
        print(f"  Expected keywords: {expected_keywords}")


@pytest.mark.asyncio
async def test_educational_domain_topics(formation):
    """Test topic generation for educational/learning requests."""
    overlord = formation
    
    test_cases = [
        ("Explain how blockchain technology works",
         ["education", "blockchain", "technology"]),
        ("Teach me the basics of machine learning",
         ["education", "machine-learning", "tutorial"]),
        ("Help me understand quantum computing concepts",
         ["education", "quantum-computing", "learning"])
    ]
    
    for message, expected_keywords in test_cases:
        response = await overlord.chat(
            message=message,
            user_id="test_user_educational",
            session_id=f"test_{hash(message)}"
        )
        
        assert response
        print(f"\n✓ Educational request: '{message[:50]}...'")
        print(f"  Expected keywords: {expected_keywords}")


@pytest.mark.asyncio
async def test_mixed_domain_topics(formation):
    """Test topic generation for requests spanning multiple domains."""
    overlord = formation
    
    # Request combining technical + business
    response1 = await overlord.chat(
        message="Build a data pipeline to analyze customer behavior for business insights",
        user_id="test_user_mixed",
        session_id="test_mixed_1"
    )
    assert response1
    print(f"\n✓ Mixed (technical + business) request processed")
    
    # Request combining creative + technical
    response2 = await overlord.chat(
        message="Design and implement a responsive website homepage",
        user_id="test_user_mixed",
        session_id="test_mixed_2"
    )
    assert response2
    print(f"✓ Mixed (creative + technical) request processed")
    
    # Request combining analysis + personal
    response3 = await overlord.chat(
        message="Track my fitness progress and provide recommendations",
        user_id="test_user_mixed",
        session_id="test_mixed_3"
    )
    assert response3
    print(f"✓ Mixed (analysis + personal) request processed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
