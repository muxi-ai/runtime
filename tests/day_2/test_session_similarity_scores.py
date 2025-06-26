"""Test that similarity scores are preserved with session_id"""
import sys
sys.path.insert(0, '.')
import pytest
import asyncio
from src.muxi.runtime.services.memory.short_term import ShortTermMemory

# Mock LLM for testing
class MockLLM:
    """Mock LLM that returns consistent embeddings for same text"""
    def __init__(self):
        self.embed_count = 0
        
    async def embed(self, text):
        # Generate consistent embeddings based on text content
        self.embed_count += 1
        # Use hash to ensure same text gets same embedding
        text_hash = hash(text)
        base_value = (text_hash % 1000) / 1000.0
        embedding = [base_value] + [0.1] * 1535
        return embedding


@pytest.mark.asyncio
async def test_similarity_scores_with_session():
    """Test that similarity scores remain consistent with and without session_id"""
    # Create model and buffer
    model = MockLLM()
    buffer = ShortTermMemory(
        max_size=10,
        buffer_multiplier=2,
        model=model,
        mode="local"
    )
    
    # Test data
    test_messages = [
        "I love Python programming",
        "Machine learning is fascinating",
        "JavaScript is good for web development",
        "Deep learning with PyTorch is powerful",
        "I enjoy cooking Italian food"
    ]
    
    # Add messages WITHOUT session_id
    print("\n=== Adding messages WITHOUT session_id ===")
    for msg in test_messages:
        await buffer.add(msg, {"role": "user"})
    
    # Search for exact match without session_id
    query = "I love Python programming"
    results_no_session = await buffer.search(query, limit=1)
    
    print(f"\nSearch for '{query}' WITHOUT session_id:")
    if results_no_session:
        score_no_session = results_no_session[0].get('score', 0)
        print(f"  Text: {results_no_session[0]['text']}")
        print(f"  Score: {score_no_session}")
    
    # Clear buffer and add messages WITH session_id
    buffer.clear()
    session_id = "test-session-123"
    
    print("\n=== Adding messages WITH session_id ===")
    for msg in test_messages:
        await buffer.add(msg, {"role": "user", "session_id": session_id})
    
    # Search for exact match WITH session_id
    results_with_session = await buffer.search(query, limit=1, session_id=session_id)
    
    print(f"\nSearch for '{query}' WITH session_id:")
    if results_with_session:
        score_with_session = results_with_session[0].get('score', 0)
        print(f"  Text: {results_with_session[0]['text']}")
        print(f"  Score: {score_with_session}")
    
    # Also search without passing session_id to see base score
    results_no_session_param = await buffer.search(query, limit=1)
    
    print(f"\nSearch for '{query}' (has session in metadata but not in search):")
    if results_no_session_param:
        score_no_session_param = results_no_session_param[0].get('score', 0)
        print(f"  Text: {results_no_session_param[0]['text']}")
        print(f"  Score: {score_no_session_param}")
    
    # Verify scores
    print("\n=== Score Comparison ===")
    print(f"Score without session_id in data: {score_no_session}")
    print(f"Score with session_id match: {score_with_session}")
    print(f"Score with session_id in data but not search: {score_no_session_param}")
    
    # The key test: when not using session weighting, scores should be the same
    assert abs(score_no_session - score_no_session_param) < 0.01, \
        f"Scores should be similar when not using session weighting: {score_no_session} vs {score_no_session_param}"
    
    # With session match, score might be different due to session boost
    print(f"\nSession boost effect: {score_with_session - score_no_session_param:.3f}")
    
    # Both should still be high scores for exact match
    assert score_no_session > 0.9, f"Exact match without session should have high score: {score_no_session}"
    assert score_no_session_param > 0.9, f"Exact match should have high score: {score_no_session_param}"
    
    print("\n✅ Similarity scores are preserved correctly!")


if __name__ == "__main__":
    asyncio.run(test_similarity_scores_with_session())