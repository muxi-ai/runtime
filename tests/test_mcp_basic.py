#!/usr/bin/env python3
"""
Basic MCP connectivity tests.
"""

import pytest
import asyncio
from pathlib import Path
import yaml


class TestMCPBasic:
    """Basic tests for MCP configuration validation."""

    def test_mcp_configs_valid_yaml(self):
        """Test that MCP configurations are valid YAML."""
        test_formations_dir = Path(__file__).parent.parent / "test-formations"

        # Check formation-complete which has MCP configs
        mcp_dir = test_formations_dir / "formation-complete" / "mcp"
        if mcp_dir.exists():
            for mcp_file in mcp_dir.glob("*.yaml"):
                with open(mcp_file) as f:
                    config = yaml.safe_load(f)

                # Validate required fields
                assert "schema" in config, f"Missing schema in {mcp_file.name}"
                assert "id" in config, f"Missing id in {mcp_file.name}"
                assert "description" in config, f"Missing description in {mcp_file.name}"
                assert "type" in config, f"Missing type in {mcp_file.name}"

                # Validate type-specific fields
                if config["type"] == "http":
                    assert "endpoint" in config, f"HTTP MCP missing endpoint in {mcp_file.name}"
                elif config["type"] == "command":
                    assert "command" in config, f"Command MCP missing command in {mcp_file.name}"

    def test_builtin_mcp_configuration(self):
        """Test that formations can configure built-in MCPs."""
        test_formations_dir = Path(__file__).parent.parent / "test-formations"

        # Check formations that use built-in MCPs
        formations_with_builtin = ["formation-file-generation", "formation-complete"]

        for formation_name in formations_with_builtin:
            formation_yaml = test_formations_dir / formation_name / "formation.yaml"
            with open(formation_yaml) as f:
                config = yaml.safe_load(f)

            # Check muxi.built_in_mcps configuration
            if "runtime" in config and "built_in_mcps" in config["runtime"]:
                built_in_mcps = config["runtime"]["built_in_mcps"]
                assert isinstance(built_in_mcps, list), "built_in_mcps should be a list"
                assert "file-generation" in built_in_mcps, "Expected file-generation MCP"

    def test_a2a_service_configs(self):
        """Test A2A service configurations."""
        test_formations_dir = Path(__file__).parent.parent / "test-formations"

        # Check formation-complete which has A2A configs
        a2a_dir = test_formations_dir / "formation-complete" / "a2a"
        if a2a_dir.exists():
            for a2a_file in a2a_dir.glob("*.yaml"):
                with open(a2a_file) as f:
                    config = yaml.safe_load(f)

                # Validate required fields
                assert "schema" in config, f"Missing schema in {a2a_file.name}"
                assert "id" in config, f"Missing id in {a2a_file.name}"
                assert "name" in config, f"Missing name in {a2a_file.name}"
                assert "description" in config, f"Missing description in {a2a_file.name}"
                assert "url" in config, f"Missing url in {a2a_file.name}"

                # Validate URL format
                url = config["url"]
                assert url.startswith(("http://", "https://")), f"Invalid URL in {a2a_file.name}"

    def test_formation_mcp_defaults(self):
        """Test that formations have proper MCP default settings."""
        test_formations_dir = Path(__file__).parent.parent / "test-formations"

        formation_yaml = test_formations_dir / "formation-complete" / "formation.yaml"
        with open(formation_yaml) as f:
            config = yaml.safe_load(f)

        # Check MCP defaults
        if "mcp" in config:
            mcp_config = config["mcp"]
            assert "default_retry_attempts" in mcp_config
            assert isinstance(mcp_config["default_retry_attempts"], int)
            assert mcp_config["default_retry_attempts"] > 0

            assert "default_timeout_seconds" in mcp_config
            assert isinstance(mcp_config["default_timeout_seconds"], int)
            assert mcp_config["default_timeout_seconds"] > 0
