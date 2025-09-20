#!/usr/bin/env python3
"""Test 2E: FAISSx Integration - Both Auth Modes

This test validates:
1. FAISSx with authentication (port 65432)
2. FAISSx without authentication but with tenant (port 45678)
3. Vector search functionality
4. WorkingMemory integration
"""

import sys
import asyncio
import time
import os
import numpy as np
from pathlib import Path

# Add path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from .base_memory_test import BaseMemoryTest  # noqa: E402
from muxi.services.memory.working import WorkingMemory  # noqa: E402


# Mock LLM for testing
class MockLLM:
    async def embed(self, text):
        # Simple hash-based embedding
        text_hash = hash(text) % 1000
        return [text_hash / 1000.0] + [0.1] * 1535


class TestFAISSxBothModes(BaseMemoryTest):
    """Test FAISSx integration with both auth modes."""

    async def test_faissx_no_auth_mode(self):
        """Test FAISSx on port 45678 - No auth but with tenant ID."""
        print("\n  🔓 Testing FAISSx Port 45678 - No Auth + Tenant ID")

        try:
            import faissx.client as faiss
            from muxi.services.secrets.secrets_manager import SecretsManager

            # Load tenant ID from secrets
            secrets_manager = SecretsManager(str(self.FORMATION_DIR))
            await secrets_manager.initialize_encryption()
            tenant_id = await secrets_manager.get_secret("FAISSX_TENANT_ID")

            print("    Server: tcp://localhost:45678")
            print(f"    Tenant: {tenant_id}")
            print("    API Key: None")

            # Configure with tenant but no auth
            faiss.configure(server="tcp://localhost:45678", tenant_id=tenant_id, timeout=5.0)

            # Test basic operations
            index = faiss.IndexFlatL2(128)
            vectors = np.random.rand(3, 128).astype("float32")
            index.add(vectors)

            query = np.random.rand(1, 128).astype("float32")
            distances, indices = index.search(query, k=2)

            # Test with WorkingMemory
            buffer = WorkingMemory(
                formation_id="test_formation",
                max_size=5,
                buffer_multiplier=2,
                dimension=1536,
                model=MockLLM(),
                mode="remote",
                remote={"url": "tcp://localhost:45678", "tenant": tenant_id},
            )

            await buffer.add("Test message for tenant", {"source": "no-auth"})
            results = await buffer.search("test", limit=1)

            print("    ✓ Operations successful")
            print(f"    ✓ Index count: {index.ntotal}")
            print(f"    ✓ Search results: {len(indices[0])}")
            print(f"    ✓ Buffer items: {len(buffer)}")
            print(f"    ✓ Memory search results: {len(results)}")

            return True, {
                "port": 45678,
                "auth_required": False,
                "tenant_required": True,
                "tenant_id": tenant_id,
                "index_count": index.ntotal,
                "search_results": len(indices[0]),
                "buffer_size": len(buffer),
                "memory_results": len(results),
            }

        except Exception as e:
            print(f"    ❌ No-auth mode failed: {str(e)}")
            return False, {"error": str(e)}

    async def test_faissx_full_auth_mode(self):
        """Test FAISSx on port 65432 - Full authentication."""
        print("\n  🔐 Testing FAISSx Port 65432 - Full Auth (API Key + Tenant)")

        try:
            import faissx.client as faiss
            from muxi.services.secrets.secrets_manager import SecretsManager

            # Load authentication from secrets
            secrets_manager = SecretsManager(str(self.FORMATION_DIR))
            await secrets_manager.initialize_encryption()
            api_key = await secrets_manager.get_secret("FAISSX_API_KEY")
            tenant_id = await secrets_manager.get_secret("FAISSX_TENANT_ID")

            print("    Server: tcp://localhost:65432")
            print(f"    Tenant: {tenant_id}")
            print(f"    API Key: {api_key[:10]}...")

            # Configure with full auth
            faiss.configure(
                server="tcp://localhost:65432", api_key=api_key, tenant_id=tenant_id, timeout=5.0
            )

            # Test basic operations
            index = faiss.IndexFlatL2(128)
            vectors = np.random.rand(3, 128).astype("float32")
            index.add(vectors)

            query = np.random.rand(1, 128).astype("float32")
            distances, indices = index.search(query, k=2)

            # Test with WorkingMemory
            buffer = WorkingMemory(
                formation_id="test_formation",
                max_size=5,
                buffer_multiplier=2,
                dimension=1536,
                model=MockLLM(),
                mode="remote",
                remote={"url": "tcp://localhost:65432", "api_key": api_key, "tenant": tenant_id},
            )

            await buffer.add("Authenticated message", {"source": "full-auth"})
            results = await buffer.search("authenticated", limit=1)

            print("    ✓ Operations successful")
            print(f"    ✓ Index count: {index.ntotal}")
            print(f"    ✓ Search results: {len(indices[0])}")
            print(f"    ✓ Buffer items: {len(buffer)}")
            print(f"    ✓ Memory search results: {len(results)}")

            return True, {
                "port": 65432,
                "auth_required": True,
                "tenant_required": True,
                "api_key": api_key[:10] + "...",
                "tenant_id": tenant_id,
                "index_count": index.ntotal,
                "search_results": len(indices[0]),
                "buffer_size": len(buffer),
                "memory_results": len(results),
            }

        except Exception as e:
            print(f"    ❌ Full-auth mode failed: {str(e)}")
            return False, {"error": str(e)}

    async def test_formation_configurations(self):
        """Test loading formations with different FAISSx configs."""
        print("\n  📄 Testing Formation Configurations")

        from muxi.formation import Formation

        formations_to_test = [
            {
                "config": "postgres_faissx",
                "name": "No Auth + Tenant",
                "expected_port": "45678",
                "has_auth": False,
            },
            {
                "config": "postgres_faissx_auth",
                "name": "Full Auth",
                "expected_port": "65432",
                "has_auth": True,
            },
        ]

        results = []
        all_passed = True

        for formation_config in formations_to_test:
            print(f"    Testing: {formation_config['name']}")

            try:
                formation = Formation()
                yaml_file = self.MEMORY_CONFIGS.get(formation_config["config"])
                if yaml_file:
                    formation_path = self.FORMATION_DIR / yaml_file
                    await formation.load(str(formation_path))

                    # Extract memory config
                    memory_config = formation.config.get("memory", {})
                    working_config = memory_config.get("working", {})
                    remote_config = working_config.get("remote", {})

                    result = {
                        "loaded": True,
                        "mode": working_config.get("mode"),
                        "url": remote_config.get("url"),
                        "has_api_key": "api_key" in remote_config,
                        "has_tenant": "tenant" in remote_config,
                    }

                    print("      ✓ Formation loaded successfully")
                    print(f"      ✓ Mode: {result['mode']}")
                    print(f"      ✓ URL: {result['url']}")
                    print(f"      ✓ Has API key: {result['has_api_key']}")
                    print(f"      ✓ Has tenant: {result['has_tenant']}")

                    # Verify configuration
                    port_correct = formation_config["expected_port"] in result.get("url", "")
                    auth_correct = result["has_api_key"] == formation_config["has_auth"]

                    if not port_correct:
                        print("      ❌ Wrong port in URL")
                        all_passed = False
                    if not auth_correct:
                        print("      ❌ Auth config mismatch")
                        all_passed = False

                    await formation.shutdown()

                else:
                    print(f"      ❌ Unknown formation config: {formation_config['config']}")
                    all_passed = False
                    result = {"loaded": False, "error": "Unknown config"}

                results.append({"name": formation_config["name"], "result": result})

            except Exception as e:
                print(f"      ❌ Failed to load: {str(e)}")
                all_passed = False
                results.append(
                    {"name": formation_config["name"], "result": {"loaded": False, "error": str(e)}}
                )

        return all_passed, results

    async def test_faissx_modes(self):
        """Main test method."""
        test_name = "2e_faissx_both_modes"
        self.print_test_header(test_name, "Test FAISSx with and without authentication")

        start_time = time.time()
        checks_passed = []
        transcript = []
        all_passed = True

        try:
            print("  Testing FAISSx Both Authentication Modes...")

            # Test 1: No auth mode (port 45678)
            no_auth_success, no_auth_result = await self.test_faissx_no_auth_mode()
            if no_auth_success:
                checks_passed.append("FAISSx no-auth mode (port 45678) working")
                transcript.append(("System", f"No-auth FAISSx test passed: {no_auth_result}"))
            else:
                all_passed = False
                transcript.append(("System", f"No-auth FAISSx test failed: {no_auth_result}"))

            # Test 2: Full auth mode (port 65432)
            full_auth_success, full_auth_result = await self.test_faissx_full_auth_mode()
            if full_auth_success:
                checks_passed.append("FAISSx full-auth mode (port 65432) working")
                transcript.append(("System", f"Full-auth FAISSx test passed: {full_auth_result}"))
            else:
                all_passed = False
                transcript.append(("System", f"Full-auth FAISSx test failed: {full_auth_result}"))

            # Test 3: Formation configurations
            formations_success, formations_result = await self.test_formation_configurations()
            if formations_success:
                checks_passed.append("Formation configurations loaded correctly")
                transcript.append(
                    ("System", f"Formation tests passed: {len(formations_result)} configs tested")
                )
            else:
                all_passed = False
                transcript.append(("System", f"Formation tests failed: {formations_result}"))

            # Summary
            if no_auth_success and full_auth_success:
                print("  ✅ BOTH FAISSx CONFIGURATIONS WORKING!")
                print("    - Port 45678: Requires only tenant ID (no auth)")
                print("    - Port 65432: Requires both API key and tenant ID")
                print("    - WorkingMemory integrates correctly with both")
                checks_passed.append("Both FAISSx configurations functional")
            else:
                print("  ⚠️ PARTIAL SUCCESS")
                if no_auth_success:
                    print("    - Port 45678 (no auth) is working ✅")
                else:
                    print("    - Port 45678 (no auth) is NOT working ❌")
                if full_auth_success:
                    print("    - Port 65432 (full auth) is working ✅")
                else:
                    print("    - Port 65432 (full auth) is NOT working ❌")

        except Exception as e:
            print(f"  ✗ Test failed with error: {e}")
            all_passed = False
            transcript.append(("System", f"Test failed with error: {str(e)}"))

        finally:
            await self.cleanup()

        duration = time.time() - start_time
        self.print_test_result(test_name, all_passed, checks_passed, transcript, duration)

        return all_passed

    async def run_test(self):
        """Run all test cases."""
        print("\n" + "=" * 60)
        print("🔐 AREA 2E: FAISSX BOTH MODES")
        print("=" * 60)

        # Run test cases
        result = await self.test_faissx_modes()

        print("\n" + "=" * 60)
        print(f"🎯 OVERALL RESULT: {'✅ ALL TESTS PASSED' if result else '❌ SOME TESTS FAILED'}")
        print("=" * 60)

        return result


def main():
    """Main entry point."""
    test = TestFAISSxBothModes()
    result = asyncio.run(test.run_test())
    os._exit(0 if result else 1)


if __name__ == "__main__":
    main()
