"""
Protobuf Schema Management and Validation Framework
Implements schema validation and JSON compatibility checking for observability events.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime


# Using built-in ValueError for validation errors
class ValidationError(ValueError):
    """Error raised when validation fails"""
    pass


def find_project_root(start_path: Optional[Path] = None) -> Path:
    """
    Find the project root directory by looking for common project markers.

    Args:
        start_path: Starting directory for search (defaults to current file's directory)

    Returns:
        Path to the project root directory

    Raises:
        ValidationError: If project root cannot be found
    """
    if start_path is None:
        start_path = Path(__file__).parent

    current = start_path.resolve()

    # Look for common project root markers
    root_markers = [
        'pyproject.toml',
        'setup.py',
        '.git',
        'runtime',  # Our specific project structure
        'schemas'   # Look for schemas directory directly
    ]

    # Search up the directory tree
    for _ in range(10):  # Limit search depth to avoid infinite loops
        for marker in root_markers:
            marker_path = current / marker
            if marker_path.exists():
                # If we found schemas directory, we're at project root
                if marker == 'schemas':
                    return current
                # If we found other markers, check if schemas exists at this level
                schemas_path = current / 'schemas' / 'protobuf'
                if schemas_path.exists():
                    return current

        # Move up one level
        parent = current.parent
        if parent == current:  # Reached filesystem root
            break
        current = parent

    # Fallback: check environment variable
    if 'MUXI_PROJECT_ROOT' in os.environ:
        env_root = Path(os.environ['MUXI_PROJECT_ROOT'])
        if env_root.exists() and (env_root / 'schemas' / 'protobuf').exists():
            return env_root

    # If all else fails, raise an error with helpful message
    raise ValidationError(
        f"Could not find project root starting from {start_path}. "
        f"Please ensure you're running from within the project directory, "
        f"or set the MUXI_PROJECT_ROOT environment variable."
    )


@dataclass
class ValidationResult:
    """Result of schema validation operation"""
    valid: bool
    issues: List[str]
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class ProtobufSchemaManager:
    """
    Manages protobuf schemas and validates JSON event compatibility.

    This class provides validation capabilities to ensure JSON events
    can be successfully converted to protobuf messages without data loss.
    """

    def __init__(self, schema_path: Optional[str] = None):
        self.schema_path = Path(schema_path) if schema_path else self._get_default_schema_path()
        self.schemas = {}
        self.validators = {}
        self._load_schemas()
        self._create_validators()

    def _get_default_schema_path(self) -> Path:
        """
        Get default path to protobuf schemas using robust project root detection.

        Returns:
            Path to the schemas/protobuf directory
        """
        try:
            project_root = find_project_root()
            return project_root / "schemas" / "protobuf"
        except ValidationError as e:
            # Provide a more specific error message for schema loading
            raise ValidationError(
                f"Cannot locate protobuf schemas: {e}. "
                f"Ensure you're running from the project directory or set MUXI_PROJECT_ROOT."
            )

    def _load_schemas(self):
        """Load all protobuf schema definitions"""
        if not self.schema_path.exists():
            raise ValidationError(f"Schema path does not exist: {self.schema_path}")

        # For now, we track the main observability schema
        observability_proto = self.schema_path / "observability.proto"
        if observability_proto.exists():
            self.schemas["observability"] = str(observability_proto)

    def _create_validators(self):
        """Create validation rules for different event types"""
        self.validators = {
            "required_fields": self._validate_required_fields,
            "field_types": self._validate_field_types,
            "event_types": self._validate_event_types,
            "data_compatibility": self._validate_data_compatibility,
            "timestamp_format": self._validate_timestamp_format,
            "token_structure": self._validate_token_structure
        }

    def validate_json_compatibility(self, json_event: Dict[str, Any]) -> ValidationResult:
        """
        Ensure JSON events can be converted to protobuf without data loss.

        Args:
            json_event: The JSON event data to validate

        Returns:
            ValidationResult with validation status and any issues found
        """
        issues = []
        warnings = []

        # Run all validation checks
        for validator_name, validator_func in self.validators.items():
            try:
                result = validator_func(json_event)
                if result and hasattr(result, 'issues'):
                    issues.extend(result.issues)
                if result and hasattr(result, 'warnings'):
                    warnings.extend(result.warnings)
            except Exception as e:
                issues.append(f"Validator {validator_name} failed: {str(e)}")

        return ValidationResult(
            valid=len(issues) == 0,
            issues=issues,
            warnings=warnings
        )

    def _validate_required_fields(self, json_event: Dict[str, Any]) -> ValidationResult:
        """Validate that all required fields are present"""
        issues = []

        # Core required fields for ObservabilityEvent
        required_fields = ['id', 'timestamp', 'level', 'muxi_version', 'server', 'event']

        for field in required_fields:
            if field not in json_event:
                issues.append(f"Missing required field: {field}")
            elif json_event[field] is None:
                issues.append(f"Required field cannot be null: {field}")
            elif isinstance(json_event[field], str) and not json_event[field].strip():
                issues.append(f"Required field cannot be empty: {field}")

        return ValidationResult(valid=len(issues) == 0, issues=issues)

    def _validate_field_types(self, json_event: Dict[str, Any]) -> ValidationResult:
        """Validate field type compatibility with protobuf"""
        issues = []
        warnings = []

        # Define expected types for core fields
        expected_types = {
            'id': str,
            'timestamp': (int, float),  # Unix timestamp in milliseconds
            'level': str,
            'muxi_version': str,
            'server': str,
            'event': str,
            'parent_event_id': str,
        }

        for field, expected_type in expected_types.items():
            if field in json_event:
                value = json_event[field]
                if value is not None:
                    if isinstance(expected_type, tuple):
                        if not isinstance(value, expected_type):
                            issues.append(f"Field '{field}' must be one of {expected_type}, got {type(value)}")
                    else:
                        if not isinstance(value, expected_type):
                            issues.append(f"Field '{field}' must be {expected_type}, got {type(value)}")

        # Validate nested structures
        if 'request' in json_event and json_event['request'] is not None:
            request_issues = self._validate_request_context(json_event['request'])
            issues.extend(request_issues)

        return ValidationResult(valid=len(issues) == 0, issues=issues, warnings=warnings)

    def _validate_event_types(self, json_event: Dict[str, Any]) -> ValidationResult:
        """Validate event type enumeration compatibility"""
        issues = []
        warnings = []

        if 'event' not in json_event:
            return ValidationResult(valid=True, issues=[], warnings=[])

        event_type = json_event['event']

        # Define valid event types based on our protobuf schema
        valid_event_types = {
            # System Events
            'SYSTEM_STARTUP', 'SYSTEM_SHUTDOWN', 'SYSTEM_ERROR', 'SYSTEM_HEALTH_CHECK',
            # Conversation Events
            'CONVERSATION_STARTED', 'CONVERSATION_MESSAGE', 'CONVERSATION_COMPLETED', 'CONVERSATION_ERROR',
            # MCP Events
            'MCP_TOOL_CALL', 'MCP_TOOL_RESULT', 'MCP_CONNECTION_ERROR', 'MCP_TIMEOUT',
            # Memory Events
            'MEMORY_STORE', 'MEMORY_RETRIEVE', 'MEMORY_CLEANUP', 'MEMORY_ERROR',
            # A2A Events
            'A2A_REQUEST', 'A2A_RESPONSE', 'A2A_DISCOVERY', 'A2A_ERROR',
            # Performance Events
            'PERFORMANCE_METRIC', 'PERFORMANCE_ALERT'
        }

        if event_type not in valid_event_types:
            warnings.append(f"Event type '{event_type}' not in known types, will use custom payload")

        return ValidationResult(valid=True, issues=issues, warnings=warnings)

    def _validate_data_compatibility(self, json_event: Dict[str, Any]) -> ValidationResult:
        """Validate data field structure for protobuf compatibility"""
        issues = []
        warnings = []

        if 'data' not in json_event or json_event['data'] is None:
            return ValidationResult(valid=True, issues=[], warnings=[])

        data = json_event['data']

        if not isinstance(data, dict):
            issues.append("Data field must be a dictionary/object")
            return ValidationResult(valid=False, issues=issues)

        # Check for complex nested structures that might cause issues
        max_depth = self._get_dict_depth(data)
        if max_depth > 10:
            warnings.append(f"Data structure is deeply nested (depth: {max_depth}), may impact performance")

        # Check for very large data payloads
        data_str = json.dumps(data)
        if len(data_str) > 1024 * 1024:  # 1MB
            warnings.append(f"Data payload is large ({len(data_str)} bytes), may impact performance")

        return ValidationResult(valid=len(issues) == 0, issues=issues, warnings=warnings)

    def _validate_timestamp_format(self, json_event: Dict[str, Any]) -> ValidationResult:
        """Validate timestamp format for protobuf compatibility"""
        issues = []

        if 'timestamp' not in json_event:
            return ValidationResult(valid=True, issues=[])

        timestamp = json_event['timestamp']

        # Check if timestamp is in milliseconds (reasonable range)
        current_time_ms = int(datetime.now().timestamp() * 1000)
        min_time_ms = 1000000000000  # ~2001
        max_time_ms = current_time_ms + (365 * 24 * 60 * 60 * 1000)  # +1 year

        if not isinstance(timestamp, (int, float)):
            issues.append("Timestamp must be numeric")
        elif timestamp < min_time_ms or timestamp > max_time_ms:
            issues.append(f"Timestamp {timestamp} appears to be outside reasonable range")

        return ValidationResult(valid=len(issues) == 0, issues=issues)

    def _validate_token_structure(self, json_event: Dict[str, Any]) -> ValidationResult:
        """Validate token usage structure for protobuf compatibility"""
        issues = []
        warnings = []

        if 'request' not in json_event or not json_event['request']:
            return ValidationResult(valid=True, issues=[], warnings=[])

        request = json_event['request']
        if 'tokens' not in request or not request['tokens']:
            return ValidationResult(valid=True, issues=[], warnings=[])

        tokens = request['tokens']

        if not isinstance(tokens, dict):
            issues.append("Tokens field must be a dictionary")
            return ValidationResult(valid=False, issues=issues)

        # Check for required total field
        if 'total' not in tokens:
            issues.append("Tokens must include 'total' field")
        elif not isinstance(tokens['total'], (int, float)):
            issues.append("Token total must be numeric")

        # Check breakdown structure
        if 'breakdown' in tokens:
            breakdown = tokens['breakdown']
            if isinstance(breakdown, dict):
                # Check for known provider patterns
                if 'model' in breakdown:
                    model = breakdown['model']
                    if 'gpt' in model.lower() or 'openai' in model.lower():
                        # OpenAI pattern
                        if not any(k in breakdown for k in ['prompt_tokens', 'completion_tokens']):
                            warnings.append("OpenAI model detected but missing expected token fields")
                    elif 'claude' in model.lower() or 'anthropic' in model.lower():
                        # Anthropic pattern
                        if not any(k in breakdown for k in ['input_tokens', 'output_tokens']):
                            warnings.append("Anthropic model detected but missing expected token fields")

        return ValidationResult(valid=len(issues) == 0, issues=issues, warnings=warnings)

    def _validate_request_context(self, request_context: Dict[str, Any]) -> List[str]:
        """Validate request context structure"""
        issues = []

        if not isinstance(request_context, dict):
            issues.append("Request context must be a dictionary")
            return issues

        # Check required fields
        required_request_fields = ['id', 'status']
        for field in required_request_fields:
            if field not in request_context:
                issues.append(f"Missing required request field: {field}")

        # Check field types
        if 'started' in request_context and not isinstance(request_context['started'], (int, float)):
            issues.append("Request 'started' field must be numeric timestamp")

        if 'duration_ms' in request_context and not isinstance(request_context['duration_ms'], (int, float)):
            issues.append("Request 'duration_ms' field must be numeric")

        return issues

    def _get_dict_depth(self, d: Dict[str, Any], depth: int = 1) -> int:
        """Calculate maximum depth of nested dictionary"""
        if not isinstance(d, dict):
            return depth

        max_depth = depth
        for value in d.values():
            if isinstance(value, dict):
                current_depth = self._get_dict_depth(value, depth + 1)
                max_depth = max(max_depth, current_depth)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        current_depth = self._get_dict_depth(item, depth + 1)
                        max_depth = max(max_depth, current_depth)

        return max_depth

    def get_schema_info(self) -> Dict[str, Any]:
        """Get information about loaded schemas"""
        return {
            "schema_path": str(self.schema_path),
            "loaded_schemas": list(self.schemas.keys()),
            "validators": list(self.validators.keys()),
            "schema_files": [f.name for f in self.schema_path.glob("*.proto")] if self.schema_path.exists() else []
        }
