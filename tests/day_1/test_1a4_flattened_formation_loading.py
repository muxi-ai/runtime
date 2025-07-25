"""
Simple Formation Loading Test - Day 1 Foundation

This test verifies basic formation loading without starting the overlord.
"""
import pytest
import os
import asyncio
from pathlib import Path
from muxi.formation import Formation
from muxi.datatypes.exceptions import (
    ConfigurationNotFoundError,
    ConfigurationValidationError,
)


class TestSimpleFormationLoading:
    """Basic formation loading tests without overlord startup"""

    async def test_load_valid_formation(self):
        """Test loading a valid formation configuration"""
        formation = Formation()
        await formation.load("test-formations/formation-basic/")

        # Verify configuration was loaded
        assert formation.config is not None
        assert formation.formation_id is not None
        assert "agents" in formation._agents_config or formation._agents_config is not None

    async def test_load_nonexistent_formation(self):
        """Test loading from non-existent path"""
        formation = Formation()

        with pytest.raises(ConfigurationNotFoundError) as exc_info:
            await formation.load("test-formations/does-not-exist/")

        assert "not found" in str(exc_info.value).lower()

    async def test_load_invalid_yaml(self):
        """Test loading invalid YAML syntax"""
        formation = Formation()

        # Should raise some form of error for invalid YAML
        with pytest.raises(Exception) as exc_info:
            await formation.load("test-formations/invalid-syntax.yaml")

        # Could be yaml.YAMLError or wrapped in ConfigurationLoadError
        assert exc_info.value is not None

    async def test_formation_state_after_load(self):
        """Test formation state after successful load"""
        formation = Formation()

        # Initially no config
        assert formation.config is None
        assert formation._is_running is False

        # Load configuration
        await formation.load("test-formations/formation-basic/")

        # Config should be loaded but not running
        assert formation.config is not None
        assert formation._is_running is False
        assert formation.secrets_manager is not None

    async def test_multiple_load_attempts(self):
        """Test loading different formations sequentially"""
        formation = Formation()

        # First load
        await formation.load("test-formations/formation-basic/")
        first_id = formation.formation_id

        # Cannot load while running (if we started overlord)
        # But since we haven't started, we should be able to load again
        await formation.load("test-formations/formation-multi-agent/")
        second_id = formation.formation_id

        # Formation ID might change based on config
        assert formation.config is not None
