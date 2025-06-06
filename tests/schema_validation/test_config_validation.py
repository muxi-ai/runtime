#!/usr/bin/env python3
"""
Test script to validate updated configuration files.
"""
import sys
sys.path.append('.')

from muxi.runtime.config.validation import FormationValidator


def test_config_validations():
    """Test validation of updated configuration files."""

    validator = FormationValidator()

    # Test the knowledge agent
    print("Testing Knowledge Agent Configuration...")
    result = validator.validate('examples/knowledge/knowledge_agent.yaml')
    print(f'Valid: {result.is_valid}')
    if result.errors:
        print(f'Errors: {result.errors}')
    if result.warnings:
        print(f'Warnings: {result.warnings}')
    print()

    # Test postgres memory agent
    print("Testing Postgres Memory Agent Configuration...")
    result = validator.validate('tests/configs/postgres_memory_agent.yaml')
    print(f'Valid: {result.is_valid}')
    if result.errors:
        print(f'Errors: {result.errors}')
    if result.warnings:
        print(f'Warnings: {result.warnings}')
    print()

    # Test sqlite memory agent
    print("Testing SQLite Memory Agent Configuration...")
    result = validator.validate('tests/configs/sqlite_memory_agent.yaml')
    print(f'Valid: {result.is_valid}')
    if result.errors:
        print(f'Errors: {result.errors}')
    if result.warnings:
        print(f'Warnings: {result.warnings}')
    print()

    # Test default sqlite agent
    print("Testing Default SQLite Agent Configuration...")
    result = validator.validate('tests/configs/default_sqlite_agent.yaml')
    print(f'Valid: {result.is_valid}')
    if result.errors:
        print(f'Errors: {result.errors}')
    if result.warnings:
        print(f'Warnings: {result.warnings}')
    print()

    print('✅ All configuration file validations completed!')


if __name__ == '__main__':
    test_config_validations()
