#!/usr/bin/env python3
"""
Test comprehensive logging configuration according to multi-stream schema

This test module validates:
1. Logging configuration validation in FormationValidator (multi-stream)
2. Logging configuration initialization in Overlord (multi-stream)
3. All logging configuration fields according to the new schema
"""

import pytest
import tempfile
import yaml
from pathlib import Path

# Import the classes to test
from muxi.runtime.config.validation import FormationValidator
from muxi.runtime.overlord import Overlord


class TestLoggingConfigValidation:
    """Test logging configuration validation according to multi-stream schema"""

    def setup_method(self):
        """Set up test fixtures"""
        self.validator = FormationValidator()

    def create_test_formation(self, logging_config):
        """Create a test formation with logging config"""
        return {
            'schema': '1.0.0',
            'id': 'test-formation',
            'description': 'Test formation for logging validation',
            'logging': logging_config
        }

    def test_valid_logging_config_stdout(self):
        """Test valid logging configuration with stdout transport"""
        logging_config = {
            'enabled': True,
            'streams': [
                {
                    'transport': 'stdout',
                    'level': 'info',
                    'format': 'jsonl',
                    'events': ['*']
                }
            ]
        }

        formation = self.create_test_formation(logging_config)

        # Create temporary file for testing
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert result.is_valid
            assert len(result.errors) == 0
        finally:
            temp_file.unlink()

    def test_valid_logging_config_file(self):
        """Test valid logging configuration with file transport"""
        logging_config = {
            'enabled': True,
            'streams': [
                {
                    'transport': 'file',
                    'level': 'debug',
                    'format': 'text',
                    'destination': '/var/logs/muxi.log',
                    'events': ['*']
                }
            ]
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert result.is_valid
            assert len(result.errors) == 0
        finally:
            temp_file.unlink()

    def test_valid_logging_config_stream_zmq(self):
        """Test valid logging configuration with ZMQ stream transport"""
        logging_config = {
            'enabled': True,
            'streams': [
                {
                    'transport': 'stream',
                    'level': 'info',
                    'format': 'msgpack',
                    'destination': 'tcp://server:8000/ingest',
                    'protocol': 'zmq',
                    'events': ['*'],
                    'auth': {
                        'type': 'token',
                        'token': '${{ secrets.ZMQ_TOKEN }}'
                    }
                }
            ]
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert result.is_valid
            assert len(result.errors) == 0
        finally:
            temp_file.unlink()

    def test_valid_logging_config_stream_webhook(self):
        """Test valid logging configuration with webhook stream transport"""
        logging_config = {
            'enabled': True,
            'streams': [
                {
                    'transport': 'stream',
                    'level': 'warn',
                    'format': 'datadog_json',
                    'destination': 'https://logs.datadoghq.com/v1/input/api_key',
                    'protocol': 'webhook',
                    'events': ['error.*', 'request.received'],
                    'auth': {
                        'type': 'bearer',
                        'token': '${{ secrets.DATADOG_TOKEN }}'
                    }
                }
            ]
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert result.is_valid
            assert len(result.errors) == 0
        finally:
            temp_file.unlink()

    def test_valid_logging_config_trail(self):
        """Test valid logging configuration with MUXI trail transport"""
        logging_config = {
            'enabled': True,
            'streams': [
                {
                    'transport': 'trail',
                    'auth': {
                        'type': 'bearer',
                        'token': '${{ secrets.TRAIL_TOKEN }}'
                    }
                }
            ]
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert result.is_valid
            assert len(result.errors) == 0
        finally:
            temp_file.unlink()

    def test_valid_logging_config_multiple_streams(self):
        """Test valid logging configuration with multiple streams"""
        logging_config = {
            'enabled': True,
            'streams': [
                {
                    'transport': 'stdout',
                    'level': 'info',
                    'format': 'jsonl',
                    'events': ['request.received', 'response.delivered']
                },
                {
                    'transport': 'file',
                    'level': 'debug',
                    'format': 'text',
                    'destination': '/var/logs/debug.log',
                    'events': ['*']
                },
                {
                    'transport': 'stream',
                    'level': 'error',
                    'format': 'elastic_bulk',
                    'destination': 'https://elastic.company.com/_bulk',
                    'protocol': 'webhook',
                    'events': ['error.*'],
                    'auth': {
                        'type': 'basic',
                        'username': '${{ secrets.ELASTIC_USER }}',
                        'password': '${{ secrets.ELASTIC_PASS }}'
                    }
                }
            ]
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert result.is_valid
            assert len(result.errors) == 0
        finally:
            temp_file.unlink()

    def test_missing_streams_array(self):
        """Test missing streams array"""
        logging_config = {
            'enabled': True
            # Missing 'streams' array
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert not result.is_valid
            assert any("must include 'streams' array" in error for error in result.errors)
        finally:
            temp_file.unlink()

    def test_invalid_transport(self):
        """Test invalid transport type"""
        logging_config = {
            'enabled': True,
            'streams': [
                {
                    'transport': 'invalid_transport',
                    'level': 'info',
                    'format': 'jsonl'
                }
            ]
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert not result.is_valid
            assert any("invalid transport" in error for error in result.errors)
        finally:
            temp_file.unlink()

    def test_invalid_level(self):
        """Test invalid log level"""
        logging_config = {
            'enabled': True,
            'streams': [
                {
                    'transport': 'stdout',
                    'level': 'invalid_level',
                    'format': 'jsonl'
                }
            ]
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert not result.is_valid
            assert any("invalid level" in error for error in result.errors)
        finally:
            temp_file.unlink()

    def test_invalid_format(self):
        """Test invalid format type"""
        logging_config = {
            'enabled': True,
            'streams': [
                {
                    'transport': 'stdout',
                    'level': 'info',
                    'format': 'invalid_format'
                }
            ]
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert not result.is_valid
            assert any("invalid format" in error for error in result.errors)
        finally:
            temp_file.unlink()

    def test_missing_destination_for_file(self):
        """Test missing destination for file transport"""
        logging_config = {
            'enabled': True,
            'streams': [
                {
                    'transport': 'file',
                    'level': 'info',
                    'format': 'text'
                    # Missing 'destination' field
                }
            ]
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert not result.is_valid
            assert any("requires 'destination' field" in error for error in result.errors)
        finally:
            temp_file.unlink()

    def test_missing_destination_for_stream(self):
        """Test missing destination for stream transport"""
        logging_config = {
            'enabled': True,
            'streams': [
                {
                    'transport': 'stream',
                    'level': 'info',
                    'format': 'jsonl'
                    # Missing 'destination' field
                }
            ]
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert not result.is_valid
            assert any("requires 'destination' field" in error for error in result.errors)
        finally:
            temp_file.unlink()

    def test_missing_auth_for_trail(self):
        """Test missing auth for trail transport"""
        logging_config = {
            'enabled': True,
            'streams': [
                {
                    'transport': 'trail'
                    # Missing 'auth' field
                }
            ]
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert not result.is_valid
            assert any("requires 'auth' configuration" in error for error in result.errors)
        finally:
            temp_file.unlink()

    def test_protocol_auto_detection_suggestions(self):
        """Test that protocol auto-detection provides suggestions"""
        logging_config = {
            'enabled': True,
            'streams': [
                {
                    'transport': 'stream',
                    'level': 'info',
                    'format': 'jsonl',
                    'destination': 'https://webhook.example.com/logs'
                    # No explicit protocol - should suggest 'webhook'
                }
            ]
        }

        formation = self.create_test_formation(logging_config)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(formation, f)
            temp_file = Path(f.name)

        try:
            result = self.validator.validate(temp_file)
            assert result.is_valid
            protocol_suggestion = any(
                "consider adding 'protocol:" in suggestion
                for suggestion in result.suggestions
            )
            assert protocol_suggestion
            assert any("webhook" in suggestion for suggestion in result.suggestions)
        finally:
            temp_file.unlink()

    def test_new_logging_formats(self):
        """Test new logging formats (grafana_loki, newrelic_json, opentelemetry)"""
        new_formats = ['grafana_loki', 'newrelic_json', 'opentelemetry']

        for format_name in new_formats:
            logging_config = {
                'enabled': True,
                'streams': [
                    {
                        'transport': 'stdout',
                        'level': 'info',
                        'format': format_name,
                        'events': ['request.received', 'response.delivered']
                    }
                ]
            }

            formation = self.create_test_formation(logging_config)

            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                yaml.dump(formation, f)
                temp_file = Path(f.name)

            try:
                result = self.validator.validate(temp_file)
                error_msg = (
                    f"Format '{format_name}' should be valid but validation "
                    f"failed with errors: {result.errors}"
                )
                assert result.is_valid, error_msg
                error_msg = (
                    f"Format '{format_name}' produced unexpected errors: "
                    f"{result.errors}"
                )
                assert len(result.errors) == 0, error_msg
            finally:
                temp_file.unlink()


class TestLoggingConfigInitialization:
    """Test logging configuration initialization in Overlord"""

    @pytest.mark.asyncio
    async def test_logging_config_initialization(self):
        """Test that overlord initializes multi-stream logging configuration correctly"""
        formation_config = {
            'schema': '1.0.0',
            'id': 'test-formation',
            'description': 'Test formation for logging initialization',
            'logging': {
                'enabled': True,
                'streams': [
                    {
                        'transport': 'stdout',
                        'level': 'debug',
                        'format': 'jsonl',
                        'events': ['request.received', 'response.delivered']
                    },
                    {
                        'transport': 'file',
                        'level': 'info',
                        'format': 'text',
                        'destination': '/tmp/test.log',
                        'events': ['*']
                    }
                ]
            }
        }

        overlord = Overlord()
        overlord.formation_config = formation_config

        # Mock secret interpolation
        async def mock_interpolate_secrets(config):
            return config

        overlord.interpolate_secrets = mock_interpolate_secrets

        await overlord._initialize_logging_config()

        # Verify that the logging config was stored
        assert hasattr(overlord, '_logging_config')
        assert overlord._logging_config['enabled'] is True
        assert len(overlord._logging_config['streams']) == 2

        # Check first stream (stdout)
        stdout_stream = overlord._logging_config['streams'][0]
        assert stdout_stream['transport'] == 'stdout'
        assert stdout_stream['level'] == 'debug'
        assert stdout_stream['format'] == 'jsonl'

        # Check second stream (file)
        file_stream = overlord._logging_config['streams'][1]
        assert file_stream['transport'] == 'file'
        assert file_stream['level'] == 'info'
        assert file_stream['format'] == 'text'
        assert file_stream['destination'] == '/tmp/test.log'

    @pytest.mark.asyncio
    async def test_logging_config_protocol_detection(self):
        """Test that protocol detection works correctly"""
        overlord = Overlord()

        # Test webhook protocol detection
        webhook_url = 'https://webhook.example.com/logs'
        webhook_protocol = overlord._detect_stream_protocol(webhook_url)
        assert webhook_protocol == 'webhook'

        # Test ZMQ protocol detection
        zmq_protocol = overlord._detect_stream_protocol('tcp://server:8000/ingest')
        assert zmq_protocol == 'zmq'

        # Test WebSocket protocol detection
        ws_protocol = overlord._detect_stream_protocol('wss://websocket.example.com/logs')
        assert ws_protocol == 'websocket'

        # Test default fallback
        default_protocol = overlord._detect_stream_protocol('unknown://protocol')
        assert default_protocol == 'zmq'

    @pytest.mark.asyncio
    async def test_no_logging_config(self):
        """Test that overlord handles missing logging configuration gracefully"""
        formation_config = {
            'schema': '1.0.0',
            'id': 'test-formation',
            'description': 'Test formation without logging config'
            # No 'logging' section
        }

        overlord = Overlord()
        overlord.formation_config = formation_config

        # This should not raise an exception
        await overlord._initialize_logging_config()

        # Verify that no logging config was stored
        assert not hasattr(overlord, '_logging_config')

    @pytest.mark.asyncio
    async def test_disabled_logging(self):
        """Test disabled logging configuration"""
        formation_config = {
            'logging': {
                'enabled': False,
                'streams': [
                    {
                        'transport': 'stdout',
                        'level': 'info',
                        'format': 'jsonl'
                    }
                ]
            }
        }

        overlord = Overlord()
        overlord.formation_config = formation_config

        await overlord._initialize_logging_config()

        # Config should not be processed when disabled
        assert not hasattr(overlord, '_logging_config')

    @pytest.mark.asyncio
    async def test_trail_transport_processing(self):
        """Test MUXI trail transport processing"""
        formation_config = {
            'logging': {
                'enabled': True,
                'streams': [
                    {
                        'transport': 'trail',
                        'auth': {
                            'type': 'bearer',
                            'token': '${{ secrets.TRAIL_TOKEN }}'
                        }
                    }
                ]
            }
        }

        overlord = Overlord()
        overlord.formation_config = formation_config

        # Mock secret interpolation
        async def mock_interpolate_secrets(config):
            if config.get('token') == '${{ secrets.TRAIL_TOKEN }}':
                return {'type': 'bearer', 'token': 'interpolated_token'}
            return config

        overlord.interpolate_secrets = mock_interpolate_secrets

        await overlord._initialize_logging_config()

        # Verify trail-specific processing
        assert hasattr(overlord, '_logging_config')
        trail_stream = overlord._logging_config['streams'][0]
        assert trail_stream['transport'] == 'trail'
        assert trail_stream['destination'] == 'tcps://trail.muxi.ai/ingest'
        assert trail_stream['protocol'] == 'zmq'
        assert trail_stream['format'] == 'msgpack'
        assert trail_stream['auth']['token'] == 'interpolated_token'


if __name__ == '__main__':
    pytest.main([__file__])
