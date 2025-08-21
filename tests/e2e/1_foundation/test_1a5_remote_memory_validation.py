#!/usr/bin/env python3
"""Test remote memory configuration validation in formations"""

import sys
from pathlib import Path


import pytest  # noqa: F401, E402
import tempfile  # noqa: F401
import asyncio  # noqa: F401

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))


async def test_remote_memory_requires_url():
    """Test that remote memory mode requires a URL"""
    formation_yaml = """
schema: "1.0.0"
id: "test-remote-memory"
name: "Test Remote Memory"

memory:
  working:
    mode: "remote"
    max_memory_mb: 512
    remote:
      tenant: "test-tenant"
      # Missing url - should fail
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        formation_path = Path(tmpdir) / "formation.yaml"
        formation_path.write_text(formation_yaml)

        from muxi.formation.formation import Formation

        formation = Formation()

        with pytest.raises(Exception) as exc_info:
            await formation.load(str(formation_path))

        error_msg = str(exc_info.value).lower()
        assert (
            "url" in error_msg or "required" in error_msg
        ), f"Expected error about missing URL, got: {exc_info.value}"


async def test_remote_memory_requires_tenant():
    """Test that remote memory mode requires a tenant"""
    formation_yaml = """
schema: "1.0.0"
id: "test-remote-memory"
name: "Test Remote Memory"

memory:
  working:
    mode: "remote"
    max_memory_mb: 512
    remote:
      url: "tcp://localhost:45678"
      # Missing tenant - should fail
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        formation_path = Path(tmpdir) / "formation.yaml"
        formation_path.write_text(formation_yaml)

        from muxi.formation.formation import Formation

        formation = Formation()

        with pytest.raises(Exception) as exc_info:
            await formation.load(str(formation_path))

        error_msg = str(exc_info.value).lower()
        assert (
            "tenant" in error_msg or "required" in error_msg
        ), f"Expected error about missing tenant, got: {exc_info.value}"


async def test_remote_memory_requires_explicit_max_memory():
    """Test that remote memory mode requires explicit max_memory_mb (not 'auto')"""
    formation_yaml = """
schema: "1.0.0"
id: "test-remote-memory"
name: "Test Remote Memory"

memory:
  working:
    mode: "remote"
    max_memory_mb: "auto"  # Should fail - must be explicit for remote
    remote:
      url: "tcp://localhost:45678"
      tenant: "test-tenant"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        formation_path = Path(tmpdir) / "formation.yaml"
        formation_path.write_text(formation_yaml)

        from muxi.formation.formation import Formation

        formation = Formation()

        with pytest.raises(Exception) as exc_info:
            await formation.load(str(formation_path))

        error_msg = str(exc_info.value).lower()
        assert ("auto" in error_msg and "remote" in error_msg) or (
            "max_memory_mb" in error_msg and "explicit" in error_msg
        ), f"Expected error about auto not allowed for remote, got: {exc_info.value}"


async def test_remote_memory_valid_configuration():
    """Test that valid remote memory configuration loads successfully"""
    formation_yaml = """
schema: "1.0.0"
id: "test-remote-memory"
name: "Test Remote Memory"
description: "Test formation for remote memory validation"

llm:
  models:
    - text: "test/mock"

memory:
  working:
    mode: "remote"
    max_memory_mb: 512  # Explicit value
    remote:
      url: "tcp://localhost:45678"
      tenant: "test-tenant"
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        formation_path = Path(tmpdir) / "formation.yaml"
        formation_path.write_text(formation_yaml)

        from muxi.formation.formation import Formation

        formation = Formation()

        # Should load without errors
        await formation.load(str(formation_path))

        # Verify configuration
        memory_config = formation.config.get("memory", {})
        working_config = memory_config.get("working", {})

        assert working_config.get("mode") == "remote"
        assert working_config.get("max_memory_mb") == 512
        assert working_config.get("remote", {}).get("url") == "tcp://localhost:45678"
        assert working_config.get("remote", {}).get("tenant") == "test-tenant"


async def test_local_memory_allows_auto():
    """Test that local memory mode allows 'auto' for max_memory_mb"""
    formation_yaml = """
schema: "1.0.0"
id: "test-local-memory"
name: "Test Local Memory"
description: "Test formation for local memory with auto"

llm:
  models:
    - text: "test/mock"

memory:
  working:
    mode: "local"
    max_memory_mb: "auto"  # Should be allowed for local mode
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        formation_path = Path(tmpdir) / "formation.yaml"
        formation_path.write_text(formation_yaml)

        from muxi.formation.formation import Formation

        formation = Formation()

        # Should load without errors
        await formation.load(str(formation_path))

        # Verify configuration
        memory_config = formation.config.get("memory", {})
        working_config = memory_config.get("working", {})

        assert working_config.get("mode") == "local"
        assert working_config.get("max_memory_mb") == "auto"


async def test_remote_memory_with_auth():
    """Test remote memory configuration with authentication"""
    formation_yaml = """
schema: "1.0.0"
id: "test-remote-memory-auth"
name: "Test Remote Memory with Auth"
description: "Test formation for remote memory with authentication"

llm:
  models:
    - text: "test/mock"

memory:
  working:
    mode: "remote"
    max_memory_mb: 1024  # Explicit value
    remote:
      url: "tcp://localhost:65432"
      tenant: "auth-tenant"
      api_key: "test-api-key"  # Optional auth
"""

    with tempfile.TemporaryDirectory() as tmpdir:
        formation_path = Path(tmpdir) / "formation.yaml"
        formation_path.write_text(formation_yaml)

        from muxi.formation.formation import Formation

        formation = Formation()

        # Should load without errors
        await formation.load(str(formation_path))

        # Verify configuration
        memory_config = formation.config.get("memory", {})
        working_config = memory_config.get("working", {})
        remote_config = working_config.get("remote", {})

        assert working_config.get("mode") == "remote"
        assert working_config.get("max_memory_mb") == 1024
        assert remote_config.get("url") == "tcp://localhost:65432"
        assert remote_config.get("tenant") == "auth-tenant"
        assert remote_config.get("api_key") == "test-api-key"


if __name__ == "__main__":
    # Run all tests
    async def run_tests():
        print("🧪 Testing Remote Memory Configuration Validation")
        print("=" * 60)

        tests = [
            ("URL requirement", test_remote_memory_requires_url),
            ("Tenant requirement", test_remote_memory_requires_tenant),
            ("Explicit max_memory_mb", test_remote_memory_requires_explicit_max_memory),
            ("Valid configuration", test_remote_memory_valid_configuration),
            ("Local mode allows auto", test_local_memory_allows_auto),
            ("Remote with auth", test_remote_memory_with_auth),
        ]

        passed = 0
        failed = 0

        for test_name, test_func in tests:
            try:
                await test_func()
                print(f"✅ {test_name}")
                passed += 1
            except AssertionError as e:
                print(f"❌ {test_name}: {e}")
                failed += 1
            except Exception as e:
                print(f"❌ {test_name}: Unexpected error: {e}")
                failed += 1

        print("\n" + "=" * 60)
        print(f"Results: {passed} passed, {failed} failed")

        if failed == 0:
            print("✅ All remote memory validation tests passed!")
        else:
            print("❌ Some tests failed")
            exit(1)

    asyncio.run(run_tests())
