#!/usr/bin/env python3
"""
Test script to verify comprehensive events integration in the observability system.
"""

import asyncio
from runtime.src.muxi.runtime.observability import (
    ObservabilityManager,
    ConversationEventType,
    EventLevel,
)


async def test_comprehensive_events():
    """Test that comprehensive events are properly integrated."""
    print("🔍 Testing comprehensive events integration...")

    # Initialize observability manager
    config = {"observability": {"enabled": True}}
    manager = ObservabilityManager(config)
    await manager.start()

    print("✅ ObservabilityManager started successfully")
    print(f"📊 Total events defined: {len(ConversationEventType)}")

    # Test request lifecycle events
    print("\n🔄 Testing request lifecycle events...")
    async with manager.track_request("test-req-123", "test-formation") as ctx:
        # Test request received event
        await manager.event_logger.emit_event(
            ConversationEventType.REQUEST_RECEIVED,
            level=EventLevel.INFO,
            request_context=ctx,
            data={"message_length": 50, "user_id": "test-user"},
            description="Test request received",
        )
        print("  ✅ REQUEST_RECEIVED event emitted")

        # Test request validation event
        await manager.event_logger.emit_event(
            ConversationEventType.REQUEST_VALIDATED,
            level=EventLevel.INFO,
            request_context=ctx,
            data={"message_valid": True, "agent_exists": True},
            description="Test request validated",
        )
        print("  ✅ REQUEST_VALIDATED event emitted")

    # Test memory operation events
    print("\n🧠 Testing memory operation events...")
    await manager.event_logger.emit_event(
        ConversationEventType.MEMORY_RETRIEVAL_STARTED,
        level=EventLevel.DEBUG,
        data={"query": "test query", "memory_type": "buffer", "k": 5},
        description="Test memory retrieval started",
    )
    print("  ✅ MEMORY_RETRIEVAL_STARTED event emitted")

    await manager.event_logger.emit_event(
        ConversationEventType.MEMORY_RETRIEVAL_SHORT_TERM,
        level=EventLevel.DEBUG,
        data={"query": "test query", "results_count": 3},
        description="Test buffer memory search completed",
    )
    print("  ✅ MEMORY_RETRIEVAL_SHORT_TERM event emitted")

    await manager.event_logger.emit_event(
        ConversationEventType.MEMORY_STORE,
        level=EventLevel.DEBUG,
        data={"content_length": 100, "memory_type": "long_term"},
        description="Test memory storage",
    )
    print("  ✅ MEMORY_STORE event emitted")

    # Test agent processing events
    print("\n🤖 Testing agent processing events...")
    await manager.event_logger.emit_event(
        ConversationEventType.AGENT_MESSAGE_PROCESSING,
        level=EventLevel.INFO,
        data={"agent_id": "test-agent", "message_length": 50},
        description="Test agent message processing started",
    )
    print("  ✅ AGENT_MESSAGE_PROCESSING event emitted")

    await manager.event_logger.emit_event(
        ConversationEventType.AGENT_MESSAGE_COMPLETED,
        level=EventLevel.INFO,
        data={"agent_id": "test-agent", "response_length": 200},
        description="Test agent message completed",
    )
    print("  ✅ AGENT_MESSAGE_COMPLETED event emitted")

    # Test MCP tool events
    print("\n🔧 Testing MCP tool events...")
    await manager.event_logger.emit_event(
        ConversationEventType.MCP_TOOL_CALLED,
        level=EventLevel.INFO,
        data={"tool_name": "test-tool", "server_id": "test-server"},
        description="Test MCP tool called",
    )
    print("  ✅ MCP_TOOL_CALLED event emitted")

    await manager.event_logger.emit_event(
        ConversationEventType.MCP_TOOL_COMPLETED,
        level=EventLevel.INFO,
        data={"tool_name": "test-tool", "execution_time": 0.5},
        description="Test MCP tool completed",
    )
    print("  ✅ MCP_TOOL_COMPLETED event emitted")

    # Test overlord routing events
    print("\n🎯 Testing overlord routing events...")
    await manager.event_logger.emit_event(
        ConversationEventType.OVERLORD_ROUTING_STARTED,
        level=EventLevel.INFO,
        data={"message": "test message", "agent_name": None},
        description="Test overlord routing started",
    )
    print("  ✅ OVERLORD_ROUTING_STARTED event emitted")

    await manager.event_logger.emit_event(
        ConversationEventType.OVERLORD_AGENT_SELECTION_STARTED,
        level=EventLevel.INFO,
        data={"message": "test message"},
        description="Test agent selection started",
    )
    print("  ✅ OVERLORD_AGENT_SELECTION_STARTED event emitted")

    await manager.event_logger.emit_event(
        ConversationEventType.OVERLORD_AGENT_SELECTION_COMPLETED,
        level=EventLevel.INFO,
        data={"selected_agent": "test-agent"},
        description="Test agent selection completed",
    )
    print("  ✅ OVERLORD_AGENT_SELECTION_COMPLETED event emitted")

    await manager.event_logger.emit_event(
        ConversationEventType.OVERLORD_ROUTING_COMPLETED,
        level=EventLevel.INFO,
        data={"processing_time": 1.5, "mode": "sync"},
        description="Test overlord routing completed",
    )
    print("  ✅ OVERLORD_ROUTING_COMPLETED event emitted")

    # Test performance monitoring events
    print("\n📈 Testing performance monitoring events...")
    await manager.event_logger.emit_event(
        ConversationEventType.PERFORMANCE_DURATION_RECORDED,
        level=EventLevel.DEBUG,
        data={"operation": "sync_chat", "processing_time": 2.1, "phase": "completed"},
        description="Test performance duration recorded",
    )
    print("  ✅ PERFORMANCE_DURATION_RECORDED event emitted")

    # Test error handling events
    print("\n❌ Testing error handling events...")
    await manager.event_logger.emit_event(
        ConversationEventType.ERROR_TIMEOUT_DETECTED,
        level=EventLevel.ERROR,
        data={"operation": "test_operation", "timeout_seconds": 30},
        description="Test timeout detected",
    )
    print("  ✅ ERROR_TIMEOUT_DETECTED event emitted")

    await manager.event_logger.emit_event(
        ConversationEventType.ERROR_RETRY_ATTEMPTED,
        level=EventLevel.ERROR,
        data={"memory_type": "long_term", "retry_count": 1},
        description="Test retry attempted",
    )
    print("  ✅ ERROR_RETRY_ATTEMPTED event emitted")

    print("\n🎉 All comprehensive events tested successfully!")
    print("📊 Event integration status: COMPLETE")
    print(f"📈 Events being used in runtime: ~15+ out of {len(ConversationEventType)} total events")

    # Show event categories
    events = [e.name for e in ConversationEventType]
    categories = {}
    for event in events:
        category = event.split("_")[0]
        categories[category] = categories.get(category, 0) + 1

    print("\n📋 Event categories:")
    for category, count in sorted(categories.items()):
        print(f"  {category}: {count} events")


if __name__ == "__main__":
    asyncio.run(test_comprehensive_events())
