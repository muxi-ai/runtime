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
                "encryption_key": "test-encryption-key",
                "allowed_environments": ["development", "staging"],
                "require_https": True,
                "credential_ttl_minutes": 60,
                "max_attempts": 3
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

    def test_invalid_allowed_environments(self):
        """Test that invalid allowed_environments is rejected."""
        validator = FormationValidator()
        
        config = {
            "schema": "1.0.0",
            "id": "test-formation",
            "description": "Test formation with invalid allowed environments",
            "user_credentials": {
                "mode": "dynamic",
                "allowed_environments": "development"  # Should be a list
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            temp_path = Path(f.name)
        
        try:
            result = validator.validate(temp_path)
            assert not result.is_valid
            assert any("allowed_environments must be a list" in error for error in result.errors)
        finally:
            temp_path.unlink()

    def test_invalid_ttl(self):
        """Test that invalid TTL is rejected."""
        validator = FormationValidator()
        
        config = {
            "schema": "1.0.0",
            "id": "test-formation",
            "description": "Test formation with invalid TTL",
            "user_credentials": {
                "mode": "dynamic",
                "credential_ttl_minutes": -5  # Negative value should be rejected
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            temp_path = Path(f.name)
        
        try:
            result = validator.validate(temp_path)
            assert not result.is_valid
            assert any("credential_ttl_minutes must be a positive number" in error for error in result.errors)
        finally:
            temp_path.unlink()

    def test_invalid_max_attempts(self):
        """Test that invalid max_attempts is rejected."""
        validator = FormationValidator()
        
        config = {
            "schema": "1.0.0",
            "id": "test-formation",
            "description": "Test formation with invalid max attempts",
            "user_credentials": {
                "mode": "dynamic",
                "max_attempts": 0  # Zero should be rejected
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config, f)
            temp_path = Path(f.name)
        
        try:
            result = validator.validate(temp_path)
            assert not result.is_valid
            assert any("max_attempts must be a positive integer" in error for error in result.errors)
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