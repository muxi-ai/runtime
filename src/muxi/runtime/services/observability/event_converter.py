"""
Bidirectional JSON-Protobuf Event Converter
Implements conversion between JSON observability events and protobuf messages.
"""

from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from .proto import observability_pb2
    from google.protobuf import struct_pb2
else:
    observability_pb2 = None
    struct_pb2 = None

try:
    from .proto import observability_pb2  # type: ignore[misc]
    from google.protobuf import struct_pb2  # type: ignore[misc]
    PROTOBUF_AVAILABLE = True
except ImportError:
    PROTOBUF_AVAILABLE = False


class ConversionError(Exception):
    """Error during JSON-Protobuf conversion"""
    pass


class ObservabilityEventConverter:
    """
    Converts between JSON observability events and protobuf messages.

    Provides bidirectional conversion with proper type mapping and data preservation.
    """

    def __init__(self):
        if not PROTOBUF_AVAILABLE:
            raise ConversionError(
                "Protobuf modules not available. Run protobuf code generation first."
            )

        self.event_type_mapping = self._build_event_type_mapping()
        self.level_mapping = self._build_level_mapping()
        self.reverse_event_type_mapping = {
            v: k for k, v in self.event_type_mapping.items()
        }
        self.reverse_level_mapping = {
            v: k for k, v in self.level_mapping.items()
        }

    def _build_event_type_mapping(self) -> Dict[str, int]:
        """Build mapping from string event types to protobuf enum values"""
        if not observability_pb2:
            return {}

        return {
            # System Events
            'SYSTEM_STARTUP': observability_pb2.SYSTEM_STARTUP,
            'SYSTEM_SHUTDOWN': observability_pb2.SYSTEM_SHUTDOWN,
            'SYSTEM_ERROR': observability_pb2.SYSTEM_ERROR,
            'SYSTEM_HEALTH_CHECK': observability_pb2.SYSTEM_HEALTH_CHECK,

            # Conversation Events
            'CONVERSATION_STARTED': observability_pb2.CONVERSATION_STARTED,
            'CONVERSATION_MESSAGE': observability_pb2.CONVERSATION_MESSAGE,
            'CONVERSATION_COMPLETED': observability_pb2.CONVERSATION_COMPLETED,
            'CONVERSATION_ERROR': observability_pb2.CONVERSATION_ERROR,

            # MCP Events
            'MCP_TOOL_CALL': observability_pb2.MCP_TOOL_CALL,
            'MCP_TOOL_RESULT': observability_pb2.MCP_TOOL_RESULT,
            'MCP_CONNECTION_ERROR': observability_pb2.MCP_CONNECTION_ERROR,
            'MCP_TIMEOUT': observability_pb2.MCP_TIMEOUT,

            # Memory Events
            'MEMORY_STORE': observability_pb2.MEMORY_STORE,
            'MEMORY_RETRIEVE': observability_pb2.MEMORY_RETRIEVE,
            'MEMORY_CLEANUP': observability_pb2.MEMORY_CLEANUP,
            'MEMORY_ERROR': observability_pb2.MEMORY_ERROR,

            # A2A Events
            'A2A_REQUEST': observability_pb2.A2A_REQUEST,
            'A2A_RESPONSE': observability_pb2.A2A_RESPONSE,
            'A2A_DISCOVERY': observability_pb2.A2A_DISCOVERY,
            'A2A_ERROR': observability_pb2.A2A_ERROR,

            # Performance Events
            'PERFORMANCE_METRIC': observability_pb2.PERFORMANCE_METRIC,
            'PERFORMANCE_ALERT': observability_pb2.PERFORMANCE_ALERT,
        }

    def _build_level_mapping(self) -> Dict[str, int]:
        """Build mapping from string levels to protobuf enum values"""
        if not observability_pb2:
            return {}

        return {
            'DEBUG': observability_pb2.DEBUG,
            'INFO': observability_pb2.INFO,
            'WARNING': observability_pb2.WARNING,
            'ERROR': observability_pb2.ERROR,
        }

    def json_to_protobuf(
        self, json_event: Dict[str, Any]
    ) -> observability_pb2.ObservabilityEvent:
        """
        Convert JSON event to protobuf message.

        Args:
            json_event: Dictionary containing event data

        Returns:
            ObservabilityEvent protobuf message

        Raises:
            ConversionError: If conversion fails
        """
        try:
            if not observability_pb2:
                raise ConversionError("Protobuf module not available")
            pb_event = observability_pb2.ObservabilityEvent()

            # Core fields
            pb_event.id = json_event["id"]

            # Convert timestamp
            timestamp_ms = json_event["timestamp"]
            pb_event.timestamp.FromMilliseconds(int(timestamp_ms))

            # Map event level
            level_str = json_event["level"]
            if level_str not in self.level_mapping:
                raise ConversionError(f"Unknown event level: {level_str}")
            pb_event.level = self.level_mapping[level_str]

            pb_event.muxi_version = json_event["muxi_version"]
            pb_event.server = json_event["server"]

            # Map event type
            event_type_str = json_event["event"]
            if event_type_str not in self.event_type_mapping:
                raise ConversionError(f"Unknown event type: {event_type_str}")
            pb_event.event_type = self.event_type_mapping[event_type_str]

            # Optional fields
            if "parent_event_id" in json_event and json_event["parent_event_id"]:
                pb_event.parent_event_id = json_event["parent_event_id"]

            if "request" in json_event and json_event["request"]:
                pb_event.request.CopyFrom(
                    self._convert_request_context(json_event["request"])
                )

            if "data" in json_event and json_event["data"]:
                pb_event.data.CopyFrom(
                    self._convert_event_data(json_event["data"], event_type_str)
                )

            return pb_event

        except Exception as e:
            raise ConversionError(f"Failed to convert JSON to protobuf: {e}")

    def protobuf_to_json(
        self, pb_event: observability_pb2.ObservabilityEvent
    ) -> Dict[str, Any]:
        """
        Convert protobuf message to JSON event.

        Args:
            pb_event: ObservabilityEvent protobuf message

        Returns:
            Dictionary containing event data

        Raises:
            ConversionError: If conversion fails
        """
        try:
            json_event = {
                "id": pb_event.id,
                "timestamp": pb_event.timestamp.ToMilliseconds(),
                "level": self._reverse_map_level(pb_event.level),
                "muxi_version": pb_event.muxi_version,
                "server": pb_event.server,
                "event": self._reverse_map_event_type(pb_event.event_type),
            }

            # Optional fields
            if pb_event.HasField("parent_event_id"):
                json_event["parent_event_id"] = pb_event.parent_event_id

            if pb_event.HasField("request"):
                json_event["request"] = self._convert_request_to_json(
                    pb_event.request
                )

            if pb_event.HasField("data"):
                json_event["data"] = self._convert_data_to_json(pb_event.data)

            return json_event

        except Exception as e:
            raise ConversionError(f"Failed to convert protobuf to JSON: {e}")

    def _convert_request_context(
        self, json_request: Dict[str, Any]
    ) -> observability_pb2.RequestContext:
        """Convert JSON request context to protobuf"""
        if not observability_pb2:
            raise ConversionError("Protobuf module not available")
        pb_request = observability_pb2.RequestContext()

        pb_request.id = json_request["id"]
        pb_request.status = json_request["status"]

        if "started" in json_request:
            pb_request.started = int(json_request["started"])

        if "duration_ms" in json_request:
            pb_request.duration_ms = int(json_request["duration_ms"])

        if "formation_id" in json_request and json_request["formation_id"]:
            pb_request.formation_id = json_request["formation_id"]

        if "user_id" in json_request and json_request["user_id"]:
            pb_request.user_id = json_request["user_id"]

        if "tokens" in json_request and json_request["tokens"]:
            pb_request.tokens.CopyFrom(
                self._convert_token_usage(json_request["tokens"])
            )

        return pb_request

    def _convert_token_usage(
        self, json_tokens: Dict[str, Any]
    ) -> observability_pb2.TokenUsage:
        """Convert JSON token usage to protobuf"""
        if not observability_pb2:
            raise ConversionError("Protobuf module not available")
        pb_tokens = observability_pb2.TokenUsage()

        pb_tokens.total = int(json_tokens["total"])

        if "breakdown" in json_tokens and json_tokens["breakdown"]:
            breakdown = json_tokens["breakdown"]
            model = breakdown.get("model", "")

            # Detect provider type and use appropriate breakdown
            if "gpt" in model.lower() or "openai" in model.lower():
                # OpenAI breakdown
                openai_breakdown = observability_pb2.OpenAITokenBreakdown()
                openai_breakdown.prompt_tokens = int(
                    breakdown.get("prompt_tokens", breakdown.get("input", 0))
                )
                openai_breakdown.completion_tokens = int(
                    breakdown.get("completion_tokens", breakdown.get("output", 0))
                )
                openai_breakdown.model = model
                if "cached_tokens" in breakdown:
                    openai_breakdown.cached_tokens = int(breakdown["cached_tokens"])
                pb_tokens.openai.CopyFrom(openai_breakdown)

            elif "claude" in model.lower() or "anthropic" in model.lower():
                # Anthropic breakdown
                anthropic_breakdown = observability_pb2.AnthropicTokenBreakdown()
                anthropic_breakdown.input_tokens = int(
                    breakdown.get("input_tokens", breakdown.get("input", 0))
                )
                anthropic_breakdown.output_tokens = int(
                    breakdown.get("output_tokens", breakdown.get("output", 0))
                )
                anthropic_breakdown.model = model
                if "cache_creation_input_tokens" in breakdown:
                    anthropic_breakdown.cache_creation_input_tokens = int(
                        breakdown["cache_creation_input_tokens"]
                    )
                if "cache_read_input_tokens" in breakdown:
                    anthropic_breakdown.cache_read_input_tokens = int(
                        breakdown["cache_read_input_tokens"]
                    )
                pb_tokens.anthropic.CopyFrom(anthropic_breakdown)

            else:
                # Generic breakdown
                generic_breakdown = observability_pb2.GenericTokenBreakdown()
                generic_breakdown.input_tokens = int(
                    breakdown.get("input_tokens", breakdown.get("input", 0))
                )
                generic_breakdown.output_tokens = int(
                    breakdown.get("output_tokens", breakdown.get("output", 0))
                )
                generic_breakdown.model = model

                # Add any additional metrics
                additional_metrics = {}
                for key, value in breakdown.items():
                    if key not in [
                        "input_tokens", "output_tokens", "input", "output", "model"
                    ]:
                        additional_metrics[key] = value

                if additional_metrics:
                    self._dict_to_struct(
                        additional_metrics, generic_breakdown.additional_metrics
                    )

                pb_tokens.generic.CopyFrom(generic_breakdown)

        return pb_tokens

    def _convert_event_data(
        self, json_data: Dict[str, Any], event_type: str
    ) -> observability_pb2.EventData:
        """Convert JSON event data to protobuf based on event type"""
        if not observability_pb2:
            raise ConversionError("Protobuf module not available")
        pb_data = observability_pb2.EventData()

        if "description" in json_data:
            pb_data.description = json_data["description"]

        # Route to appropriate typed payload based on event type
        if event_type.startswith("CONVERSATION_"):
            conversation_data = observability_pb2.ConversationEventData()

            if "user_message" in json_data:
                conversation_data.user_message = json_data["user_message"]
            if "agent_response" in json_data:
                conversation_data.agent_response = json_data["agent_response"]
            if "agent_id" in json_data:
                conversation_data.agent_id = json_data["agent_id"]
            if "session_id" in json_data:
                conversation_data.session_id = json_data["session_id"]
            if "tool_calls" in json_data and isinstance(
                json_data["tool_calls"], list
            ):
                conversation_data.tool_calls[:] = json_data["tool_calls"]
            if "response_time_ms" in json_data:
                conversation_data.response_time_ms = int(
                    json_data["response_time_ms"]
                )

            pb_data.conversation.CopyFrom(conversation_data)

        elif event_type.startswith("SYSTEM_"):
            system_data = observability_pb2.SystemEventData()

            if "component" in json_data:
                system_data.component = json_data["component"]
            if "version" in json_data:
                system_data.version = json_data["version"]
            if "error_message" in json_data:
                system_data.error_message = json_data["error_message"]
            if "exit_code" in json_data:
                system_data.exit_code = int(json_data["exit_code"])
            if "metrics" in json_data:
                self._dict_to_struct(json_data["metrics"], system_data.metrics)

            pb_data.system.CopyFrom(system_data)

        elif event_type.startswith("MCP_"):
            mcp_data = observability_pb2.MCPEventData()

            if "server_id" in json_data:
                mcp_data.server_id = json_data["server_id"]
            if "tool_name" in json_data:
                mcp_data.tool_name = json_data["tool_name"]
            if "parameters" in json_data:
                self._dict_to_struct(json_data["parameters"], mcp_data.parameters)
            if "result" in json_data:
                self._dict_to_struct(json_data["result"], mcp_data.result)
            if "error_message" in json_data:
                mcp_data.error_message = json_data["error_message"]
            if "execution_time_ms" in json_data:
                mcp_data.execution_time_ms = int(
                    json_data["execution_time_ms"]
                )

            pb_data.mcp.CopyFrom(mcp_data)

        else:
            # Fallback to flexible Struct for unknown data
            self._dict_to_struct(json_data, pb_data.custom)

        return pb_data

    def _dict_to_struct(self, data: Dict[str, Any], struct: "struct_pb2.Struct"):
        """Convert dictionary to protobuf Struct"""
        struct.Clear()
        for key, value in data.items():
            struct.fields[key].CopyFrom(self._value_to_protobuf_value(value))

    def _value_to_protobuf_value(self, value: Any) -> "struct_pb2.Value":
        """Convert Python value to protobuf Value"""
        if not struct_pb2:
            raise ConversionError("Protobuf struct module not available")
        pb_value = struct_pb2.Value()

        if value is None:
            pb_value.null_value = struct_pb2.NULL_VALUE
        elif isinstance(value, bool):
            pb_value.bool_value = value
        elif isinstance(value, (int, float)):
            pb_value.number_value = float(value)
        elif isinstance(value, str):
            pb_value.string_value = value
        elif isinstance(value, list):
            for item in value:
                pb_value.list_value.values.append(self._value_to_protobuf_value(item))
        elif isinstance(value, dict):
            self._dict_to_struct(value, pb_value.struct_value)
        else:
            # Convert to string as fallback
            pb_value.string_value = str(value)

        return pb_value

    def _convert_request_to_json(
        self, pb_request: observability_pb2.RequestContext
    ) -> Dict[str, Any]:
        """Convert protobuf request context to JSON"""
        json_request = {
            "id": pb_request.id,
            "status": pb_request.status,
        }

        if pb_request.started:
            json_request["started"] = pb_request.started

        if pb_request.duration_ms:
            json_request["duration_ms"] = pb_request.duration_ms

        if pb_request.HasField("formation_id"):
            json_request["formation_id"] = pb_request.formation_id

        if pb_request.HasField("user_id"):
            json_request["user_id"] = pb_request.user_id

        if pb_request.HasField("tokens"):
            json_request["tokens"] = self._convert_tokens_to_json(
                pb_request.tokens
            )

        return json_request

    def _convert_tokens_to_json(
        self, pb_tokens: observability_pb2.TokenUsage
    ) -> Dict[str, Any]:
        """Convert protobuf token usage to JSON"""
        json_tokens = {"total": pb_tokens.total}

        breakdown = {}

        # Check which breakdown type is used
        if pb_tokens.HasField("openai"):
            openai = pb_tokens.openai
            breakdown = {
                "prompt_tokens": openai.prompt_tokens,
                "completion_tokens": openai.completion_tokens,
                "model": openai.model,
            }
            if openai.HasField("cached_tokens"):
                breakdown["cached_tokens"] = openai.cached_tokens

        elif pb_tokens.HasField("anthropic"):
            anthropic = pb_tokens.anthropic
            breakdown = {
                "input_tokens": anthropic.input_tokens,
                "output_tokens": anthropic.output_tokens,
                "model": anthropic.model,
            }
            if anthropic.HasField("cache_creation_input_tokens"):
                breakdown["cache_creation_input_tokens"] = (
                    anthropic.cache_creation_input_tokens
                )
            if anthropic.HasField("cache_read_input_tokens"):
                breakdown["cache_read_input_tokens"] = (
                    anthropic.cache_read_input_tokens
                )

        elif pb_tokens.HasField("generic"):
            generic = pb_tokens.generic
            breakdown = {
                "input_tokens": generic.input_tokens,
                "output_tokens": generic.output_tokens,
                "model": generic.model,
            }
            if generic.HasField("additional_metrics"):
                additional = self._struct_to_dict(generic.additional_metrics)
                breakdown.update(additional)

        if breakdown:
            json_tokens["breakdown"] = breakdown

        return json_tokens

    def _convert_data_to_json(
        self, pb_data: observability_pb2.EventData
    ) -> Dict[str, Any]:
        """Convert protobuf event data to JSON"""
        json_data = {}

        if pb_data.HasField("description"):
            json_data["description"] = pb_data.description

        # Check which payload type is used
        if pb_data.HasField("conversation"):
            conv = pb_data.conversation
            if conv.user_message:
                json_data["user_message"] = conv.user_message
            if conv.HasField("agent_response"):
                json_data["agent_response"] = conv.agent_response
            if conv.HasField("agent_id"):
                json_data["agent_id"] = conv.agent_id
            if conv.HasField("session_id"):
                json_data["session_id"] = conv.session_id
            if conv.tool_calls:
                json_data["tool_calls"] = list(conv.tool_calls)
            if conv.HasField("response_time_ms"):
                json_data["response_time_ms"] = conv.response_time_ms

        elif pb_data.HasField("system"):
            sys = pb_data.system
            if sys.component:
                json_data["component"] = sys.component
            if sys.HasField("version"):
                json_data["version"] = sys.version
            if sys.HasField("error_message"):
                json_data["error_message"] = sys.error_message
            if sys.HasField("exit_code"):
                json_data["exit_code"] = sys.exit_code
            if sys.HasField("metrics"):
                json_data["metrics"] = self._struct_to_dict(sys.metrics)

        elif pb_data.HasField("mcp"):
            mcp = pb_data.mcp
            if mcp.server_id:
                json_data["server_id"] = mcp.server_id
            if mcp.tool_name:
                json_data["tool_name"] = mcp.tool_name
            if mcp.HasField("parameters"):
                json_data["parameters"] = self._struct_to_dict(mcp.parameters)
            if mcp.HasField("result"):
                json_data["result"] = self._struct_to_dict(mcp.result)
            if mcp.HasField("error_message"):
                json_data["error_message"] = mcp.error_message
            if mcp.HasField("execution_time_ms"):
                json_data["execution_time_ms"] = mcp.execution_time_ms

        elif pb_data.HasField("custom"):
            json_data.update(self._struct_to_dict(pb_data.custom))

        return json_data

    def _struct_to_dict(self, struct: "struct_pb2.Struct") -> Dict[str, Any]:
        """Convert protobuf Struct to dictionary"""
        result = {}
        for key, value in struct.fields.items():
            result[key] = self._protobuf_value_to_python(value)
        return result

    def _protobuf_value_to_python(self, value: "struct_pb2.Value") -> Any:
        """Convert protobuf Value to Python value"""
        kind = value.WhichOneof("kind")

        if kind == "null_value":
            return None
        elif kind == "bool_value":
            return value.bool_value
        elif kind == "number_value":
            # Try to preserve integer types when possible
            if value.number_value.is_integer():
                return int(value.number_value)
            return value.number_value
        elif kind == "string_value":
            return value.string_value
        elif kind == "list_value":
            return [
                self._protobuf_value_to_python(item)
                for item in value.list_value.values
            ]
        elif kind == "struct_value":
            return self._struct_to_dict(value.struct_value)
        else:
            return None

    def _reverse_map_level(self, level: int) -> str:
        """Reverse map protobuf level enum to string"""
        if level not in self.reverse_level_mapping:
            raise ConversionError(f"Unknown level enum: {level}")
        return self.reverse_level_mapping[level]

    def _reverse_map_event_type(self, event_type: int) -> str:
        """Reverse map protobuf event type enum to string"""
        if event_type not in self.reverse_event_type_mapping:
            raise ConversionError(f"Unknown event type enum: {event_type}")
        return self.reverse_event_type_mapping[event_type]
