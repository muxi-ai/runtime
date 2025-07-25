from typing import Dict, Type, Any
from .base import BaseFormatter
from .jsonl import JSONLFormatter
from .text import TextFormatter
from .msgpack import MsgPackFormatter
from .protobuf import ProtobufFormatter
from .datadog import DatadogFormatter
from .splunk import SplunkFormatter
from .elastic import ElasticFormatter
from .grafana import GrafanaLokiFormatter
from .newrelic import NewRelicFormatter
from .opentelemetry import OpenTelemetryFormatter

FORMATTER_REGISTRY: Dict[str, Type[BaseFormatter]] = {
    "jsonl": JSONLFormatter,
    "text": TextFormatter,
    "msgpack": MsgPackFormatter,
    "protobuf": ProtobufFormatter,
    "datadog_json": DatadogFormatter,
    "splunk_hec": SplunkFormatter,
    "elastic_bulk": ElasticFormatter,
    "grafana_loki": GrafanaLokiFormatter,
    "newrelic_json": NewRelicFormatter,
    "opentelemetry": OpenTelemetryFormatter,
}


def create_formatter(format_type: str, config: Dict[str, Any] = None) -> BaseFormatter:
    """Create formatter instance by type."""
    if format_type not in FORMATTER_REGISTRY:
        raise ValueError(f"Unknown formatter type: {format_type}")

    formatter_class = FORMATTER_REGISTRY[format_type]
    return formatter_class(config or {})


__all__ = [
    "BaseFormatter",
    "JSONLFormatter",
    "TextFormatter",
    "MsgPackFormatter",
    "ProtobufFormatter",
    "DatadogFormatter",
    "SplunkFormatter",
    "ElasticFormatter",
    "GrafanaLokiFormatter",
    "NewRelicFormatter",
    "OpenTelemetryFormatter",
    "FORMATTER_REGISTRY",
    "create_formatter"
]
