"""
Day 1 - Test Group 1B: Basic Agent Communication Tests

Tests basic agent responses and multi-agent routing functionality.
"""
import pytest
import asyncio
from concurrent.futures import ThreadPoolExecutor
from muxi.runtime.formation import Formation


class TestBasicCommunication:
    """Test Group 1B: Basic Agent Communication"""
    
    def test_1b1_single_agent_response(self):
        """Test 1B1: Single Agent Response"""
        def run_test():
            # Load single-agent formation
            formation = Formation()
            formation.load("test-formations/formation-basic/")
            overlord = formation.start_overlord()
            
            # Test basic helpfulness query
            response = asyncio.run(overlord.chat("What can you help me with?"))
            assert response is not None
            assert len(response) > 0
            
            # Verify response mentions helping (case-insensitive)
            response_lower = response.lower()
            assert any(word in response_lower for word in ["help", "assist", "support", "can"])
            
            # Test another simple interaction
            response2 = asyncio.run(overlord.chat("Tell me a fun fact"))
            assert response2 is not None
            assert len(response2) > 0
            
            formation.stop_overlord()
        
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            future.result()
    
    def test_1b2_agent_routing_validation(self):
        """Test 1B2: Agent Routing Validation"""
        def run_test():
            # Load multi-agent formation
            formation = Formation()
            formation.load("test-formations/formation-multi-agent/")
            overlord = formation.start_overlord()
            
            # Test 1: Math query should route to appropriate agent
            response = asyncio.run(overlord.chat("Calculate 2+2"))
            assert response is not None
            assert "4" in response
            
            # Test 2: Different types of queries for routing
            # Research query
            research_response = asyncio.run(overlord.chat("What are the latest trends in renewable energy?"))
            assert research_response is not None
            assert len(research_response) > 50  # Should be substantive
            
            # General query
            general_response = asyncio.run(overlord.chat("How are you today?"))
            assert general_response is not None
            
            formation.stop_overlord()
        
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            future.result()
    
    def test_1b_response_consistency(self):
        """Additional Test: Response Consistency"""
        def run_test():
            # Ensure agents provide consistent quality responses
            formation = Formation()
            formation.load("test-formations/formation-basic/")
            overlord = formation.start_overlord()
            
            # Multiple queries to test consistency
            queries = [
                "Hello",
                "What's the weather like?",
                "Can you help me learn Python?",
                "What's 10 divided by 2?"
            ]
            
            responses = []
            for query in queries:
                response = asyncio.run(overlord.chat(query))
                assert response is not None
                assert len(response) > 0
                assert not response.isspace()  # Not just whitespace
                responses.append(response)
            
            # All responses should be unique (not canned responses)
            assert len(set(responses)) == len(responses)
            
            formation.stop_overlord()
        
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            future.result()
    
    def test_1b_error_handling(self):
        """Additional Test: Basic Error Handling in Communication"""
        def run_test():
            formation = Formation()
            formation.load("test-formations/formation-basic/")
            overlord = formation.start_overlord()
            
            # Test with empty message
            response = asyncio.run(overlord.chat(""))
            # Should handle gracefully, possibly ask for clarification
            assert response is not None
            
            # Test with very long message
            long_message = "Please help me with " + " and ".join([f"task {i}" for i in range(100)])
            response = asyncio.run(overlord.chat(long_message))
            assert response is not None
            
            formation.stop_overlord()
        
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            future.result()