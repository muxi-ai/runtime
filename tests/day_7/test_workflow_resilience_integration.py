"""
Test the resilience integration with workflow execution.

This test verifies that the ResilientWorkflowExecutor provides better
error messages when MCP tools fail.
"""

import pytest
import asyncio
from typing import Dict, Any, Optional
from unittest.mock import AsyncMock, patch

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

from muxi.runtime.formation import Formation
from muxi.runtime.datatypes.muxi import MuxiRequest, MuxiResponse
from muxi.runtime.datatypes.workflow import Workflow, TaskStatus


class TestWorkflowResilienceIntegration:
    """Test resilience features in workflow execution."""

    async def test_mcp_tool_timeout_with_resilience(self):
        """Test that MCP tool timeouts produce user-friendly error messages."""
        
        # Create formation with resilience enabled
        formation_config = {
            "name": "test-resilience-formation",
            "version": "1.0.0",
            "llm": {
                "models": [
                    {
                        "text": "openai/gpt-4o-mini",
                        "temperature": 0.3
                    }
                ]
            },
            "agents": [
                {
                    "id": "research-agent",
                    "name": "Research Agent",
                    "description": "Agent that uses MCP tools for research",
                    "capabilities": ["research", "web_search"],
                    "model": "openai/gpt-4o-mini",
                    "max_concurrent_tasks": 1
                }
            ],
            "overlord": {
                "config": {
                    "workflow": {
                        "auto_decomposition": True,
                        "complexity_threshold": 3.0,
                        "plan_approval_threshold": 10
                    }
                }
            },
            "resilience": {
                "enable_workflow_resilience": True,
                "enable_circuit_breaker": True,
                "enable_recovery_strategies": True,
                "enable_fallbacks": True,
                "circuit_breaker": {
                    "failure_threshold": 2,
                    "timeout": 30,
                    "half_open_attempts": 1
                }
            },
            "memory": {
                "working": {
                    "enabled": True,
                    "max_size": 1000
                },
                "buffer": {
                    "enabled": True,
                    "max_messages": 50
                }
            }
        }
        
        # Create formation
        formation = Formation()
        await formation.load_from_dict(formation_config)
        overlord = await formation.start_overlord()
        
        # Mock the MCP tool to simulate timeout
        with patch.object(
            overlord.agents["research-agent"],
            "process_message",
            side_effect=asyncio.TimeoutError("MCP tool timeout while connecting to web search")
        ):
            # Send a request that would normally use MCP tools
            response = await overlord.chat(
                "Search for the latest news about AI and summarize it",
                user_id="test-user",
                session_id="test-session"
            )
            
            # Verify we get a user-friendly error message
            assert response.role == "assistant"
            assert isinstance(response.content, str)
            
            # Check for specific resilience-aware messaging
            assert any(phrase in response.content.lower() for phrase in [
                "technical difficulties",
                "external services",
                "based on my knowledge",
                "connectivity",
                "taking longer than expected"
            ]), f"Expected user-friendly error message, got: {response.content}"
            
            # Should not contain generic error messages
            assert "there was an error" not in response.content.lower()
            assert "exception" not in response.content.lower()
            assert "traceback" not in response.content.lower()

    async def test_authentication_failure_with_resilience(self):
        """Test that authentication failures produce actionable error messages."""
        
        # Create formation
        formation_config = {
            "name": "test-auth-resilience",
            "version": "1.0.0",
            "llm": {
                "models": [
                    {
                        "text": "openai/gpt-4o-mini",
                        "temperature": 0.3
                    }
                ]
            },
            "agents": [
                {
                    "id": "linear-agent",
                    "name": "Linear Agent",
                    "description": "Agent that creates Linear issues",
                    "capabilities": ["issue_tracking", "linear"],
                    "model": "openai/gpt-4o-mini"
                }
            ],
            "overlord": {
                "config": {
                    "workflow": {
                        "auto_decomposition": True,
                        "complexity_threshold": 3.0
                    }
                }
            },
            "resilience": {
                "enable_workflow_resilience": True,
                "enable_recovery_strategies": True,
                "enable_fallbacks": True
            },
            "memory": {
                "working": {
                    "enabled": True,
                    "max_size": 1000
                }
            }
        }
        
        formation = Formation()
        await formation.load_from_dict(formation_config)
        overlord = await formation.start_overlord()
        
        # Mock authentication failure
        with patch.object(
            overlord.agents["linear-agent"],
            "process_message",
            side_effect=Exception("401 Unauthorized: Invalid Linear API credentials")
        ):
            response = await overlord.chat(
                "Create a Linear issue for the new feature",
                user_id="test-user"
            )
            
            # Should get actionable guidance
            assert response.role == "assistant"
            content_lower = response.content.lower()
            
            # Check for authentication-specific messaging
            assert any(phrase in content_lower for phrase in [
                "credentials",
                "authentication",
                "don't have the proper",
                "check that"
            ]), f"Expected authentication guidance, got: {response.content}"
            
            # Should not expose raw error
            assert "401 unauthorized" not in content_lower
            assert "invalid linear api" not in content_lower

    async def test_partial_workflow_completion_with_resilience(self):
        """Test that partially completed workflows provide useful partial results."""
        
        formation_config = {
            "name": "test-partial-resilience",
            "version": "1.0.0",
            "llm": {
                "models": [
                    {
                        "text": "openai/gpt-4o-mini",
                        "temperature": 0.3
                    }
                ]
            },
            "agents": [
                {
                    "id": "agent-1",
                    "name": "Working Agent",
                    "description": "Agent that works",
                    "capabilities": ["analysis"],
                    "model": "openai/gpt-4o-mini"
                },
                {
                    "id": "agent-2",
                    "name": "Failing Agent",
                    "description": "Agent that fails",
                    "capabilities": ["special_task"],
                    "model": "openai/gpt-4o-mini"
                }
            ],
            "overlord": {
                "config": {
                    "workflow": {
                        "auto_decomposition": True,
                        "complexity_threshold": 2.0
                    }
                }
            },
            "resilience": {
                "enable_workflow_resilience": True,
                "enable_fallbacks": True,
                "enable_partial_responses": True
            },
            "memory": {
                "working": {
                    "enabled": True,
                    "max_size": 1000
                }
            }
        }
        
        formation = Formation()
        await formation.load_from_dict(formation_config)
        overlord = await formation.start_overlord()
        
        # Create a mock that makes agent-1 succeed but agent-2 fail
        original_execute = overlord.workflow_executor._execute_task_with_agent
        
        async def mock_execute(task, agent, context):
            if agent.agent_id == "agent-1":
                # Let first agent succeed normally
                task.status = TaskStatus.DONE
                return {
                    "task_id": task.id,
                    "status": TaskStatus.DONE,
                    "outputs": {"content": "Analysis complete: Data shows positive trends"},
                    "success": True
                }
            else:
                # Make second agent fail
                raise Exception("Network error: Unable to connect to special service")
        
        with patch.object(
            overlord.workflow_executor,
            "_execute_task_with_agent",
            side_effect=mock_execute
        ):
            response = await overlord.chat(
                "Analyze the data and then perform the special task",
                user_id="test-user"
            )
            
            # Should get partial results
            assert response.role == "assistant"
            assert "analysis complete" in response.content.lower()
            assert "positive trends" in response.content.lower()
            
            # Should explain what couldn't be completed
            assert any(phrase in response.content.lower() for phrase in [
                "unable to",
                "couldn't complete",
                "special task",
                "partial"
            ])

    async def test_circuit_breaker_activation(self):
        """Test that circuit breaker prevents cascading failures."""
        
        formation_config = {
            "name": "test-circuit-breaker",
            "version": "1.0.0",
            "llm": {
                "models": [
                    {
                        "text": "openai/gpt-4o-mini"
                    }
                ]
            },
            "agents": [
                {
                    "id": "flaky-agent",
                    "name": "Flaky Agent",
                    "description": "Agent that fails repeatedly",
                    "capabilities": ["flaky_task"],
                    "model": "openai/gpt-4o-mini"
                }
            ],
            "overlord": {
                "config": {
                    "workflow": {
                        "auto_decomposition": True,
                        "complexity_threshold": 2.0
                    }
                }
            },
            "resilience": {
                "enable_workflow_resilience": True,
                "enable_circuit_breaker": True,
                "circuit_breaker": {
                    "failure_threshold": 2,  # Open after 2 failures
                    "timeout": 10,
                    "half_open_attempts": 1
                }
            },
            "memory": {
                "working": {
                    "enabled": True
                }
            }
        }
        
        formation = Formation()
        await formation.load_from_dict(formation_config)
        overlord = await formation.start_overlord()
        
        # Mock repeated failures
        failure_count = 0
        
        async def mock_failing_agent(message, **kwargs):
            nonlocal failure_count
            failure_count += 1
            raise Exception(f"Service unavailable (attempt {failure_count})")
        
        with patch.object(
            overlord.agents["flaky-agent"],
            "process_message",
            side_effect=mock_failing_agent
        ):
            # First request should try and fail
            response1 = await overlord.chat(
                "Do the flaky task",
                user_id="test-user"
            )
            assert failure_count >= 1
            
            # Second request should also try and fail
            response2 = await overlord.chat(
                "Do the flaky task again",
                user_id="test-user"
            )
            assert failure_count >= 2
            
            # Third request should trigger circuit breaker (no more attempts)
            initial_count = failure_count
            response3 = await overlord.chat(
                "Do the flaky task one more time",
                user_id="test-user"
            )
            
            # Circuit breaker should prevent additional attempts
            assert failure_count == initial_count or failure_count == initial_count + 1
            
            # Should get circuit breaker message
            assert any(phrase in response3.content.lower() for phrase in [
                "technical difficulties",
                "external services",
                "fallback"
            ])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])