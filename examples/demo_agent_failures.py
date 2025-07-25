#!/usr/bin/env python3
"""
Demo: Agent Failure Scenarios

This script demonstrates various ways agents can become unavailable during runtime
and how the discovery service detects and handles these scenarios.
"""

import asyncio
from unittest.mock import MagicMock
from src.muxi.a2a.discovery import LocalDiscoveryService, DiscoveryConfig
from src.muxi.a2a.models import AgentCard, A2ACapability


class MockFailingHTTPClient:
    """Mock HTTP client that simulates various failure scenarios"""

    def __init__(self):
        self.failure_mode = "healthy"
        self.call_count = 0

    def set_failure_mode(self, mode: str):
        """Set the type of failure to simulate"""
        self.failure_mode = mode
        self.call_count = 0

    async def get(self, url: str):
        """Mock HTTP GET with various failure modes"""
        self.call_count += 1

        if self.failure_mode == "healthy":
            # Normal successful response
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {
                "name": "Test Agent",
                "description": "A test agent",
                "capabilities": {"test": {"name": "test", "enabled": True}},
                "version": "1.0.0",
                "url": "http://localhost:8081"
            }
            response.raise_for_status = MagicMock()
            return response

        elif self.failure_mode == "slow_response":
            # Simulate slow response (impacts health score)
            await asyncio.sleep(1.5)  # 1.5 second delay
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {
                "name": "Slow Agent",
                "description": "A slow responding agent",
                "capabilities": {"test": {"name": "test", "enabled": True}},
                "version": "1.0.0",
                "url": "http://localhost:8081"
            }
            response.raise_for_status = MagicMock()
            return response

        elif self.failure_mode == "http_error":
            # Simulate HTTP error (503 Service Unavailable)
            response = MagicMock()
            response.status_code = 503
            response.json.return_value = {"error": "Service temporarily unavailable"}
            response.raise_for_status = MagicMock()
            return response

        elif self.failure_mode == "network_timeout":
            # Simulate network timeout
            raise asyncio.TimeoutError("Connection timed out")

        elif self.failure_mode == "connection_refused":
            # Simulate connection refused (agent process down)
            raise ConnectionError("Connection refused")

        elif self.failure_mode == "intermittent":
            # Simulate intermittent failures (fails every other call)
            if self.call_count % 2 == 0:
                raise ConnectionError("Intermittent failure")
            else:
                response = MagicMock()
                response.status_code = 200
                response.json.return_value = {
                    "name": "Flaky Agent",
                    "description": "An intermittently failing agent",
                    "capabilities": {"test": {"name": "test", "enabled": True}},
                    "version": "1.0.0",
                    "url": "http://localhost:8081"
                }
                response.raise_for_status = MagicMock()
                return response

        elif self.failure_mode == "gradual_degradation":
            # Simulate gradual performance degradation
            delay = min(self.call_count * 0.3, 3.0)  # Increase delay with each call
            await asyncio.sleep(delay)
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {
                "name": "Degrading Agent",
                "description": "An agent with degrading performance",
                "capabilities": {"test": {"name": "test", "enabled": True}},
                "version": "1.0.0",
                "url": "http://localhost:8081"
            }
            response.raise_for_status = MagicMock()
            return response

    async def aclose(self):
        """Mock close method"""
        pass


async def demo_failure_scenario(scenario_name: str, failure_mode: str, description: str):
    """Demonstrate a specific failure scenario"""
    print(f"\n{'='*60}")
    print(f"SCENARIO: {scenario_name}")
    print(f"{'='*60}")
    print(f"Description: {description}")
    print()

    # Create discovery service with fast health checks for demo
    config = DiscoveryConfig(
        health_check_interval=2,  # Check every 2 seconds
        agent_timeout=10,         # Mark unreachable after 10 seconds
        enable_persistence=False
    )

    discovery = LocalDiscoveryService(config)
    mock_client = MockFailingHTTPClient()
    discovery.http_client = mock_client

    await discovery.start("demo_formation", 8080)

    try:
        # Create and register test agent
        test_card = AgentCard(
            name="Demo Agent",
            description=f"Agent for {scenario_name} demo",
            version="1.0.0",
            url="http://localhost:8081"
        )
        test_card.add_capability(A2ACapability(name="demo", enabled=True))

        # Start with healthy agent
        mock_client.set_failure_mode("healthy")
        await discovery.register_agent("demo_agent", "http://localhost:8081", test_card)

        print("✓ Agent registered successfully")

        # Show initial healthy status
        agent_info = discovery.get_agent_info("demo_agent")
        print(f"Initial status: {agent_info['status']}, health: {agent_info['health_score']}")

        # Switch to failure mode
        print(f"\n🔥 Switching to failure mode: {failure_mode}")
        mock_client.set_failure_mode(failure_mode)

        # Monitor status changes over several health checks
        for i in range(5):
            await asyncio.sleep(2.5)  # Wait a bit longer than health check interval

            agent_info = discovery.get_agent_info("demo_agent")
            if agent_info:
                print(f"Check {i+1}: Status={agent_info['status']}, "
                      f"Health={agent_info['health_score']:.1f}, "
                      f"Response time={agent_info.get('response_time_ms', 'N/A')}")
            else:
                print(f"Check {i+1}: Agent not found")

        # Show discovery results
        print("\nDiscovery Results:")
        active_agents = discovery.discover_agents(status_filter=["active"])
        inactive_agents = discovery.discover_agents(status_filter=["inactive"])
        unreachable_agents = discovery.discover_agents(status_filter=["unreachable"])

        print(f"  Active agents: {len(active_agents)}")
        print(f"  Inactive agents: {len(inactive_agents)}")
        print(f"  Unreachable agents: {len(unreachable_agents)}")

        # Formation status
        formation_status = discovery.get_formation_status()
        print(f"\nFormation Health Score: {formation_status['avg_health_score']}")

    finally:
        await discovery.stop()


async def main():
    """Run all failure scenario demonstrations"""
    print("AGENT FAILURE SCENARIOS DEMONSTRATION")
    print("=" * 60)
    print("This demo shows how agents become unavailable and how discovery handles it")

    scenarios = [
        ("Slow Response", "slow_response",
         "Agent responds but very slowly (>1.5s), affecting health score"),

        ("HTTP Errors", "http_error",
         "Agent returns HTTP 503 errors (overloaded/maintenance)"),

        ("Network Timeout", "network_timeout",
         "Agent doesn't respond within timeout (network issues)"),

        ("Process Crash", "connection_refused",
         "Agent process is down (connection refused)"),

        ("Intermittent Failures", "intermittent",
         "Agent fails every other request (network instability)"),

        ("Gradual Degradation", "gradual_degradation",
         "Agent performance degrades over time (resource exhaustion)")
    ]

    for scenario_name, failure_mode, description in scenarios:
        await demo_failure_scenario(scenario_name, failure_mode, description)
        print("\nPress Enter to continue to next scenario...")
        input()

    print("\n" + "=" * 60)
    print("🎉 All failure scenarios demonstrated!")
    print("\nKey Takeaways:")
    print("- Agents can fail in many different ways during runtime")
    print("- Discovery service continuously monitors and adapts")
    print("- Health scores help with intelligent routing decisions")
    print("- Status tracking enables graceful degradation")


if __name__ == "__main__":
    asyncio.run(main())
