import tempfile
import yaml
from src.muxi.runtime.config.validation import FormationValidator


def test_valid_agent_knowledge_config_basic():
    """Test valid basic agent knowledge configuration."""
    formation = {
        'schema': '1.0.0',
        'id': 'test-formation',
        'description': 'Test formation',
        'agents': [
            {
                'schema': '1.0.0',
                'id': 'knowledge-agent',
                'name': 'Knowledge Agent',
                'description': 'Agent with knowledge configuration',
                'knowledge': {
                    'enabled': True
                }
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(formation, f)
        f.flush()

        validator = FormationValidator()
        result = validator.validate(f.name)

        assert result.is_valid


def test_valid_agent_knowledge_config_with_sources():
    """Test valid agent knowledge configuration with sources."""
    formation = {
        'schema': '1.0.0',
        'id': 'test-formation',
        'description': 'Test formation',
        'agents': [
            {
                'schema': '1.0.0',
                'id': 'knowledge-agent',
                'name': 'Knowledge Agent',
                'description': 'Agent with knowledge sources',
                'knowledge': {
                    'enabled': True,
                    'sources': [
                        {
                            'path': 'faq/',
                            'description': 'Frequently asked questions'
                        },
                        {
                            'path': 'products.txt',
                            'description': 'Product catalog information'
                        }
                    ]
                }
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(formation, f)
        f.flush()

        validator = FormationValidator()
        result = validator.validate(f.name)

        assert result.is_valid


def test_invalid_knowledge_enabled_type():
    """Test invalid agent knowledge enabled field type."""
    formation = {
        'schema': '1.0.0',
        'id': 'test-formation',
        'description': 'Test formation',
        'agents': [
            {
                'schema': '1.0.0',
                'id': 'knowledge-agent',
                'name': 'Knowledge Agent',
                'description': 'Agent with invalid enabled type',
                'knowledge': {
                    'enabled': 'yes'  # Should be boolean
                }
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(formation, f)
        f.flush()

        validator = FormationValidator()
        result = validator.validate(f.name)

        assert not result.is_valid
        assert any("knowledge 'enabled' must be a boolean" in error for error in result.errors)


def test_invalid_knowledge_sources_type():
    """Test invalid agent knowledge sources field type."""
    formation = {
        'schema': '1.0.0',
        'id': 'test-formation',
        'description': 'Test formation',
        'agents': [
            {
                'schema': '1.0.0',
                'id': 'knowledge-agent',
                'name': 'Knowledge Agent',
                'description': 'Agent with invalid sources type',
                'knowledge': {
                    'enabled': True,
                    'sources': 'not a list'  # Should be list
                }
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(formation, f)
        f.flush()

        validator = FormationValidator()
        result = validator.validate(f.name)

        assert not result.is_valid
        assert any("knowledge 'sources' must be a list" in error for error in result.errors)


def test_missing_knowledge_source_path():
    """Test knowledge source missing required path field."""
    formation = {
        'schema': '1.0.0',
        'id': 'test-formation',
        'description': 'Test formation',
        'agents': [
            {
                'schema': '1.0.0',
                'id': 'knowledge-agent',
                'name': 'Knowledge Agent',
                'description': 'Agent with incomplete source',
                'knowledge': {
                    'enabled': True,
                    'sources': [
                        {
                            'description': 'Missing path field'
                            # Missing: path
                        }
                    ]
                }
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(formation, f)
        f.flush()

        validator = FormationValidator()
        result = validator.validate(f.name)

        assert not result.is_valid
        errors = result.errors
        assert any("knowledge source 0 missing required field: 'path'" in error for error in errors)


def test_missing_knowledge_source_description():
    """Test knowledge source missing required description field."""
    formation = {
        'schema': '1.0.0',
        'id': 'test-formation',
        'description': 'Test formation',
        'agents': [
            {
                'schema': '1.0.0',
                'id': 'knowledge-agent',
                'name': 'Knowledge Agent',
                'description': 'Agent with incomplete source',
                'knowledge': {
                    'enabled': True,
                    'sources': [
                        {
                            'path': 'docs/'
                            # Missing: description
                        }
                    ]
                }
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(formation, f)
        f.flush()

        validator = FormationValidator()
        result = validator.validate(f.name)

        assert not result.is_valid
        expected_error = "knowledge source 0 missing required field: 'description'"
        assert any(expected_error in error for error in result.errors)


def test_invalid_knowledge_source_path_type():
    """Test knowledge source with invalid path type."""
    formation = {
        'schema': '1.0.0',
        'id': 'test-formation',
        'description': 'Test formation',
        'agents': [
            {
                'schema': '1.0.0',
                'id': 'knowledge-agent',
                'name': 'Knowledge Agent',
                'description': 'Agent with invalid path type',
                'knowledge': {
                    'enabled': True,
                    'sources': [
                        {
                            'path': 123,  # Should be string
                            'description': 'Invalid path type'
                        }
                    ]
                }
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(formation, f)
        f.flush()

        validator = FormationValidator()
        result = validator.validate(f.name)

        assert not result.is_valid
        assert any("knowledge source 0 'path' must be a string" in error for error in result.errors)


def test_empty_knowledge_source_path():
    """Test knowledge source with empty path."""
    formation = {
        'schema': '1.0.0',
        'id': 'test-formation',
        'description': 'Test formation',
        'agents': [
            {
                'schema': '1.0.0',
                'id': 'knowledge-agent',
                'name': 'Knowledge Agent',
                'description': 'Agent with empty path',
                'knowledge': {
                    'enabled': True,
                    'sources': [
                        {
                            'path': '',  # Empty path
                            'description': 'Empty path source'
                        }
                    ]
                }
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(formation, f)
        f.flush()

        validator = FormationValidator()
        result = validator.validate(f.name)

        assert not result.is_valid
        assert any("knowledge source 0 'path' cannot be empty" in error for error in result.errors)


def test_invalid_knowledge_config_type():
    """Test invalid knowledge configuration type."""
    formation = {
        'schema': '1.0.0',
        'id': 'test-formation',
        'description': 'Test formation',
        'agents': [
            {
                'schema': '1.0.0',
                'id': 'knowledge-agent',
                'name': 'Knowledge Agent',
                'description': 'Agent with invalid knowledge type',
                'knowledge': 'should be dict'  # Should be dictionary
            }
        ]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(formation, f)
        f.flush()

        validator = FormationValidator()
        result = validator.validate(f.name)

        assert not result.is_valid
        expected_error = "knowledge configuration must be a dictionary"
        assert any(expected_error in error for error in result.errors)
