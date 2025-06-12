"""
Test A2A service validation functionality.

Tests the comprehensive A2A service validation according to SCHEMA_GUIDE.md,
including all required fields, optional metadata, authentication types,
and error conditions.
"""

import tempfile
import yaml
from pathlib import Path
from src.muxi.runtime.config.validation import FormationValidator


class TestA2AServiceValidation:
    """Test A2A service validation according to SCHEMA_GUIDE.md."""

    def test_valid_a2a_service_config(self):
        """Test valid A2A service configuration passes validation."""
        a2a_service = {
            'schema': '1.0.0',
            'id': 'external-billing-service',
            'name': 'External Billing Service',
            'description': 'External billing and payment processing service',
            'url': 'https://billing.external.com/a2a',
            'active': True,
            'author': 'External Partner <api@external.com>',
            'version': '2.1.0',
            'documentation': 'https://docs.external.com/a2a',
            'support_contact': 'support@external.com',
            'retry_attempts': 5,
            'timeout_seconds': 45,
            'auth': {
                'type': 'api_key',
                'header': 'X-API-Key',
                'key': '${{ secrets.EXTERNAL_BILLING_API_KEY }}'
            }
        }

        formation = {
            'schema': '1.0.0',
            'id': 'test-formation',
            'description': 'Test formation',
            'a2a': {
                'outbound': {
                    'services': [a2a_service]
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            f.flush()

            validator = FormationValidator()
            result = validator.validate(f.name)

            assert result.is_valid

    def test_a2a_service_missing_required_fields(self):
        """Test A2A service with missing required fields."""
        a2a_service = {
            'schema': '1.0.0',
            'id': 'incomplete-service'
            # Missing: name, description, url
        }

        formation = {
            'schema': '1.0.0',
            'id': 'test-formation',
            'description': 'Test formation',
            'a2a': {
                'outbound': {
                    'services': [a2a_service]
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            f.flush()

            validator = FormationValidator()
            result = validator.validate(f.name)

            assert not result.is_valid

    def test_a2a_service_invalid_url(self):
        """Test A2A service with invalid URL format."""
        a2a_service = {
            'schema': '1.0.0',
            'id': 'invalid-url-service',
            'name': 'Invalid URL Service',
            'description': 'Service with invalid URL',
            'url': 'ftp://invalid.protocol.com/a2a'  # Invalid protocol
        }

        formation = {
            'schema': '1.0.0',
            'id': 'test-formation',
            'description': 'Test formation',
            'a2a': {
                'outbound': {
                    'services': [a2a_service]
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            f.flush()

            validator = FormationValidator()
            result = validator.validate(f.name)

            assert not result.is_valid

    def test_a2a_service_bearer_auth(self):
        """Test A2A service with bearer token authentication."""
        a2a_service = {
            'schema': '1.0.0',
            'id': 'bearer-auth-service',
            'name': 'Bearer Auth Service',
            'description': 'Service with bearer authentication',
            'url': 'https://api.example.com/a2a',
            'auth': {
                'type': 'bearer',
                'token': '${{ secrets.EXTERNAL_SERVICE_TOKEN }}'
            }
        }

        formation = {
            'schema': '1.0.0',
            'id': 'test-formation',
            'description': 'Test formation',
            'a2a': {
                'outbound': {
                    'services': [a2a_service]
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            f.flush()

            validator = FormationValidator()
            result = validator.validate(f.name)

            assert result.is_valid

    def test_a2a_service_basic_auth(self):
        """Test A2A service with basic authentication."""
        a2a_service = {
            'schema': '1.0.0',
            'id': 'basic-auth-service',
            'name': 'Basic Auth Service',
            'description': 'Service with basic authentication',
            'url': 'https://api.example.com/a2a',
            'auth': {
                'type': 'basic',
                'username': '${{ secrets.EXTERNAL_USERNAME }}',
                'password': '${{ secrets.EXTERNAL_PASSWORD }}'
            }
        }

        formation = {
            'schema': '1.0.0',
            'id': 'test-formation',
            'description': 'Test formation',
            'a2a': {
                'outbound': {
                    'services': [a2a_service]
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            f.flush()

            validator = FormationValidator()
            result = validator.validate(f.name)

            assert result.is_valid

    def test_a2a_service_custom_auth(self):
        """Test A2A service with custom authentication headers."""
        a2a_service = {
            'schema': '1.0.0',
            'id': 'custom-auth-service',
            'name': 'Custom Auth Service',
            'description': 'Service with custom authentication',
            'url': 'https://api.example.com/a2a',
            'auth': {
                'type': 'custom',
                'headers': {
                    'Authorization': 'Custom ${{ secrets.CUSTOM_TOKEN }}',
                    'X-Client-ID': '${{ secrets.CLIENT_ID }}',
                    'X-Tenant': '${{ secrets.TENANT_ID }}'
                }
            }
        }

        formation = {
            'schema': '1.0.0',
            'id': 'test-formation',
            'description': 'Test formation',
            'a2a': {
                'outbound': {
                    'services': [a2a_service]
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            f.flush()

            validator = FormationValidator()
            result = validator.validate(f.name)

            assert result.is_valid

    def test_a2a_service_invalid_auth_type(self):
        """Test A2A service with invalid authentication type."""
        a2a_service = {
            'schema': '1.0.0',
            'id': 'invalid-auth-service',
            'name': 'Invalid Auth Service',
            'description': 'Service with invalid auth type',
            'url': 'https://api.example.com/a2a',
            'auth': {
                'type': 'invalid_type',
                'token': '${{ secrets.TOKEN }}'
            }
        }

        formation = {
            'schema': '1.0.0',
            'id': 'test-formation',
            'description': 'Test formation',
            'a2a': {
                'outbound': {
                    'services': [a2a_service]
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            f.flush()

            validator = FormationValidator()
            result = validator.validate(f.name)

            assert not result.is_valid

    def test_a2a_service_incomplete_bearer_auth(self):
        """Test A2A service with incomplete bearer authentication."""
        a2a_service = {
            'schema': '1.0.0',
            'id': 'incomplete-bearer-service',
            'name': 'Incomplete Bearer Service',
            'description': 'Service with incomplete bearer auth',
            'url': 'https://api.example.com/a2a',
            'auth': {
                'type': 'bearer'
                # Missing: token
            }
        }

        formation = {
            'schema': '1.0.0',
            'id': 'test-formation',
            'description': 'Test formation',
            'a2a': {
                'outbound': {
                    'services': [a2a_service]
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            f.flush()

            validator = FormationValidator()
            result = validator.validate(f.name)

            assert not result.is_valid

    def test_a2a_service_invalid_retry_attempts(self):
        """Test A2A service with invalid retry attempts."""
        a2a_service = {
            'schema': '1.0.0',
            'id': 'invalid-retry-service',
            'name': 'Invalid Retry Service',
            'description': 'Service with invalid retry attempts',
            'url': 'https://api.example.com/a2a',
            'retry_attempts': -1  # Invalid: negative value
        }

        formation = {
            'schema': '1.0.0',
            'id': 'test-formation',
            'description': 'Test formation',
            'a2a': {
                'outbound': {
                    'services': [a2a_service]
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            f.flush()

            validator = FormationValidator()
            result = validator.validate(f.name)

            assert not result.is_valid

    def test_a2a_directory_validation(self):
        """Test A2A directory validation with actual files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create formation directory structure
            formation_dir = temp_path / 'test_formation'
            formation_dir.mkdir()
            a2a_dir = formation_dir / 'a2a'
            a2a_dir.mkdir()

            # Create formation.yaml
            formation_config = {
                'schema': '1.0.0',
                'id': 'test-formation',
                'description': 'Test formation for A2A validation'
            }

            with open(formation_dir / 'formation.yaml', 'w') as f:
                yaml.dump(formation_config, f)

            # Create valid A2A service file
            valid_service = {
                'schema': '1.0.0',
                'id': 'external-service',
                'name': 'External Service',
                'description': 'External A2A service',
                'url': 'https://api.external.com/a2a',
                'auth': {
                    'type': 'api_key',
                    'key': '${{ secrets.EXTERNAL_API_KEY }}'
                }
            }

            with open(a2a_dir / 'external_service.yaml', 'w') as f:
                yaml.dump(valid_service, f)

            # Create invalid A2A service file
            invalid_service = {
                'schema': '1.0.0',
                'id': 'invalid-service'
                # Missing required fields
            }

            with open(a2a_dir / 'invalid_service.yaml', 'w') as f:
                yaml.dump(invalid_service, f)

            validator = FormationValidator()
            result = validator.validate(formation_dir)

            assert not result.is_valid

    def test_duplicate_a2a_service_ids(self):
        """Test validation of duplicate A2A service IDs."""
        service1 = {
            'schema': '1.0.0',
            'id': 'duplicate-id',
            'name': 'Service One',
            'description': 'First service',
            'url': 'https://api1.example.com/a2a'
        }

        service2 = {
            'schema': '1.0.0',
            'id': 'duplicate-id',  # Same ID as service1
            'name': 'Service Two',
            'description': 'Second service',
            'url': 'https://api2.example.com/a2a'
        }

        formation = {
            'schema': '1.0.0',
            'id': 'test-formation',
            'description': 'Test formation',
            'a2a': {
                'outbound': {
                    'services': [service1, service2]
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            f.flush()

            validator = FormationValidator()
            result = validator.validate(f.name)

            assert not result.is_valid
