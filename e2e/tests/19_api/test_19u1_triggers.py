#!/usr/bin/env python3
"""Test 19u1: Triggers endpoints."""

import asyncio, os, time, sys, httpx
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))
from common import BaseE2ETest, TestOutputFormatter


class TestTriggers(BaseE2ETest):
    def __init__(self):
        super().__init__(test_name="test_19u1_triggers", test_description="Test triggers endpoints", test_area="19_api")
        self.base_url, self.client_key = "http://127.0.0.1:8271/v1", "test-client-key-456"
        self.headers = {"X-Muxi-Client-Key": self.client_key, "Content-Type": "application/json"}

    async def test_19u1_triggers(self):
        formatter, start_time = TestOutputFormatter(), time.time()
        formatter.print_test_header(test_name="test_19u1_triggers", description="Test triggers endpoints")
        try:
            print("\n1. Setting up formation...")
            await self.setup_formation(formation_path=Path(__file__).parent / "formation-api-full")
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("✅ Formation ready")

            formation_id = "api-test-formation-full"
            async with httpx.AsyncClient(timeout=30.0) as client:
                # GET /v1/formations/{formation_id}/triggers
                print("\n2. Testing GET /v1/formations/{formation_id}/triggers...")
                r = await client.get(f"{self.base_url}/formations/{formation_id}/triggers", headers=self.headers)
                assert r.status_code in [200, 404]
                print("✅ GET /v1/formations/{formation_id}/triggers verified")

                # POST /v1/formations/{formation_id}/triggers/{trigger_name}
                print("\n3. Testing POST /v1/formations/{formation_id}/triggers/{trigger_name}...")
                r = await client.post(f"{self.base_url}/formations/{formation_id}/triggers/test_trigger", 
                    headers=self.headers, json={"data": {}})
                assert r.status_code in [200, 400, 404]
                print("✅ POST /v1/formations/{formation_id}/triggers/{trigger_name} verified")

                # Auth test
                print("\n4. Testing authentication...")
                r = await client.get(f"{self.base_url}/formations/{formation_id}/triggers", headers={"Content-Type": "application/json"})
                assert r.status_code == 401
                print("✅ Authentication enforced")

            formatter.print_test_result(test_name="test_19u1_triggers", success=True, 
                checks=["GET triggers", "POST trigger", "Auth enforced"], 
                transcript=[], duration=time.time()-start_time)
        except Exception as e:
            formatter.print_test_result(test_name="test_19u1_triggers", success=False, checks=[f"Failed: {e}"], transcript=[], duration=time.time()-start_time)
            import traceback; traceback.print_exc()
            raise
        finally:
            if self.formation: await self.cleanup_formation()


async def main():
    await TestTriggers().test_19u1_triggers()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
