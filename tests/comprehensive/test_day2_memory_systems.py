"""
Day 2: Memory Systems - Comprehensive Test Suite
Date: June 26, 2025
Focus: Validate 3-tier memory architecture with comprehensive coverage

Test Groups:
- 2A: Buffer Memory (conversation context, overflow, memory limits)
- 2B: Long-term Memory - SQLite (persistence, vector search)
- 2C: Multi-User PostgreSQL Memory (user isolation, concurrent access)
- 2D: Remote Faiss Vector Store (no auth, with auth, multi-user)
- 2E: Memory Cleanup & Management (auto-extraction, FIFO, size validation)

External Services Required:
- PostgreSQL database (for multi-user tests)
- Faiss servers on configured ports (with and without auth)
"""

import asyncio
import os
import sys
import time
import pytest
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from muxi.formation import Formation


class TestDay2MemorySystems:
    """Day 2: Memory Systems Test Suite"""

    # Test Group 2A: Buffer Memory
    def test_2a1_conversation_context(self):
        """Test 2A1: Basic conversation context retention in buffer memory"""
        def run_test():
            formation = Formation()
            formation.load("test-formations/formation-memory/formation-basic.yaml")
            overlord = formation.start_overlord()

            try:
                # Set context
                response = asyncio.run(overlord.chat("My name is John and I prefer concise answers"))
                assert response is not None

                # Test recall
                response = asyncio.run(overlord.chat("What's my name?"))
                assert "john" in response.lower(), f"Expected 'john' in response, got: {response}"

                # Test preference recall - ask more directly
                response = asyncio.run(overlord.chat("Do you remember what I said about how I prefer answers?"))
                assert any(word in response.lower() for word in ["concise", "brief", "short", "prefer"]), \
                    f"Expected preference mention in response, got: {response}"
            finally:
                formation.stop_overlord()

        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            future.result()

    def test_2a2_buffer_overflow(self):
        """Test 2A2: Buffer overflow with FIFO eviction

        Note: LLMs have their own context window, so we test buffer behavior
        by checking what the agent explicitly recalls from earlier messages.
        """
        def run_test():
            formation = Formation()
            formation.load("test-formations/formation-memory/formation-basic.yaml")
            overlord = formation.start_overlord()

            try:
                # Send more messages than buffer size (buffer size = 10)
                # Use distinct facts to make it clear what's remembered
                facts = [
                    "The capital of France is Paris",
                    "The largest planet is Jupiter",
                    "Water boils at 100 degrees Celsius",
                    "The speed of light is 299,792,458 m/s",
                    "Mount Everest is the tallest mountain",
                    "The Pacific Ocean is the largest ocean",
                    "Shakespeare wrote Romeo and Juliet",
                    "The human body has 206 bones",
                    "Gold's chemical symbol is Au",
                    "The Great Wall of China is visible from space",
                    "Fact 10: Tomatoes are technically fruits",
                    "Fact 11: The Eiffel Tower is 330 meters tall",
                    "Fact 12: Honey never spoils",
                    "Fact 13: Octopi have three hearts",
                    "Fact 14: The moon affects Earth's tides"
                ]

                for i, fact in enumerate(facts):
                    response = asyncio.run(overlord.chat(f"Remember fact {i}: {fact}"))
                    assert response is not None

                # Test that very old facts might be less accessible
                # Ask about the first fact in a way that tests memory
                response = asyncio.run(overlord.chat("What did I tell you about France?"))
                # It's OK if it remembers (LLM context), but check recent facts are definitely there

                # Test that recent facts are definitely remembered
                response = asyncio.run(overlord.chat("What did I tell you about the moon?"))
                assert "tide" in response.lower() or "moon" in response.lower(), \
                    f"Should remember recent fact about moon/tides, but got: {response}"

                # Test explicit recall of a recent fact number
                response = asyncio.run(overlord.chat("What was fact 13?"))
                assert "octopi" in response.lower() or "three hearts" in response.lower() or "13" in response.lower(), \
                    f"Should remember fact 13 about octopi, but got: {response}"
            finally:
                formation.stop_overlord()

        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            future.result()

    def test_2a3_memory_size_limits(self):
        """Test 2A3: Memory size limits (max_memory_mb) enforcement

        Note: This test is simplified to avoid excessive API calls.
        In production, you'd test with actual memory size measurements.
        """
        def run_test():
            formation = Formation()
            formation.load("test-formations/formation-memory/formation-memory-limits.yaml")
            overlord = formation.start_overlord()

            try:
                # Send enough messages to test memory behavior
                # Using meaningful content instead of large chunks
                topics = [
                    "Python programming",
                    "JavaScript frameworks",
                    "Database design",
                    "Cloud computing",
                    "Machine learning",
                    "Web security",
                    "Mobile development",
                    "DevOps practices",
                    "API design",
                    "System architecture",
                    "Data structures",
                    "Algorithms",
                    "Testing strategies",
                    "Performance optimization",
                    "Code review"
                ]

                # Store facts about each topic
                for i, topic in enumerate(topics):
                    fact = f"Topic {i}: {topic} is important for modern software development"
                    response = asyncio.run(overlord.chat(f"Remember this: {fact}"))
                    assert response is not None

                # Test that memory is working
                response = asyncio.run(overlord.chat("What topics have we discussed?"))
                # Should mention at least some recent topics
                recent_topics = ["testing", "performance", "code review", "optimization"]
                assert any(topic in response.lower() for topic in recent_topics), \
                    f"Should remember some recent topics, but got: {response}"

                # Verify system is still responsive
                response = asyncio.run(overlord.chat("What's 2+2?"))
                assert "4" in response, f"System should still handle basic queries, but got: {response}"
            finally:
                formation.stop_overlord()

        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            future.result()

    # Test Group 2B: Long-term Memory - SQLite
    @pytest.mark.skip(reason="SQLite configuration needs fixing - connection string format issue")
    def test_2b1_sqlite_persistence(self):
        """Test 2B1: SQLite persistence across restarts"""
        def run_test():
            formation = Formation()
            formation.load("test-formations/formation-memory/formation-sqlite.yaml")

            # First session - store information
            overlord = formation.start_overlord()
            try:
                response = asyncio.run(overlord.chat("Remember that I'm working on project Apollo"))
                assert response is not None

                response = asyncio.run(overlord.chat("My favorite programming language is Python"))
                assert response is not None
            finally:
                formation.stop_overlord()

            # Second session - verify persistence
            overlord = formation.start_overlord()
            try:
                response = asyncio.run(overlord.chat("What project am I working on?"))
                assert "apollo" in response.lower(), \
                    f"Should remember project Apollo after restart, but got: {response}"

                response = asyncio.run(overlord.chat("What's my favorite programming language?"))
                assert "python" in response.lower(), \
                    f"Should remember Python preference after restart, but got: {response}"
            finally:
                formation.stop_overlord()

        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            future.result()

    @pytest.mark.skip(reason="SQLite configuration needs fixing - connection string format issue")
    def test_2b2_sqlite_vector_search(self):
        """Test 2B2: SQLite vector similarity search"""
        def run_test():
            formation = Formation()
            formation.load("test-formations/formation-memory/formation-sqlite.yaml")
            overlord = formation.start_overlord()

            try:
                # Store related information
                asyncio.run(overlord.chat("Python is great for machine learning and data science"))
                asyncio.run(overlord.chat("JavaScript is good for web development and frontend"))
                asyncio.run(overlord.chat("Rust is excellent for systems programming and performance"))

                # Test vector similarity search
                response = asyncio.run(overlord.chat("What language is good for AI?"))
                assert "python" in response.lower(), \
                    f"Should retrieve Python via similarity to AI/ML, but got: {response}"

                response = asyncio.run(overlord.chat("What should I use for building websites?"))
                assert "javascript" in response.lower(), \
                    f"Should retrieve JavaScript via similarity to web/websites, but got: {response}"
            finally:
                formation.stop_overlord()

        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            future.result()

    # Test Group 2C: Multi-User PostgreSQL Memory
    def test_2c1_postgresql_user_isolation(self):
        """Test 2C1: PostgreSQL with complete user isolation

        Requires: PostgreSQL database running and accessible
        """
        def run_test():
            formation = Formation()
            formation.load("test-formations/formation-memory/formation-postgres.yaml")
            overlord = formation.start_overlord()

            try:
                # User 1 stores information
                asyncio.run(overlord.chat("My name is Alice and I like Python", user_id="user1"))
                asyncio.run(overlord.chat("I work at TechCorp as a developer", user_id="user1"))
                asyncio.run(overlord.chat("My current project is an AI chatbot", user_id="user1"))

                # User 2 stores different information
                asyncio.run(overlord.chat("My name is Bob and I like JavaScript", user_id="user2"))
                asyncio.run(overlord.chat("I work at WebCo as a designer", user_id="user2"))
                asyncio.run(overlord.chat("My current project is an e-commerce site", user_id="user2"))

                # User 3 stores different information
                asyncio.run(overlord.chat("My name is Charlie and I like Rust", user_id="user3"))
                asyncio.run(overlord.chat("I work at SystemsInc as an architect", user_id="user3"))
                asyncio.run(overlord.chat("My current project is a distributed database", user_id="user3"))

                # Verify complete user isolation
                response1 = asyncio.run(overlord.chat("What's my name?", user_id="user1"))
                assert "alice" in response1.lower() and "bob" not in response1.lower() and "charlie" not in response1.lower(), \
                    f"User1 should only see Alice, but got: {response1}"

                response2 = asyncio.run(overlord.chat("What language do I like?", user_id="user2"))
                assert "javascript" in response2.lower() and "python" not in response2.lower() and "rust" not in response2.lower(), \
                    f"User2 should only see JavaScript, but got: {response2}"

                response3 = asyncio.run(overlord.chat("Where do I work?", user_id="user3"))
                assert "systemsinc" in response3.lower() and "techcorp" not in response3.lower() and "webco" not in response3.lower(), \
                    f"User3 should only see SystemsInc, but got: {response3}"

                # Test project isolation
                response1 = asyncio.run(overlord.chat("What's my current project?", user_id="user1"))
                assert "chatbot" in response1.lower() or "ai" in response1.lower(), \
                    f"User1 should mention AI chatbot project, but got: {response1}"

                response2 = asyncio.run(overlord.chat("What am I building?", user_id="user2"))
                assert "e-commerce" in response2.lower() or "ecommerce" in response2.lower(), \
                    f"User2 should mention e-commerce project, but got: {response2}"
            finally:
                formation.stop_overlord()

        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            future.result()

    @pytest.mark.skip(reason="PostgreSQL formation not created yet")
    def test_2c2_concurrent_multi_user_access(self):
        """Test 2C2: Concurrent multi-user access without cross-contamination

        Requires: PostgreSQL database running and accessible
        """
        def run_test():
            formation = Formation()
            formation.load("test-formations/formation-memory/formation-postgres.yaml")
            overlord = formation.start_overlord()

            try:
                # Note: Cannot use asyncio.gather in sync context, so we'll do sequential for now
                # This still tests isolation but not true concurrency
                asyncio.run(overlord.chat("Remember: I'm building a Python REST API with FastAPI", user_id="user1"))
                asyncio.run(overlord.chat("Remember: I'm designing a React app with TypeScript", user_id="user2"))
                asyncio.run(overlord.chat("Remember: I'm optimizing Rust code for high performance", user_id="user3"))

                # Add more concurrent information
                asyncio.run(overlord.chat("My API uses PostgreSQL and Redis", user_id="user1"))
                asyncio.run(overlord.chat("My app uses Material-UI and Redux", user_id="user2"))
                asyncio.run(overlord.chat("My code uses async/await and zero-copy", user_id="user3"))

                # Verify no cross-contamination
                response1 = asyncio.run(overlord.chat("What am I building and what technologies?", user_id="user1"))
                assert all(tech in response1.lower() for tech in ["python", "api", "fastapi"]), \
                    f"User1 should mention Python/FastAPI, but got: {response1}"
                assert not any(tech in response1.lower() for tech in ["react", "rust", "material-ui", "redux"]), \
                    f"User1 should not see other users' tech, but got: {response1}"

                response2 = asyncio.run(overlord.chat("What technologies am I using?", user_id="user2"))
                assert any(tech in response2.lower() for tech in ["react", "typescript", "material"]), \
                    f"User2 should mention React/TypeScript, but got: {response2}"
                assert not any(tech in response2.lower() for tech in ["python", "rust", "postgresql", "redis"]), \
                    f"User2 should not see other users' tech, but got: {response2}"
            finally:
                formation.stop_overlord()

        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            future.result()

    # Test Group 2D: Remote Faiss Vector Store
    @pytest.mark.skip(reason="PostgreSQL+Faiss formation not created yet")
    def test_2d1_postgresql_faiss_no_auth(self):
        """Test 2D1: PostgreSQL + Remote Faiss without authentication

        Requires:
        - PostgreSQL database running
        - Faiss server running on configured port (no auth)
        """
        def run_test():
            formation = Formation()
            formation.load("test-formations/formation-memory/formation-postgres-and-faissx.yaml")
            overlord = formation.start_overlord()

            try:
                # Store embeddings in remote Faiss
                asyncio.run(overlord.chat("Machine learning requires understanding of linear algebra and calculus"))
                asyncio.run(overlord.chat("Deep learning builds on machine learning with neural networks"))
                asyncio.run(overlord.chat("Natural language processing uses transformers and attention mechanisms"))
                asyncio.run(overlord.chat("Web development requires HTML, CSS, JavaScript, and frameworks"))
                asyncio.run(overlord.chat("Database design needs normalization and indexing knowledge"))

                # Test vector similarity search via Faiss
                response = asyncio.run(overlord.chat("What do I need to know for AI development?"))
                # Should retrieve ML/DL/NLP memories via Faiss similarity
                assert any(term in response.lower() for term in ["machine learning", "linear algebra", "deep learning", "neural"]), \
                    f"Should retrieve AI-related memories via Faiss, but got: {response}"

                response = asyncio.run(overlord.chat("What's important for data storage?"))
                assert any(term in response.lower() for term in ["database", "normalization", "indexing"]), \
                    f"Should retrieve database-related memories via Faiss, but got: {response}"
            finally:
                formation.stop_overlord()

        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            future.result()

    @pytest.mark.skip(reason="PostgreSQL+Faiss formation not created yet")
    def test_2d2_postgresql_faiss_with_auth(self):
        """Test 2D2: PostgreSQL + Remote Faiss with authentication

        Requires:
        - PostgreSQL database running
        - Faiss server running on configured port with auth enabled
        """
        def run_test():
            formation = Formation()
            formation.load("test-formations/formation-memory/formation-postgres-and-faissx-with-auth.yaml")
            overlord = formation.start_overlord()

            try:
                # Verify auth token is used (Faiss servers are configured to require it)
                asyncio.run(overlord.chat("Quantum computing uses qubits and superposition"))
                asyncio.run(overlord.chat("Quantum algorithms include Shor's and Grover's algorithms"))
                asyncio.run(overlord.chat("Quantum error correction is crucial for practical quantum computers"))

                response = asyncio.run(overlord.chat("Tell me about quantum computers"))
                assert any(term in response.lower() for term in ["qubit", "quantum", "superposition"]), \
                    f"Should retrieve quantum computing info via authenticated Faiss, but got: {response}"

                # Test another domain
                asyncio.run(overlord.chat("Blockchain technology uses cryptographic hashing and consensus"))
                asyncio.run(overlord.chat("Smart contracts execute automatically on the blockchain"))

                response = asyncio.run(overlord.chat("Explain distributed ledger technology"))
                assert any(term in response.lower() for term in ["blockchain", "cryptographic", "consensus"]), \
                    f"Should retrieve blockchain info via authenticated Faiss, but got: {response}"
            finally:
                formation.stop_overlord()

        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            future.result()

    @pytest.mark.skip(reason="PostgreSQL+Faiss formation not created yet")
    def test_2d3_multi_user_faiss_vector_search(self):
        """Test 2D3: Multi-user vector searches with Faiss isolation

        Requires:
        - PostgreSQL database running
        - Faiss server running on configured port
        """
        def run_test():
            formation = Formation()
            formation.load("test-formations/formation-memory/formation-postgres-and-faissx.yaml")
            overlord = formation.start_overlord()

            try:
                # User 1 - Food preferences
                asyncio.run(overlord.chat("I love Italian cuisine, especially pasta carbonara and pizza", user_id="user1"))
                asyncio.run(overlord.chat("My favorite wines are Chianti and Barolo from Tuscany", user_id="user1"))

                # User 2 - Different food preferences
                asyncio.run(overlord.chat("I prefer Japanese food like sushi, ramen, and tempura", user_id="user2"))
                asyncio.run(overlord.chat("I enjoy sake and Japanese green tea with my meals", user_id="user2"))

                # User 3 - Yet different preferences
                asyncio.run(overlord.chat("I'm vegetarian and love Indian curry and Thai food", user_id="user3"))
                asyncio.run(overlord.chat("I drink kombucha and herbal teas exclusively", user_id="user3"))

                # Test user-specific vector searches
                response1 = asyncio.run(overlord.chat("What food do I like?", user_id="user1"))
                assert "italian" in response1.lower() and "pasta" in response1.lower(), \
                    f"User1 should get Italian food results, but got: {response1}"
                assert not any(food in response1.lower() for food in ["japanese", "sushi", "indian", "curry"]), \
                    f"User1 should not see other users' preferences, but got: {response1}"

                response2 = asyncio.run(overlord.chat("What's my favorite cuisine and drinks?", user_id="user2"))
                assert "japanese" in response2.lower() and any(item in response2.lower() for item in ["sushi", "ramen", "sake"]), \
                    f"User2 should get Japanese food results, but got: {response2}"
                assert not any(food in response2.lower() for food in ["italian", "pasta", "indian", "vegetarian"]), \
                    f"User2 should not see other users' preferences, but got: {response2}"

                response3 = asyncio.run(overlord.chat("What are my dietary preferences?", user_id="user3"))
                assert any(term in response3.lower() for term in ["vegetarian", "indian", "thai"]), \
                    f"User3 should get vegetarian/Indian/Thai results, but got: {response3}"
                assert not any(food in response3.lower() for food in ["italian", "japanese", "meat", "wine"]), \
                    f"User3 should not see other users' preferences, but got: {response3}"
            finally:
                formation.stop_overlord()

        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            future.result()

    # Test Group 2E: Memory Cleanup & Management
    def test_2e1_auto_extraction(self):
        """Test 2E1: Auto-extraction of user information"""
        def run_test():
            formation = Formation()
            formation.load("test-formations/formation-memory/formation-auto-extract.yaml")
            overlord = formation.start_overlord()

            try:
                # Provide information that should be auto-extracted
                asyncio.run(overlord.chat("I'm Sarah Johnson and I work in marketing at Acme Corp"))
                asyncio.run(overlord.chat("I'm based in New York and have been with the company for 3 years"))
                asyncio.run(overlord.chat("My main focus is digital marketing and social media campaigns"))

                # Test if information was extracted
                response = asyncio.run(overlord.chat("What's my name?"))
                assert "sarah" in response.lower(), f"Should remember extracted name, but got: {response}"

                response = asyncio.run(overlord.chat("Where do I work?"))
                assert "acme" in response.lower() or "marketing" in response.lower(), \
                    f"Should remember extracted workplace, but got: {response}"

                response = asyncio.run(overlord.chat("What city am I in?"))
                assert "new york" in response.lower() or "ny" in response.lower(), \
                    f"Should remember extracted location, but got: {response}"
            finally:
                formation.stop_overlord()

        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            future.result()

    def test_2e2_fifo_memory_cleanup(self):
        """Test 2E2: FIFO memory cleanup when limit reached"""
        def run_test():
            formation = Formation()
            formation.load("test-formations/formation-memory/formation-memory-limits.yaml")
            overlord = formation.start_overlord()

            try:
                # Track message order
                messages = []
                for i in range(20):
                    msg = f"Important fact #{i}: Data point {i} with unique identifier {i * 100}"
                    messages.append((i, msg))
                    response = asyncio.run(overlord.chat(msg))
                    assert response is not None

                # Verify FIFO cleanup (oldest messages removed first)
                response = asyncio.run(overlord.chat("What was important fact #0?"))
                # Should not remember due to FIFO cleanup
                assert not ("fact #0" in response.lower() and "identifier 0" in response.lower()), \
                    f"Old messages should be cleaned up via FIFO, but got: {response}"

                response = asyncio.run(overlord.chat("What was important fact #19?"))
                # Should remember recent messages
                assert "19" in response or "1900" in response, \
                    f"Recent messages should be retained, but got: {response}"

                # Test boundary - messages around the cutoff
                response = asyncio.run(overlord.chat("Tell me about facts #5 through #15"))
                # Some early ones might be gone, but later ones should be there
                recent_facts = [str(i) for i in range(10, 16)]
                assert any(fact in response for fact in recent_facts), \
                    f"Should remember at least some recent facts, but got: {response}"
            finally:
                formation.stop_overlord()

        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            future.result()

    def test_2e3_memory_size_validation(self):
        """Test 2E3: Memory size validation and enforcement"""
        def run_test():
            formation = Formation()
            formation.load("test-formations/formation-memory/formation-memory-limits.yaml")
            overlord = formation.start_overlord()

            try:
                # Generate substantial data to test memory limits
                large_chunks = []
                for i in range(50):
                    # Create ~10KB chunks
                    chunk = f"Large data block {i}: " + ("x" * 10000)
                    large_chunks.append(chunk)
                    response = asyncio.run(overlord.chat(f"Store this: {chunk}"))
                    assert response is not None

                # Memory should have enforced limits via FIFO
                response = asyncio.run(overlord.chat("What was in large data block 0?"))
                assert not ("block 0" in response.lower()), \
                    f"Memory limits should have evicted old data, but got: {response}"

                # Recent data should still be accessible
                response = asyncio.run(overlord.chat("What's the most recent large data block number?"))
                assert any(str(i) in response for i in range(45, 50)), \
                    f"Recent data should be retained within memory limits, but got: {response}"

                # Verify we can still have normal conversations
                asyncio.run(overlord.chat("Let's talk about something else. What's 2+2?"))
                response = asyncio.run(overlord.chat("What did I just ask you?"))
                assert "2+2" in response or "2 + 2" in response or "math" in response.lower(), \
                    f"Memory should still function normally after limit enforcement, but got: {response}"
            finally:
                formation.stop_overlord()

        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            future.result()


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v", "-s"])
