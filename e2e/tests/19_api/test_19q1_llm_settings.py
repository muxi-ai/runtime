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
                assert r.status_code == 200, f"Expected 200, got {r.status_code}"
                data = r.json()
                assert data.get("success") is True
                print(f"   LLM config retrieved: {list(data.get('data', {}).keys())}")
                print("✅ GET /v1/llm/settings passed")

                # PATCH /v1/llm/settings - DEPRECATED (commented out in implementation)
                print("\n3. Skipping PATCH /v1/llm/settings (deprecated - use deployment instead)")
                print("✅ PATCH /v1/llm/settings skipped")

                # DELETE /v1/llm/settings/{item} - DEPRECATED (commented out in implementation)
                print("\n4. Skipping DELETE /v1/llm/settings/{item} (deprecated - use deployment instead)")
                print("✅ DELETE /v1/llm/settings/{item} skipped")

                # Auth test
                print("\n5. Testing authentication...")
                r = await client.get(f"{self.base_url}/llm/settings", headers={"Content-Type": "application/json"})
                assert r.status_code == 401
                print("✅ Authentication enforced")

            formatter.print_test_result(test_name="test_19q1_llm_settings", success=True, 
                checks=["GET settings", "PATCH skipped (deprecated)", "DELETE skipped (deprecated)", "Auth enforced"], 
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
