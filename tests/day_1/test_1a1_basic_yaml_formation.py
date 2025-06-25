"""
Day 1 - Test Group 1A: Formation Loading Tests

Tests basic formation loading from YAML files and directory structures,
including comprehensive validation error testing.
"""
import pytest
import os
import yaml
import asyncio
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from muxi.runtime.formation import Formation
from muxi.runtime.datatypes.exceptions import (
    ConfigurationNotFoundError,
    ConfigurationValidationError,
    ConfigurationLoadError
)


class TestFormationLoading:
    """Test Group 1A: Formation Loading"""
    
    def test_1a1_basic_yaml_formation(self):
        """Test 1A1: Basic YAML Formation Loading"""
        # Run in a separate thread to avoid event loop conflict
        def run_test():
            # Create formation instance and load from directory
            formation = Formation()
            formation.load("test-formations/formation-basic/")
            assert formation is not None
            assert formation.formation_id is not None
            
            # Verify configuration was loaded
            assert formation.config is not None
            assert formation.formation_id == "basic-test-formation"
            assert "llm" in formation.config
            assert "memory" in formation.config
            
            print(f"✅ Formation loaded successfully: {formation.formation_id}")
            print(f"   Configuration keys: {list(formation.config.keys())}")
            
            # Note: Not starting overlord due to signal handler thread issue
            # This would require running in main thread, which conflicts with async tests
        
        # Execute in thread to avoid event loop conflicts
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            future.result()  # Wait for completion and raise any exceptions
    
    def test_1a2_directory_structure_formation(self):
        """Test 1A2: Directory Structure Formation Loading"""
        def run_test():
            # Test loading from directory (same as 1A1 but explicit about directory)
            formation_path = Path("test-formations/formation-basic/")
            assert formation_path.is_dir()
            
            formation = Formation()
            formation.load(str(formation_path))
            assert formation is not None
            
            # Verify formation has loaded agent from agents/ subdirectory
            overlord = formation.start_overlord()
            assert overlord is not None
            
            response = asyncio.run(overlord.chat("Hello, how are you?"))
            assert response is not None
            
            formation.stop_overlord()
        
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            future.result()
    
    def test_1a3_formation_validation_failures(self):
        """Test 1A3: Formation Validation Failures - Multiple Invalid Cases"""
        
        # Test 1: Not a YAML file
        formation = Formation()
        with pytest.raises(Exception):  # Could be yaml.YAMLError or other
            formation.load("test-formations/invalid-formations/invalid-not-yaml.txt")
        
        # Test 2: Invalid YAML syntax
        formation = Formation()
        with pytest.raises(Exception):  # yaml.YAMLError expected
            formation.load("test-formations/invalid-formations/invalid-syntax.yaml")
        
        # Test 3: Missing required keys
        formation = Formation()
        with pytest.raises(ConfigurationValidationError) as exc_info:
            formation.load("test-formations/invalid-formations/invalid-missing-keys.yaml")
        # Verify it's about missing required fields
        assert "required" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()
        
        # Test 4: Invalid schema version
        formation = Formation()
        with pytest.raises(ConfigurationValidationError) as exc_info:
            formation.load("test-formations/invalid-formations/invalid-schema.yaml")
        # Should complain about schema version
        assert "schema" in str(exc_info.value).lower()
        
        # Test 5: Invalid values (e.g., negative memory size)
        formation = Formation()
        with pytest.raises(ConfigurationValidationError) as exc_info:
            formation.load("test-formations/invalid-formations/invalid-values.yaml")
        # Should complain about invalid values
        
        # Test 6: Non-existent formation path
        formation = Formation()
        with pytest.raises(ConfigurationNotFoundError):
            formation.load("test-formations/does-not-exist/")
    
    def test_1a3_additional_validation_cases(self):
        """Test 1A3 Additional: More validation edge cases"""
        
        # Test: Empty YAML file
        formation = Formation()
        with pytest.raises(ConfigurationValidationError):
            formation.load("test-formations/invalid-formations/invalid-empty.yaml")
        
        # Test: Missing agents directory in directory-based formation
        formation = Formation()
        with pytest.raises(Exception):  # Could be FileNotFoundError or ValidationError
            formation.load("test-formations/invalid-formations/invalid-no-agents/")
    
    def test_1a4_flattened_formation_loading(self):
        """Test 1A4: Load flattened formation with agents defined in main file"""
        def run_test():
            # Load flattened formation (agents defined in formation.yaml)
            formation = Formation()
            formation.load("test-formations/formation-basic/formation-flattened.yaml")
            assert formation is not None
            assert formation.formation_id == "basic-test-formation"
            
            # Verify agents were loaded from the flattened file
            assert formation._agents_config is not None
            assert len(formation._agents_config) > 0
            assert formation._agents_config[0]["id"] == "inline-assistant"
            
            # Verify MCP servers were loaded from the flattened file
            assert formation._mcp_config is not None
            assert "servers" in formation.config.get("mcp", {})
            mcp_servers = formation.config["mcp"]["servers"]
            assert len(mcp_servers) > 0
            assert mcp_servers[0]["id"] == "local-tools"
            
            print(f"✅ Flattened formation loaded successfully!")
            print(f"   Loaded {len(formation._agents_config)} agent(s)")
            print(f"   Loaded {len(mcp_servers)} MCP server(s)")
        
        # Execute in thread to avoid event loop conflicts
        with ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            future.result()