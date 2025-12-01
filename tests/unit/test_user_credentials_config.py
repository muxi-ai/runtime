"""
Tests for user credentials configuration in formations.
"""

from pathlib import Path
import tempfile
import yaml

from muxi.formation.config.validation import FormationValidator


class TestUserCredentialsConfiguration:
    """Test suite for user credentials configuration validation."""

    def test_valid_redirect_mode_configuration(self):
        """Test that valid redirect mode configuration passes validation."""
        validator = FormationValidator()
        
        config = {
            "schema": "1.0.0",
            "id": "test-formation",
            "description": "Test formation with redirect mode",
            "user_credentials": {
                "mode": "redirect",
                "redirect_message": "Please configure credentials externally"
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            temp_path = Path(f.name)
        
        try:
            result = validator.validate(temp_path)
            assert result.is_valid, f"Validation failed: {result.errors}"
        finally:
            temp_path.unlink()

    def test_valid_dynamic_mode_configuration(self):
        """Test that valid dynamic mode configuration passes validation."""
        validator = FormationValidator()
        
        config = {
            "schema": "1.0.0",
            "id": "test-formation",
            "description": "Test formation with dynamic mode",
            "user_credentials": {
                "mode": "dynamic",
                "encryption_key": "test-encryption-key"
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            temp_path = Path(f.name)
        
        try:
            result = validator.validate(temp_path)
            assert result.is_valid, f"Validation failed: {result.errors}"
        finally:
            temp_path.unlink()

    def test_invalid_mode_value(self):
        """Test that invalid mode value is rejected."""
        validator = FormationValidator()
        
        config = {
            "schema": "1.0.0",
            "id": "test-formation",
            "description": "Test formation with invalid mode",
            "user_credentials": {
                "mode": "invalid_mode"
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            temp_path = Path(f.name)
        
        try:
            result = validator.validate(temp_path)
            assert not result.is_valid
            assert any("Invalid user_credentials.mode" in error for error in result.errors)
        finally:
            temp_path.unlink()

    def test_empty_redirect_message(self):
        """Test that empty redirect message is rejected."""
        validator = FormationValidator()
        
        config = {
            "schema": "1.0.0",
            "id": "test-formation",
            "description": "Test formation with empty redirect message",
            "user_credentials": {
                "mode": "redirect",
                "redirect_message": ""
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            temp_path = Path(f.name)
        
        try:
            result = validator.validate(temp_path)
            assert not result.is_valid
            assert any("redirect_message must be a non-empty string" in error for error in result.errors)
        finally:
            temp_path.unlink()

    def test_invalid_encryption_key(self):
        """Test that invalid encryption key is rejected."""
        validator = FormationValidator()
        
        config = {
            "schema": "1.0.0",
            "id": "test-formation",
            "description": "Test formation with invalid encryption key",
            "user_credentials": {
                "mode": "dynamic",
                "encryption_key": ""  # Empty string should be rejected
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            temp_path = Path(f.name)
        
        try:
            result = validator.validate(temp_path)
            assert not result.is_valid
            assert any("encryption_key must be null or a non-empty string" in error for error in result.errors)
        finally:
            temp_path.unlink()

    def test_backward_compatibility(self):
        """Test that formations without user_credentials still validate."""
        validator = FormationValidator()
        
        config = {
            "schema": "1.0.0",
            "id": "test-formation",
            "description": "Test formation without user credentials"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            temp_path = Path(f.name)
        
        try:
            result = validator.validate(temp_path)
            assert result.is_valid, f"Validation failed: {result.errors}"
        finally:
            temp_path.unlink()

    def test_null_encryption_key_accepted(self):
        """Test that null encryption key is accepted."""
        validator = FormationValidator()
        
        config = {
            "schema": "1.0.0",
            "id": "test-formation",
            "description": "Test formation with null encryption key",
            "user_credentials": {
                "mode": "dynamic",
                "encryption_key": None  # Null should be accepted
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            temp_path = Path(f.name)
        
        try:
            result = validator.validate(temp_path)
            assert result.is_valid, f"Validation failed: {result.errors}"
        finally:
            temp_path.unlink()