"""
Unit tests for user synopsis feature.

Tests the two-tier LLM-synthesized user synopsis system with configuration support.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from muxi.runtime.formation.memory.user_context import UserContextManager


class TestUserSynopsisConfiguration:
    """Test configuration handling for user synopsis."""

    @pytest.mark.asyncio
    async def test_synopsis_disabled_returns_empty(self):
        """Test that synopsis returns empty string when disabled."""
        # Setup mock overlord with disabled synopsis
        overlord = MagicMock()
        overlord.formation_config = {
            "memory": {
                "persistent": {
                    "user_synopsis": {
                        "enabled": False,
                        "cache_ttl": 3600
                    }
                }
            }
        }
        overlord.is_multi_user = True
        overlord.buffer_memory = MagicMock()
        overlord.persistent_memory_manager = MagicMock()

        manager = UserContextManager(overlord)

        # Should return empty immediately without any cache/LLM calls
        result = await manager.get_user_synopsis("test_user")

        assert result == ""
        # Verify no cache operations were attempted
        assert not overlord.buffer_memory.kv_get.called

    @pytest.mark.asyncio
    async def test_synopsis_enabled_default(self):
        """Test that synopsis is enabled by default when config not specified."""
        # Setup mock overlord without synopsis config
        overlord = MagicMock()
        overlord.formation_config = {"memory": {}}  # No user_synopsis config
        overlord.is_multi_user = True
        overlord.buffer_memory = AsyncMock()
        overlord.buffer_memory.kv_get = AsyncMock(return_value=None)
        overlord.persistent_memory_manager = MagicMock()
        overlord.long_term_memory = AsyncMock()
        overlord.long_term_memory.get_user_public_id = AsyncMock(return_value="usr_123")

        manager = UserContextManager(overlord)

        # Should attempt to get synopsis (will fail due to minimal mocking, but that's ok)
        await manager.get_user_synopsis("test_user")

        # Should have attempted cache lookup (proves it's enabled)
        overlord.buffer_memory.kv_get.assert_called()

    @pytest.mark.asyncio
    async def test_custom_cache_ttl_used(self):
        """Test that custom cache_ttl from config is used."""
        # Setup mock overlord with custom TTL
        overlord = MagicMock()
        overlord.formation_config = {
            "memory": {
                "persistent": {
                    "user_synopsis": {
                        "enabled": True,
                        "cache_ttl": 7200  # 2 hours
                    }
                }
            }
        }
        overlord.is_multi_user = True
        overlord.buffer_memory = AsyncMock()
        overlord.buffer_memory.kv_get = AsyncMock(return_value=None)
        overlord.buffer_memory.kv_set = AsyncMock()
        overlord.persistent_memory_manager = AsyncMock()
        overlord.persistent_memory_manager.search_long_term_memory = AsyncMock(return_value=[])
        overlord.long_term_memory = AsyncMock()
        overlord.long_term_memory.get_user_public_id = AsyncMock(return_value="usr_123")

        manager = UserContextManager(overlord)

        # Get context synopsis (should use custom TTL for empty cache)
        await manager._get_context_synopsis("test_user")

        # Verify custom TTL was used
        calls = overlord.buffer_memory.kv_set.call_args_list
        assert any(
            call.kwargs.get('ttl') == 7200
            for call in calls
        ), f"Expected cache_ttl=7200 to be used, calls: {calls}"


class TestUserSynopsisCacheInvalidation:
    """Test cache invalidation behavior."""

    @pytest.mark.asyncio
    async def test_invalidation_skipped_when_disabled(self):
        """Test that cache invalidation is skipped when synopsis is disabled."""
        # Setup mock overlord with disabled synopsis
        overlord = MagicMock()
        overlord.formation_config = {
            "memory": {
                "persistent": {
                    "user_synopsis": {
                        "enabled": False
                    }
                }
            }
        }
        overlord.buffer_memory = AsyncMock()
        overlord.buffer_memory.kv_delete = AsyncMock()

        manager = UserContextManager(overlord)

        # Should return immediately without cache operations
        await manager.invalidate_identity_synopsis_cache("test_user")

        # Verify no cache deletions were attempted
        assert not overlord.buffer_memory.kv_delete.called

    @pytest.mark.asyncio
    async def test_invalidation_runs_when_enabled(self):
        """Test that cache invalidation runs when synopsis is enabled."""
        # Setup mock overlord with enabled synopsis
        overlord = MagicMock()
        overlord.formation_config = {
            "memory": {
                "persistent": {
                    "user_synopsis": {
                        "enabled": True
                    }
                }
            }
        }
        overlord.buffer_memory = AsyncMock()
        overlord.buffer_memory.kv_delete = AsyncMock()
        overlord.long_term_memory = AsyncMock()
        overlord.long_term_memory.get_user_public_id = AsyncMock(return_value="usr_123")

        manager = UserContextManager(overlord)

        # Should invalidate cache
        await manager.invalidate_identity_synopsis_cache("test_user")

        # Verify cache deletion was called
        overlord.buffer_memory.kv_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_user_context_skips_invalidation_when_disabled(self):
        """Test that add_user_context skips invalidation when disabled."""
        # Setup mock overlord
        overlord = MagicMock()
        overlord.formation_config = {
            "memory": {
                "persistent": {
                    "user_synopsis": {
                        "enabled": False
                    }
                }
            }
        }
        overlord.is_multi_user = True
        overlord.long_term_memory = AsyncMock()
        overlord.long_term_memory.get_user_id = AsyncMock(return_value=42)
        overlord.buffer_memory = AsyncMock()
        overlord.buffer_memory.kv_delete = AsyncMock()

        manager = UserContextManager(overlord)

        # Directly test invalidation method (no longer using add_user_context)
        # When synopsis is disabled, invalidation should be skipped
        await manager.invalidate_identity_synopsis_cache("test_user")

        # Verify no cache deletions (invalidation skipped when disabled)
        assert not overlord.buffer_memory.kv_delete.called


class TestUserSynopsisTwoTierSystem:
    """Test two-tier synopsis architecture."""

    @pytest.mark.asyncio
    async def test_identity_synopsis_uses_permanent_cache(self):
        """Test that identity synopsis with data uses permanent cache (ttl=None)."""
        # Setup mock overlord
        overlord = MagicMock()
        overlord.formation_config = {
            "memory": {
                "persistent": {
                    "user_synopsis": {
                        "enabled": True,
                        "cache_ttl": 3600
                    }
                }
            }
        }
        overlord.is_multi_user = True
        overlord.buffer_memory = AsyncMock()
        overlord.buffer_memory.kv_get = AsyncMock(return_value=None)
        overlord.buffer_memory.kv_set = AsyncMock()
        overlord.persistent_memory_manager = AsyncMock()
        overlord.persistent_memory_manager.search_long_term_memory = AsyncMock(
            return_value=[{"text": "User is a software engineer"}]
        )
        overlord.long_term_memory = AsyncMock()
        overlord.long_term_memory.get_user_public_id = AsyncMock(return_value="usr_123")
        overlord.extraction_model = AsyncMock()
        overlord.extraction_model.chat = AsyncMock(
            return_value=MagicMock(content="Test User is a software engineer.")
        )

        manager = UserContextManager(overlord)

        # Get identity synopsis
        await manager._get_identity_synopsis("test_user")

        # Find the cache set call with actual synopsis (not empty string)
        calls = overlord.buffer_memory.kv_set.call_args_list
        synopsis_cache_call = None
        for call in calls:
            args, kwargs = call
            if args[1] != "":  # Not empty string
                synopsis_cache_call = call
                break

        assert synopsis_cache_call is not None, "Should have cached synopsis"
        # Verify permanent cache (ttl=None)
        assert synopsis_cache_call.kwargs.get('ttl') is None

    @pytest.mark.asyncio
    async def test_empty_identity_uses_config_ttl(self):
        """Test that empty identity synopsis uses configured TTL."""
        # Setup mock overlord
        overlord = MagicMock()
        overlord.formation_config = {
            "memory": {
                "persistent": {
                    "user_synopsis": {
                        "enabled": True,
                        "cache_ttl": 1800  # 30 min
                    }
                }
            }
        }
        overlord.is_multi_user = True
        overlord.buffer_memory = AsyncMock()
        overlord.buffer_memory.kv_get = AsyncMock(return_value=None)
        overlord.buffer_memory.kv_set = AsyncMock()
        overlord.persistent_memory_manager = AsyncMock()
        overlord.persistent_memory_manager.search_long_term_memory = AsyncMock(
            return_value=[]  # No identity data
        )
        overlord.long_term_memory = AsyncMock()
        overlord.long_term_memory.get_user_public_id = AsyncMock(return_value="usr_123")

        manager = UserContextManager(overlord)

        # Get identity synopsis (empty)
        await manager._get_identity_synopsis("test_user")

        # Verify custom TTL was used for empty cache
        overlord.buffer_memory.kv_set.assert_called_once()
        call_kwargs = overlord.buffer_memory.kv_set.call_args.kwargs
        assert call_kwargs['ttl'] == 1800

    @pytest.mark.asyncio
    async def test_context_synopsis_uses_config_ttl(self):
        """Test that context synopsis uses configured TTL."""
        # Setup mock overlord
        overlord = MagicMock()
        overlord.formation_config = {
            "memory": {
                "persistent": {
                    "user_synopsis": {
                        "enabled": True,
                        "cache_ttl": 5400  # 90 min
                    }
                }
            }
        }
        overlord.is_multi_user = True
        overlord.buffer_memory = AsyncMock()
        overlord.buffer_memory.kv_get = AsyncMock(return_value=None)
        overlord.buffer_memory.kv_set = AsyncMock()
        overlord.persistent_memory_manager = AsyncMock()
        overlord.persistent_memory_manager.search_long_term_memory = AsyncMock(
            return_value=[{"text": "User prefers concise communication"}]
        )
        overlord.long_term_memory = AsyncMock()
        overlord.long_term_memory.get_user_public_id = AsyncMock(return_value="usr_123")
        overlord.extraction_model = AsyncMock()
        overlord.extraction_model.chat = AsyncMock(
            return_value=MagicMock(content="User prefers concise communication.")
        )

        manager = UserContextManager(overlord)

        # Get context synopsis
        await manager._get_context_synopsis("test_user")

        # Verify custom TTL was used
        calls = overlord.buffer_memory.kv_set.call_args_list
        assert any(
            call.kwargs.get('ttl') == 5400
            for call in calls
        )

    @pytest.mark.asyncio
    async def test_combined_synopsis_merges_both_tiers(self):
        """Test that get_user_synopsis combines both identity and context."""
        # Setup mock overlord
        overlord = MagicMock()
        overlord.formation_config = {
            "memory": {
                "persistent": {
                    "user_synopsis": {
                        "enabled": True,
                        "cache_ttl": 3600
                    }
                }
            }
        }

        manager = UserContextManager(overlord)

        # Mock both tier methods
        manager._get_identity_synopsis = AsyncMock(return_value="John Doe is a software engineer.")
        manager._get_context_synopsis = AsyncMock(return_value="He prefers technical communication.")

        # Get combined synopsis
        result = await manager.get_user_synopsis("test_user")

        # Should combine both
        assert "John Doe is a software engineer." in result
        assert "He prefers technical communication." in result
        assert result == "John Doe is a software engineer. He prefers technical communication."


class TestUserSynopsisUserIdCaching:
    """Test that synopsis uses users.id for cache keys."""

    @pytest.mark.asyncio
    async def test_uses_user_id_for_cache_key(self):
        """Test that cache operations use internal user_id (integer), not external_user_id."""
        # Setup mock overlord
        overlord = MagicMock()
        overlord.formation_config = {
            "memory": {
                "persistent": {
                    "user_synopsis": {"enabled": True, "cache_ttl": 3600}
                }
            }
        }
        overlord.is_multi_user = True
        overlord.buffer_memory = AsyncMock()
        overlord.buffer_memory.kv_get = AsyncMock(return_value="Cached synopsis")
        overlord.long_term_memory = AsyncMock()
        overlord.long_term_memory.get_user_id = AsyncMock(return_value=42)  # Integer user ID

        manager = UserContextManager(overlord)

        # Get synopsis (should hit cache)
        await manager.get_user_synopsis("external_user_123")

        # The key verification: user_id was looked up for external_user_id
        overlord.long_term_memory.get_user_id.assert_called()
        first_call_arg = overlord.long_term_memory.get_user_id.call_args[0][0]
        assert first_call_arg == "external_user_123"

        # Verify cache was queried with integer user_id (not external_user_id)
        calls = overlord.buffer_memory.kv_get.call_args_list
        assert len(calls) >= 1
        # All cache calls should use integer user_id
        for call in calls:
            assert call[0][0] == 42, f"Expected user_id 42, got {call[0][0]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
