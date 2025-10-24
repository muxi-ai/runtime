#!/usr/bin/env python3
"""Test 19f1: Agents CRUD endpoints."""

import asyncio
import time
from pathlib import Path
import sys
import httpx

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter, TestTimeouts  # noqa: E402


class TestAgentsCRUD(BaseE2ETest):
    """Test agents CRUD endpoints."""

    def __init__(self):
        super().__init__(
            test_name="test_19f1_agents_crud",
            test_description="Test agents CRUD operations",
            test_area="19_api",
        )
        self.base_url = "http://127.0.0.1:8271/v1"
        self.admin_key = "test-admin-key-123"
        self.headers = {
            "X-Muxi-Admin-Key": self.admin_key,
            "Content-Type": "application/json",
        }

    async def test_19f1_agents_crud(self):
        """Test agents CRUD endpoints."""
        formatter = TestOutputFormatter()
        start_time = time.time()
        success = False

        # Print header
        formatter.print_test_header(
            test_name="test_19f1_agents_crud",
            description="Test agents CRUD operations",
        )

        try:
            # Setup formation
            print("\n1. Setting up formation with API server...")
            await self.setup_formation(
                formation_path=Path(__file__).parent / "formation-api",
            )
            
            # Start the API server
            await self.formation.start_server(block=False)
            
            # Wait for server to be ready
            import asyncio
            await asyncio.sleep(2)
            print("✅ Formation ready with API server")

            # Test 1: List agents (GET /v1/agents)
            print("\n2. Testing GET /v1/agents...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/agents",
                    headers=self.headers,
                )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            data = response.json()
            
            # Verify response structure (API uses generic "list" type with use_generic_type=True)
            assert data["object"] == "list", f"Wrong object type: {data['object']}"
            assert data["type"] == "agent.list", f"Wrong event type: {data['type']}"  # Note: singular not plural
            assert data["success"] is True
            assert "agents" in data["data"]
            assert "count" in data["data"]
            
            initial_agent_count = data["data"]["count"]
            initial_agents = data["data"]["agents"]
            print(f"   Initial agent count: {initial_agent_count}")
            print("✅ GET /v1/agents passed")

            # Test 2: Get specific agent (GET /v1/agents/{agent_id})
            print("\n3. Testing GET /v1/agents/{agent_id}...")
            if initial_agent_count > 0:
                first_agent_id = initial_agents[0]["id"]
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(
                        f"{self.base_url}/agents/{first_agent_id}",
                        headers=self.headers,
                    )
                
                assert response.status_code == 200
                data = response.json()
                assert data["object"] == "agent"
                assert data["type"] == "agent.retrieved"
                assert data["data"]["id"] == first_agent_id
                
                print(f"   Agent ID: {data['data']['id']}")
                print(f"   Agent name: {data['data']['name']}")
                print("✅ GET /v1/agents/{agent_id} passed")
            else:
                print("   ⚠️  No agents to test individual retrieval")

            # Test 3: Create agent (POST /v1/agents)
            print("\n4. Testing POST /v1/agents...")
            
            # Cleanup: Delete test agent if it exists from previous run
            async with httpx.AsyncClient(timeout=30.0) as client:
                cleanup_response = await client.delete(
                    f"{self.base_url}/agents/test_agent_e2e",
                    headers=self.headers,
                )
            if cleanup_response.status_code == 200:
                print("   Cleaned up existing test agent from previous run")
            
            new_agent = {
                "schema": "1.0.0",  # Required field - agent schema version
                "id": "test_agent_e2e",
                "name": "Test Agent E2E",
                "description": "Agent created by e2e test",
                "system_message": "You are a test agent. Be concise.",
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/agents",
                    headers=self.headers,
                    json=new_agent,
                )
            
            if response.status_code != 201:
                print(f"   ERROR: Got status {response.status_code}")
                print(f"   Response: {response.text}")
            assert response.status_code == 201, f"Expected 201 (created), got {response.status_code}"
            data = response.json()
            assert data["object"] == "agent"
            assert data["type"] == "agent.created"
            assert data["data"]["id"] == "test_agent_e2e"
            assert data["data"]["name"] == "Test Agent E2E"
            
            print(f"   Created agent: {data['data']['name']}")
            print("✅ POST /v1/agents passed")

            # Test 4: Verify agent was created (list again)
            print("\n5. Verifying agent was created...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/agents",
                    headers=self.headers,
                )
            
            assert response.status_code == 200
            data = response.json()
            new_agent_count = data["data"]["count"]
            assert new_agent_count == initial_agent_count + 1, "Agent count should increase by 1"
            
            # Find our agent in the list
            agent_ids = [a["id"] for a in data["data"]["agents"]]
            assert "test_agent_e2e" in agent_ids, "New agent should be in list"
            print("✅ Agent creation verified")

            # Test 5: Update agent (PATCH /v1/agents/{agent_id})
            print("\n6. Testing PATCH /v1/agents/{agent_id}...")
            
            update_data = {
                "name": "Updated Test Agent",
                "description": "Updated description",
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.patch(
                    f"{self.base_url}/agents/test_agent_e2e",
                    headers=self.headers,
                    json=update_data,
                )
            
            assert response.status_code == 200
            data = response.json()
            assert data["object"] == "agent"
            assert data["type"] == "agent.updated"
            assert data["data"]["name"] == "Updated Test Agent"
            assert data["data"]["description"] == "Updated description"
            
            print(f"   Updated name: {data['data']['name']}")
            print("✅ PATCH /v1/agents/{agent_id} passed")

            # Test 6: Delete agent (DELETE /v1/agents/{agent_id})
            print("\n7. Testing DELETE /v1/agents/{agent_id}...")
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"{self.base_url}/agents/test_agent_e2e",
                    headers=self.headers,
                )
            
            if response.status_code != 200:
                print(f"   ERROR: DELETE returned {response.status_code}")
                print(f"   Response: {response.text}")
            assert response.status_code == 200
            data = response.json()
            assert data["object"] == "agent"
            assert data["type"] == "agent.deleted"
            assert data["data"]["id"] == "test_agent_e2e"
            
            print(f"   Deleted agent: {data['data']['id']}")
            print("✅ DELETE /v1/agents/{agent_id} passed")

            # Test 7: Verify agent was deleted
            print("\n8. Verifying agent was deleted...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/agents",
                    headers=self.headers,
                )
            
            assert response.status_code == 200
            data = response.json()
            final_agent_count = data["data"]["count"]
            assert final_agent_count == initial_agent_count, "Agent count should return to initial"
            
            # Verify agent is not in list
            agent_ids = [a["id"] for a in data["data"]["agents"]]
            assert "test_agent_e2e" not in agent_ids, "Deleted agent should not be in list"
            print("✅ Agent deletion verified")

            # Test 8: Get non-existent agent (should 404)
            print("\n9. Testing GET /v1/agents/{non_existent}...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/agents/non_existent_agent",
                    headers=self.headers,
                )
            
            assert response.status_code == 404, f"Expected 404, got {response.status_code}"
            data = response.json()
            assert data["success"] is False
            assert data["error"]["code"] == "RESOURCE_NOT_FOUND"
            print("✅ 404 for non-existent agent")

            # Test 9: Authentication (without admin key)
            print("\n10. Testing authentication requirement...")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/agents",
                    headers={"Content-Type": "application/json"},
                )
            
            assert response.status_code == 401
            print("✅ Authentication enforced")

            # Success!
            success = True
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19f1_agents_crud",
                success=True,
                checks=[
                    f"GET /v1/agents passed ({initial_agent_count} agents)",
                    "GET /v1/agents/{agent_id} passed" if initial_agent_count > 0 else "No agents to test individual retrieval",
                    "POST /v1/agents passed (created test_agent_e2e)",
                    "Agent creation verified in list",
                    "PATCH /v1/agents/{agent_id} passed (updated name and description)",
                    "DELETE /v1/agents/{agent_id} passed",
                    "Agent deletion verified",
                    "404 for non-existent agent",
                    "Authentication enforced",
                ],
                transcript=[],
                duration=elapsed_time,
            )

        except Exception as e:
            elapsed_time = time.time() - start_time
            formatter.print_test_result(
                test_name="test_19f1_agents_crud",
                success=False,
                checks=[f"Failed: {str(e)}"],
                transcript=[],
                duration=elapsed_time,
            )
            import traceback
            traceback.print_exc()
            raise
        finally:
            # Cleanup
            if self.formation:
                await self.cleanup_formation()


async def main():
    """Run the test."""
    test = TestAgentsCRUD()
    await test.test_19f1_agents_crud()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
