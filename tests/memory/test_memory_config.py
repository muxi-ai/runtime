#!/usr/bin/env python3

"""
Test memory configuration functionality.
"""
import sys
import os

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.muxi.runtime.config.validation import FormationValidator


def test_memory_config_validation():
    """Test memory configuration validation."""

    # Test valid memory configuration
    valid_config = {
        'schema': '1.0.0',
        'id': 'test-formation',
        'description': 'Test formation',
        'memory': {
            'buffer': {
                'size': 10,
                'multiplier': 10,
                'vector_search': True,
                'vector_dimension': 1536,
                'mode': 'local'
            },
            'long_term': {
                'connection_string': 'sqlite:///memory.db',
                'embedding_model': 'openai/text-embedding-3-small'
            }
        }
    }

    validator = FormationValidator()
    validator._validate_formation_structure(valid_config)

    print("Memory Configuration Validation Results:")
    print(f"Valid: {validator.result.is_valid}")
    if validator.result.errors:
        print(f"Errors: {validator.result.errors}")
    if validator.result.warnings:
        print(f"Warnings: {validator.result.warnings}")

    # Test invalid memory configuration
    invalid_config = {
        'schema': '1.0.0',
        'id': 'test-formation',
        'description': 'Test formation',
        'memory': {
            'buffer': {
                'size': -5,  # Invalid: negative size
                'mode': 'invalid'  # Invalid: bad mode
            },
            'long_term': {
                'connection_string': '',  # Invalid: empty string
                'embedding_model': 123  # Invalid: not a string
            }
        }
    }

    validator2 = FormationValidator()
    validator2._validate_formation_structure(invalid_config)

    print("\nInvalid Memory Configuration Results:")
    print(f"Valid: {validator2.result.is_valid}")
    if validator2.result.errors:
        print(f"Errors: {validator2.result.errors}")


def test_remote_memory_config():
    """Test remote memory configuration."""

    remote_config = {
        'schema': '1.0.0',
        'id': 'test-formation',
        'description': 'Test formation',
        'memory': {
            'buffer': {
                'size': 20,
                'multiplier': 5,
                'vector_search': True,
                'mode': 'remote',
                'remote': {
                    'url': 'tcp://localhost:8000',
                    'api_key': '${{ secrets.FAISSX_API_KEY }}',
                    'tenant': '${{ secrets.FAISSX_TENANT_ID }}'
                }
            }
        }
    }

    validator = FormationValidator()
    validator._validate_formation_structure(remote_config)

    print("\nRemote Memory Configuration Results:")
    print(f"Valid: {validator.result.is_valid}")
    if validator.result.errors:
        print(f"Errors: {validator.result.errors}")
    if validator.result.warnings:
        print(f"Warnings: {validator.result.warnings}")


if __name__ == "__main__":
    test_memory_config_validation()
    test_remote_memory_config()
    print("\n✅ Memory configuration tests complete!")
