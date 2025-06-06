#!/usr/bin/env python3
"""
Task 1.12 Completion Test: External A2A Message Routing

This script validates that Task 1.12 (A2A Message Routing) is complete by testing:
1. Two formations registering with the same A2A registry
2. Cross-formation agent discovery
3. Direct HTTP communication between formations
4. Complete A2A collaboration workflow

Test Architecture:
- Formation A (port 8080): research-agent
- Formation B (port 8081): writer-agent
- A2A Registry (port 9090): Central discovery service
- Test: research-agent delegates writing task to writer-agent
"""

import asyncio
import logging
import os
import shutil
import signal
import sys
import time
import subprocess
from pathlib import Path
import yaml
from typing import Dict, Any, List

# Add the runtime directory to Python path
sys.path.insert(0, '../runtime')

from muxi.runtime.overlord import Overlord
from muxi.runtime.llm import LLM


class Task112CompletionTest:
    """Comprehensive test for Task 1.12 completion"""

    def __init__(self):
        self.formation_a_overlord = None
        self.formation_b_overlord = None
        self.registry_process = None
        self.test_results = {
            "registry_health": False,
            "formation_a_registration": False,
            "formation_b_registration": False,
            "cross_formation_discovery": False,
            "external_messaging": False,
            "collaboration_workflow": False
        }

    async def setup_test_environment(self):
        """Set up the complete test environment"""
        print("🚀 Task 1.12 Completion Test: External A2A Message Routing")
        print("=" * 70)

        # 1. Start A2A Registry Server
        print("\n📡 Step 1: Starting A2A Registry Server...")
        await self.start_registry_server()

        # 2. Load formation configurations
        print("\n📋 Step 2: Loading formation configurations...")
        formation_a_config = self.load_formation_config("formation-a.yaml")
        formation_b_config = self.load_formation_config("formation-b.yaml")

        # 3. Create overlords for both formations
        print("\n🏗️  Step 3: Creating formation overlords...")

        # Create models (using dummy API key for testing)
        model_a = LLM(
            model="gpt-4o-mini",
            api_key="test-key-not-used",
            temperature=0.7
        )
        model_b = LLM(
            model="gpt-4o-mini",
            api_key="test-key-not-used",
            temperature=0.7
        )

        # Formation A
        self.formation_a_overlord = Overlord(
            formation_config=formation_a_config,
            request_timeout=30
        )
        await self.formation_a_overlord.initialize_external_registry_async()

        # Formation B
        self.formation_b_overlord = Overlord(
            formation_config=formation_b_config,
            request_timeout=30
        )
        await self.formation_b_overlord.initialize_external_registry_async()

        # 4. Create agents
        print("\n👥 Step 4: Creating specialized agents...")
        research_agent = self.formation_a_overlord.create_agent(
            agent_id="research-agent",
            model=model_a,
            system_message=formation_a_config['agents'][0]['system_message'],
            description=formation_a_config['agents'][0]['description'],
            a2a_external=True
        )
        writer_agent = self.formation_b_overlord.create_agent(
            agent_id="writer-agent",
            model=model_b,
            system_message=formation_b_config['agents'][0]['system_message'],
            description=formation_b_config['agents'][0]['description'],
            a2a_external=True
        )

        print(f"   ✅ Created {research_agent.agent_id} in Formation A")
        print(f"   ✅ Created {writer_agent.agent_id} in Formation B")

        print("\n🚀 Step 5: Starting Formation HTTP Servers...")
        # Start the formation servers to listen for incoming A2A messages
        await self.formation_a_overlord.start_formation_server()
        await self.formation_b_overlord.start_formation_server()
        print("   ✅ Formation A server started on port 8080")
        print("   ✅ Formation B server started on port 8081")

        # Give servers a moment to fully start
        await asyncio.sleep(1)

    async def start_registry_server(self):
        """Start the A2A registry server"""
        try:
            # Start the registry server as a subprocess
            registry_script = "../runtime/muxi/runtime/utils/a2a_registry.py"
            self.registry_process = subprocess.Popen([
                sys.executable, registry_script
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Give it time to start
            await asyncio.sleep(3)

            print("   ✅ A2A Registry server started on localhost:9090")

        except Exception as e:
            print(f"   ❌ Failed to start registry server: {e}")
            raise

    def load_formation_config(self, config_file: str) -> dict:
        """Load formation configuration from YAML file"""
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
                print(f"   ✅ Loaded {config['name']}")
                return config
        except Exception as e:
            print(f"   ❌ Failed to load {config_file}: {e}")
            raise

    async def test_registry_health(self):
        """Test 1: Registry Health Check"""
        print("\n🏥 Test 1: Registry Health Check...")

        try:
            # Test both overlords can reach the registry
            health_a = await self.formation_a_overlord.external_registry_client.health_check_all()
            health_b = await self.formation_b_overlord.external_registry_client.health_check_all()

            if health_a and health_b:
                print("   ✅ Both formations can reach the registry")
                self.test_results["registry_health"] = True
            else:
                print("   ❌ Registry health check failed")

        except Exception as e:
            print(f"   ❌ Registry health check error: {e}")

    async def test_agent_registration(self):
        """Test 2: Agent Registration with External Registry"""
        print("\n📝 Test 2: Agent Registration...")

        try:
            # Agents are already automatically registered during creation
            # Let's just verify they are registered by checking if they can be discovered

            # Wait a moment for async registration to complete
            await asyncio.sleep(2)

            # Check if research-agent is registered by trying to discover it
            discovered_a = await self.formation_a_overlord.external_registry_client.discover_agents()
            research_agent_found = False
            if isinstance(discovered_a, dict):
                for registry_url, agents in discovered_a.items():
                    for agent_card in agents:
                        if ((hasattr(agent_card, 'name') and
                             agent_card.name == "research-agent") or
                            (hasattr(agent_card, 'muxi_agent_id') and
                             agent_card.muxi_agent_id == "research-agent")):
                            research_agent_found = True
                            break

            if research_agent_found:
                print("   ✅ Formation A: research-agent registered")
                self.test_results["formation_a_registration"] = True
            else:
                print("   ❌ Formation A: research-agent not found in registry")

            # Check if writer-agent is registered
            discovered_b = await self.formation_b_overlord.external_registry_client.discover_agents()
            writer_agent_found = False
            if isinstance(discovered_b, dict):
                for registry_url, agents in discovered_b.items():
                    for agent_card in agents:
                        if ((hasattr(agent_card, 'name') and
                             agent_card.name == "writer-agent") or
                            (hasattr(agent_card, 'muxi_agent_id') and
                             agent_card.muxi_agent_id == "writer-agent")):
                            writer_agent_found = True
                            break

            if writer_agent_found:
                print("   ✅ Formation B: writer-agent registered")
                self.test_results["formation_b_registration"] = True
            else:
                print("   ❌ Formation B: writer-agent not found in registry")

        except Exception as e:
            print(f"   ❌ Agent registration error: {e}")

    async def test_cross_formation_discovery(self):
        """Test 3: Cross-Formation Agent Discovery"""
        print("\n🔍 Test 3: Cross-Formation Discovery...")

        try:
            # Formation A discovers Formation B's agents
            discovered_agents = await self.formation_a_overlord.external_registry_client.discover_agents()

            writer_agent_found = False
            if isinstance(discovered_agents, dict):
                for registry_url, agents in discovered_agents.items():
                    for agent_card in agents:
                        if ((hasattr(agent_card, 'name') and
                             agent_card.name == "writer-agent") or
                            (hasattr(agent_card, 'muxi_agent_id') and
                             agent_card.muxi_agent_id == "writer-agent")):
                            writer_agent_found = True
                            print(f"   ✅ Formation A discovered writer-agent at "
                                  f"{agent_card.url}")
                            break

            if writer_agent_found:
                self.test_results["cross_formation_discovery"] = True
            else:
                print("   ❌ Formation A could not discover writer-agent")

        except Exception as e:
            print(f"   ❌ Cross-formation discovery error: {e}")

    async def test_external_messaging(self):
        """Test 4: External A2A Messaging"""
        print("\n💬 Test 4: External A2A Messaging...")

        try:
            # Get research agent from Formation A
            research_agent = self.formation_a_overlord.get_agent("research-agent")

            # Send A2A message to writer-agent in Formation B
            test_message = "Hello writer-agent! This is a test message from research-agent via external A2A."

            response = await research_agent.send_a2a_message(
                target_agent_id="writer-agent",
                message=test_message,
                message_type="request",
                context={"collaboration_type": "consultation", "topic": "cross-formation-test"},
                wait_for_response=True,
                timeout=15
            )

            if response and response.get("status") == "success":
                print("   ✅ External A2A message successful!")
                print(f"   📧 Response: {response.get('response', 'No response content')[:100]}...")
                self.test_results["external_messaging"] = True
            else:
                print(f"   ❌ External A2A message failed: {response}")

        except Exception as e:
            print(f"   ❌ External messaging error: {e}")

    async def test_collaboration_workflow(self):
        """Test 5: Complete Collaboration Workflow"""
        print("\n🤝 Test 5: Complete Collaboration Workflow...")

        try:
            # Research agent delegates a writing task to writer agent
            research_agent = self.formation_a_overlord.get_agent("research-agent")

            research_data = """
            Research Summary: Artificial Intelligence Trends 2024
            - Machine Learning adoption has increased 40% year-over-year
            - Large Language Models are being integrated into 60% of new applications
            - AI ethics and safety concerns are driving new regulatory frameworks
            - Edge AI deployment has grown 25% for latency-sensitive applications
            """

            collaboration_request = f"""
            I have completed research on AI trends for 2024. Could you help me write a professional
            executive summary based on this data? Here's the research:

            {research_data}

            Please create a concise, executive-level summary suitable for a business presentation.
            """

            response = await research_agent.send_a2a_message(
                target_agent_id="writer-agent",
                message=collaboration_request,
                message_type="request",
                context={
                    "collaboration_type": "consultation",
                    "topic": "AI trends executive summary",
                    "urgency": "normal"
                },
                wait_for_response=True,
                timeout=20
            )

            if response and response.get("status") == "success":
                executive_summary = response.get("response", "")

                print("   ✅ Collaboration workflow successful!")
                print("   📝 Executive Summary Created:")
                print(f"   {executive_summary[:200]}...")

                # Validate the response contains expected elements
                if ("AI" in executive_summary and
                    ("summary" in executive_summary.lower() or "trends" in executive_summary.lower())):
                    self.test_results["collaboration_workflow"] = True
                    print("   ✅ Response quality validation passed")
                else:
                    print("   ⚠️  Response quality validation questionable")
            else:
                print(f"   ❌ Collaboration workflow failed: {response}")

        except Exception as e:
            print(f"   ❌ Collaboration workflow error: {e}")

    def print_test_results(self):
        """Print final test results"""
        print("\n" + "=" * 70)
        print("🎯 TASK 1.12 COMPLETION TEST RESULTS")
        print("=" * 70)

        passed = sum(self.test_results.values())
        total = len(self.test_results)

        for test_name, result in self.test_results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            test_display = test_name.replace("_", " ").title()
            print(f"   {status}: {test_display}")

        print(f"\n📊 Overall Results: {passed}/{total} tests passed")

        if passed == total:
            print("\n🎉 TASK 1.12 COMPLETION: ✅ SUCCESS!")
            print("   External A2A Message Routing is fully implemented and working!")
        else:
            print(f"\n⚠️  TASK 1.12 COMPLETION: ❌ {total - passed} issues remaining")

        return passed == total

    async def cleanup(self):
        """Clean up test environment"""
        print("\n🧹 Cleaning up test environment...")

        try:
            # Deregister agents (use correct URL format without /agents/)
            if self.formation_a_overlord and self.formation_a_overlord.external_registry_client:
                await self.formation_a_overlord.external_registry_client.deregister_agent(
                    "http://localhost:8080/research-agent"
                )

            if self.formation_b_overlord and self.formation_b_overlord.external_registry_client:
                await self.formation_b_overlord.external_registry_client.deregister_agent(
                    "http://localhost:8081/writer-agent"
                )

            # Stop registry server
            if self.registry_process:
                self.registry_process.terminate()
                self.registry_process.wait(timeout=5)

            print("   ✅ Cleanup completed")

        except Exception as e:
            print(f"   ⚠️  Cleanup warning: {e}")

    async def run_complete_test(self):
        """Run the complete Task 1.12 test suite"""
        try:
            await self.setup_test_environment()
            await self.test_registry_health()
            await self.test_agent_registration()
            await self.test_cross_formation_discovery()
            await self.test_external_messaging()
            await self.test_collaboration_workflow()

            success = self.print_test_results()
            return success

        except KeyboardInterrupt:
            print("\n🛑 Test interrupted by user")
            return False
        except Exception as e:
            print(f"\n💥 Test failed with error: {e}")
            return False
        finally:
            await self.cleanup()


async def setup_clean_registry():
    """Setup a clean registry environment by clearing persistent data"""
    try:
        # Clear registry data directory for clean start
        registry_data_dir = Path(".registry_data")
        if registry_data_dir.exists():
            shutil.rmtree(registry_data_dir)
            print("   🧹 Cleared old registry data")

        # Kill any existing registry processes
        subprocess.run(["pkill", "-f", "a2a_registry.py"], capture_output=True)
        await asyncio.sleep(2)
        print("   🔄 Killed existing registry processes")

    except Exception as e:
        print(f"   ⚠️  Registry cleanup warning: {e}")


async def start_a2a_registry() -> bool:
    """Start the A2A registry server"""
    try:
        # Start the registry server as a subprocess
        registry_script = "../runtime/muxi/runtime/utils/a2a_registry.py"
        _ = subprocess.Popen([
            sys.executable, registry_script
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Give it time to start
        await asyncio.sleep(3)

        print("   ✅ A2A Registry server started on localhost:9090")
        return True

    except Exception as e:
        print(f"   ❌ Failed to start registry server: {e}")
        return False


async def main():
    """Main test function"""
    print("🚀 Task 1.12 Completion Test: External A2A Message Routing")
    print("=" * 70)

    # Step 1: Setup clean registry environment
    print("\n🧹 Step 1: Setting up clean registry environment...")
    await setup_clean_registry()

    # Step 2: Start A2A Registry Server
    print("\n📡 Step 2: Starting A2A Registry Server...")
    if not await start_a2a_registry():
        print("❌ Failed to start A2A registry server")
        return False

    test = Task112CompletionTest()
    success = await test.run_complete_test()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
