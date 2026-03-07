#!/usr/bin/env python3
"""Test 21a5: Skills API Endpoints - verify REST API returns correct skill data."""

import asyncio
import time
from pathlib import Path
import sys
import httpx

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from common import BaseE2ETest, TestOutputFormatter  # noqa: E402


class TestSkillsAPIEndpoints(BaseE2ETest):
    def __init__(self):
        super().__init__(
            test_name="test_21a5_skills_api_endpoints",
            test_description="Verify REST API endpoints return correct skill data",
            test_area="21_skills",
        )

    async def test_skills_api_endpoints(self):
        formatter = TestOutputFormatter()
        start_time = time.time()
        checks = []

        formatter.print_test_header(
            test_name=self.test_name,
            description=self.test_description,
        )

        try:
            print("\n1. Loading formation as server...")
            formation_path = Path(__file__).parent / "formations" / "formation-skills"

            from muxi.runtime.formation import Formation
            formation = Formation()
            await formation.load(str(formation_path))

            # Start the formation server
            server = await formation.start_server(
                host="127.0.0.1",
                port=0,  # Random port
                block=False,
            )

            # Get the actual port
            port = server._server.servers[0].sockets[0].getsockname()[1] if hasattr(server, '_server') else 8271

            # Read client key
            key_path = formation_path / ".key"
            client_key = key_path.read_text().strip().split("\n")[-1]  # Last line is client key

            base_url = f"http://127.0.0.1:{port}/v1"
            headers = {"X-MUXI-CLIENT-KEY": client_key}

            async with httpx.AsyncClient() as client:
                # 2. GET /skills
                print("\n2. Testing GET /v1/skills...")
                resp = await client.get(f"{base_url}/skills", headers=headers)
                assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
                data = resp.json()
                assert data["success"] is True
                skills = data["data"]["skills"]
                assert len(skills) == 3, f"Expected 3 skills, got {len(skills)}"
                skill_names = [s["name"] for s in skills]
                assert "pdf-processing" in skill_names
                assert "data-analysis" in skill_names
                assert "ticket-handling" in skill_names
                print(f"   Listed {len(skills)} skills: {skill_names}")
                checks.append("GET /skills returns all 3 skills")

                # Check scopes
                pdf_skill = next(s for s in skills if s["name"] == "pdf-processing")
                assert pdf_skill["scope"] == "public"
                assert pdf_skill["has_scripts"] is True
                ticket_skill = next(s for s in skills if s["name"] == "ticket-handling")
                assert ticket_skill["scope"] == "private"
                checks.append("Skill scopes correct (public/private)")

                # 3. GET /skills/{name}
                print("\n3. Testing GET /v1/skills/pdf-processing...")
                resp = await client.get(f"{base_url}/skills/pdf-processing", headers=headers)
                assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
                data = resp.json()
                skill_data = data["data"]
                assert skill_data["name"] == "pdf-processing"
                assert "PDF" in skill_data["description"] or "pdf" in skill_data["description"].lower()
                assert skill_data["license"] == "MIT"
                assert "scripts/extract.py" in skill_data["resources"]
                assert "references/pdf-spec.md" in skill_data["resources"]
                print(f"   Skill: {skill_data['name']}, resources: {skill_data['resources']}")
                checks.append("GET /skills/{name} returns metadata and resources")

                # 4. GET /skills/{name} - 404
                print("\n4. Testing GET /v1/skills/nonexistent...")
                resp = await client.get(f"{base_url}/skills/nonexistent", headers=headers)
                assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
                print("   Got 404 for nonexistent skill")
                checks.append("GET /skills/{name} returns 404 for unknown skill")

                # 5. GET /agents/{id}/skills
                print("\n5. Testing GET /v1/agents/general-agent/skills...")
                resp = await client.get(f"{base_url}/agents/general-agent/skills", headers=headers)
                assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
                data = resp.json()
                agent_skills = data["data"]["skills"]
                agent_skill_names = [s["name"] for s in agent_skills]
                assert "pdf-processing" in agent_skill_names, "general-agent should have pdf-processing"
                assert "data-analysis" in agent_skill_names, "general-agent should have data-analysis"
                assert "ticket-handling" not in agent_skill_names, \
                    "general-agent should NOT have ticket-handling"
                print(f"   general-agent skills: {agent_skill_names}")
                checks.append("GET /agents/general-agent/skills returns public skills only")

                # 6. GET /agents/{id}/skills - support-agent
                print("\n6. Testing GET /v1/agents/support-agent/skills...")
                resp = await client.get(f"{base_url}/agents/support-agent/skills", headers=headers)
                assert resp.status_code == 200
                data = resp.json()
                agent_skills = data["data"]["skills"]
                agent_skill_names = [s["name"] for s in agent_skills]
                assert "pdf-processing" in agent_skill_names
                assert "data-analysis" in agent_skill_names
                assert "ticket-handling" in agent_skill_names, \
                    "support-agent should have ticket-handling"
                print(f"   support-agent skills: {agent_skill_names}")
                checks.append("GET /agents/support-agent/skills returns public + private skills")

            # Clean up
            print("\n7. Cleaning up...")
            await formation.shutdown()
            checks.append("Clean shutdown")

            duration = time.time() - start_time
            formatter.print_test_result(
                test_name=self.test_name,
                success=True,
                checks=checks,
                transcript=[],
                duration=duration,
            )
            return True

        except Exception as e:
            duration = time.time() - start_time
            formatter.print_test_result(
                test_name=self.test_name,
                success=False,
                checks=checks + [f"FAILED: {e}"],
                transcript=[],
                duration=duration,
            )
            try:
                await formation.shutdown()
            except Exception:
                pass
            return False


if __name__ == "__main__":
    test = TestSkillsAPIEndpoints()
    result = asyncio.run(test.test_skills_api_endpoints())
    sys.exit(0 if result else 1)
