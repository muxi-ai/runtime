#!/usr/bin/env python3
"""Test 19q1: LLM settings endpoints."""

import asyncio, os, time, sys, httpx
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))
from common import BaseE2ETest, TestOutputFormatter


class TestLLMSettings(BaseE2ETest):
    def __init__(self):
        super().__init__(test_name="test_19q1_llm_settings", test_description="Test LLM settings endpoints", test_area="19_api")
        self.base_url, self.admin_key = "http://127.0.0.1:8271/v1", "test-admin-key-123"
        self.headers = {"X-Muxi-Admin-Key": self.admin_key, "Content-Type": "application/json"}

    async def test_19q1_llm_settings(self):
        formatter, start_time = TestOutputFormatter(), time.time()
        formatter.print_test_header(test_name="test_19q1_llm_settings", description="Test LLM settings endpoints")
        try:
            print("\n1. Setting up formation...")
            await self.setup_formation(formation_path=Path(__file__).parent / "formation-api")
            await self.formation.start_server(block=False)
            await asyncio.sleep(2)
            print("✅ Formation ready")

            async with httpx.AsyncClient(timeout=30.0) as client:
                # GET /v1/llm/settings
                print("\n2. Testing GET /v1/llm/settings...")
                r = await client.get(f"{self.base_url}/llm/settings", headers=self.headers)
                assert r.status_code == 200
                print("✅ GET /v1/llm/settings passed")

                # PATCH /v1/llm/settings
                print("\n3. Testing PATCH /v1/llm/settings...")
                r = await client.patch(f"{self.base_url}/llm/settings", headers=self.headers, json={"settings": {"temperature": 0.7}})
                assert r.status_code in [200, 204]
                print("✅ PATCH /v1/llm/settings passed")

                # DELETE /v1/llm/settings/{item}
                print("\n4. Testing DELETE /v1/llm/settings/{item}...")
                r = await client.delete(f"{self.base_url}/llm/settings/test_setting", headers=self.headers)
                assert r.status_code in [200, 400, 404]  # 400 = bad request (invalid key), 404 = not found
                print("✅ DELETE /v1/llm/settings/{item} verified")

                # Auth test
                print("\n5. Testing authentication...")
                r = await client.get(f"{self.base_url}/llm/settings", headers={"Content-Type": "application/json"})
                assert r.status_code == 401
                print("✅ Authentication enforced")

            formatter.print_test_result(test_name="test_19q1_llm_settings", success=True, 
                checks=["GET settings", "PATCH settings", "DELETE setting item", "Auth enforced"], 
                transcript=[], duration=time.time()-start_time)
        except Exception as e:
            formatter.print_test_result(test_name="test_19q1_llm_settings", success=False, checks=[f"Failed: {e}"], transcript=[], duration=time.time()-start_time)
            import traceback; traceback.print_exc()
            raise
        finally:
            if self.formation: await self.cleanup_formation()


async def main():
    await TestLLMSettings().test_19q1_llm_settings()


if __name__ == "__main__":
    os._exit(asyncio.run(main()) or 0)
