"""Unit tests for the ResilientWorkflowExecutor tool-timeout fallback path.

The fallback in ``_apply_recovery_strategy`` retries a NETWORK_TIMEOUT task
without tools by calling ``Agent.process_message`` directly. That call must
match the real ``process_message`` signature -- passing keyword arguments the
agent does not accept raises a TypeError which the surrounding
``except Exception`` silently swallows, so the fallback returns None instead
of a degraded-but-successful TaskResult.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from muxi.runtime.datatypes.resilience import ErrorSeverity, ErrorType
from muxi.runtime.datatypes.workflow import SubTask, TaskResult, TaskStatus
from muxi.runtime.formation.workflow.resilient_executor import ResilientWorkflowExecutor

# ===================================================================
# Helpers
# ===================================================================


class FakeResponse:
    def __init__(self, content: str):
        self.content = content


class FakeAgent:
    """Agent double whose process_message mirrors the real Agent signature.

    Deliberately no ``**kwargs`` catch-all: the real
    ``Agent.process_message`` does not accept arbitrary keywords, so an
    unexpected keyword argument from the executor must surface here too.
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.id = agent_id
        self.name = agent_id
        self.calls: List[Dict[str, Any]] = []

    async def process_message(
        self,
        message,
        user_id: Any = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        is_a2a_task: bool = False,
        clean_chat_context: Optional[Dict[str, Any]] = None,
        model_override: Optional[Any] = None,
    ) -> FakeResponse:
        self.calls.append({"message": message, "user_id": user_id, "session_id": session_id})
        return FakeResponse(f"{self.agent_id} answered without tools")


def make_task(task_id: str = "task_1") -> SubTask:
    return SubTask(
        id=task_id,
        description="fetch data from the external api",
        required_capabilities=["research"],
    )


def make_error_info(retry_count: int = 1) -> Dict[str, Any]:
    return {
        "type": ErrorType.NETWORK_TIMEOUT,
        "severity": ErrorSeverity.MEDIUM,
        "message": "I encountered an issue while fetch data from the external api.",
        "details": "Tool timeout while fetch data from the external api",
        "retry_count": retry_count,
    }


# ===================================================================
# Tests
# ===================================================================


async def test_tool_timeout_fallback_returns_task_result():
    """After a retried tool timeout, the no-tools fallback must succeed."""
    agent = FakeAgent("agent_1")
    executor = ResilientWorkflowExecutor(agent_registry={"agent_1": agent})
    task = make_task()

    result = await executor._apply_recovery_strategy(
        task=task,
        agent=agent,
        context={"user_id": 42, "session_id": "sess_1"},
        error_info=make_error_info(retry_count=1),
        recovery_strategy=None,
    )

    assert isinstance(result, TaskResult)
    assert result.task_id == task.id
    assert result.status == TaskStatus.DONE.value
    fallback = result.outputs["response"]["result"]
    assert fallback["fallback_used"] is True
    assert fallback["content"] == "agent_1 answered without tools"
    assert fallback["retry_count"] == 1


async def test_tool_timeout_fallback_call_matches_agent_signature():
    """The fallback call threads user/session through and reaches the agent."""
    agent = FakeAgent("agent_1")
    executor = ResilientWorkflowExecutor(agent_registry={"agent_1": agent})

    result = await executor._apply_recovery_strategy(
        task=make_task(),
        agent=agent,
        context={"user_id": 42, "session_id": "sess_1"},
        error_info=make_error_info(retry_count=2),
        recovery_strategy=None,
    )

    assert result is not None
    assert len(agent.calls) == 1
    call = agent.calls[0]
    assert "External tools are unavailable" in call["message"]
    assert call["user_id"] == 42
    assert call["session_id"] == "sess_1"


async def test_no_fallback_before_first_retry():
    """With retry_count == 0 the executor defers to normal retry logic."""
    agent = FakeAgent("agent_1")
    executor = ResilientWorkflowExecutor(agent_registry={"agent_1": agent})

    result = await executor._apply_recovery_strategy(
        task=make_task(),
        agent=agent,
        context={"user_id": 42, "session_id": "sess_1"},
        error_info=make_error_info(retry_count=0),
        recovery_strategy=None,
    )

    assert result is None
    assert agent.calls == []
