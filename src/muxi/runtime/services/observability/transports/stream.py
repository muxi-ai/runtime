import asyncio
from typing import Dict, Any, List, Optional
from .base import BaseTransport, TransportStatus

# Optional imports for different protocols
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

try:
    from kafka import KafkaProducer
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

try:
    import zmq
    import zmq.asyncio
    ZMQ_AVAILABLE = True
except ImportError:
    ZMQ_AVAILABLE = False


class StreamTransport(BaseTransport):
    """
    Unified network transport supporting http, kafka, and zmq protocols.
    Handles trail transport as a configuration preset.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.destination = config.get("destination")
        self.protocol = config.get("protocol") or self._detect_protocol()
        self.format_type = config.get("format", "jsonl")
        self.auth_config = config.get("auth", {})
        self.retry_config = config.get("retry", {})
        self.formatter = None

        # Handle trail transport preset
        if config.get("transport") == "trail":
            self._apply_trail_preset(config)

        # Protocol-specific initialization
        self.session: Optional[aiohttp.ClientSession] = None
        self.kafka_producer: Optional[KafkaProducer] = None
        self.zmq_context: Optional[zmq.Context] = None
        self.zmq_socket: Optional[zmq.Socket] = None

    def _apply_trail_preset(self, config: Dict[str, Any]) -> None:
        """Apply MUXI trail transport defaults."""
        self.destination = "tcps://trail.muxi.ai/ingest"
        self.protocol = "zmq"
        self.format_type = "msgpack"
        self.events = ["*"]

        # Convert simplified token to auth config
        if "token" in config:
            self.auth_config = {
                "type": "bearer",
                "token": config["token"]
            }

    def _detect_protocol(self) -> str:
        """Auto-detect protocol from destination URL."""
        if not self.destination:
            return "http"

        if self.destination.startswith(("http://", "https://")):
            return "http"
        elif self.destination.startswith("kafka://"):
            return "kafka"
        elif self.destination.startswith(("tcp://", "tcps://", "ipc://", "ipcs://")):
            return "zmq"
        else:
            return "http"  # Default fallback

    async def initialize(self) -> bool:
        """Initialize transport based on protocol."""
        try:
            # Initialize formatter
            await self._initialize_formatter()

            if self.protocol == "http":
                return await self._initialize_http()
            elif self.protocol == "kafka":
                return await self._initialize_kafka()
            elif self.protocol == "zmq":
                return await self._initialize_zmq()
            else:
                self.last_error = f"Unsupported protocol: {self.protocol}"
                self.status = TransportStatus.FAILED
                return False

        except Exception as e:
            self.last_error = str(e)
            self.status = TransportStatus.FAILED
            return False

    async def _initialize_formatter(self) -> None:
        """Initialize the event formatter."""
        try:
            from ..formatters import create_formatter
            self.formatter = create_formatter(self.format_type, self.config)
        except Exception:
            # Fallback to JSON Lines if formatter fails
            from ..formatters.jsonl import JSONLFormatter
            self.formatter = JSONLFormatter(self.config)

    async def _initialize_http(self) -> bool:
        """Initialize HTTP transport."""
        if not AIOHTTP_AVAILABLE:
            self.last_error = "aiohttp not available for HTTP transport"
            self.status = TransportStatus.FAILED
            return False

        try:
            headers = {"Content-Type": self.formatter.content_type}

            # Add authentication headers
            if self.auth_config.get("type") == "bearer":
                token = self.auth_config.get("token")
                if token:
                    headers["Authorization"] = f"Bearer {token}"
            elif self.auth_config.get("type") == "api_key":
                api_key = self.auth_config.get("api_key")
                if api_key:
                    headers["X-API-Key"] = api_key

            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers=headers
            )

            self.status = TransportStatus.HEALTHY
            return True

        except Exception as e:
            self.last_error = str(e)
            self.status = TransportStatus.FAILED
            return False

    async def _initialize_kafka(self) -> bool:
        """Initialize Kafka transport."""
        if not KAFKA_AVAILABLE:
            self.last_error = "kafka-python not available for Kafka transport"
            self.status = TransportStatus.FAILED
            return False

        try:
            # Parse Kafka brokers from destination
            if self.destination.startswith("kafka://"):
                brokers = self.destination[8:].split(",")
            else:
                brokers = [self.destination]

            # Configure Kafka producer based on format
            if self.format_type in ["msgpack", "protobuf"]:
                # Binary formats
                producer_config = {
                    "bootstrap_servers": brokers,
                    "value_serializer": lambda v: (
                        v if isinstance(v, bytes) else str(v).encode('utf-8')
                    )
                }
            else:
                # Text formats
                producer_config = {
                    "bootstrap_servers": brokers,
                    "value_serializer": lambda v: (
                        v.encode('utf-8') if isinstance(v, str) else v
                    )
                }

            # Add SASL authentication if configured
            if self.auth_config.get("type") == "sasl":
                producer_config.update({
                    "security_protocol": "SASL_PLAINTEXT",
                    "sasl_mechanism": "PLAIN",
                    "sasl_plain_username": self.auth_config.get("username"),
                    "sasl_plain_password": self.auth_config.get("password")
                })

            self.kafka_producer = KafkaProducer(**producer_config)
            self.status = TransportStatus.HEALTHY
            return True

        except Exception as e:
            self.last_error = str(e)
            self.status = TransportStatus.FAILED
            return False

    async def _initialize_zmq(self) -> bool:
        """Initialize ZeroMQ transport."""
        if not ZMQ_AVAILABLE:
            self.last_error = "pyzmq not available for ZMQ transport"
            self.status = TransportStatus.FAILED
            return False

        try:
            self.zmq_context = zmq.asyncio.Context()
            socket_type = self.config.get("socket_type", "push")

            if socket_type.lower() == "push":
                self.zmq_socket = self.zmq_context.socket(zmq.PUSH)
            elif socket_type.lower() == "pub":
                self.zmq_socket = self.zmq_context.socket(zmq.PUB)
            else:
                self.zmq_socket = self.zmq_context.socket(zmq.PUSH)

            self.zmq_socket.connect(self.destination)
            self.status = TransportStatus.HEALTHY
            return True

        except Exception as e:
            self.last_error = str(e)
            self.status = TransportStatus.FAILED
            return False

    async def send_event(self, event: Dict[str, Any]) -> bool:
        """Send single event via configured protocol."""
        return await self._send_with_retry([event])

    async def send_batch(self, events: List[Dict[str, Any]]) -> bool:
        """Send batch of events via configured protocol."""
        return await self._send_with_retry(events)

    async def _send_with_retry(self, events: List[Dict[str, Any]]) -> bool:
        """Send events with retry logic."""
        max_attempts = self.retry_config.get("max_attempts", 3)
        backoff_seconds = self.retry_config.get("backoff_seconds", 2)

        for attempt in range(max_attempts):
            try:
                if self.protocol == "http":
                    success = await self._send_http(events)
                elif self.protocol == "kafka":
                    success = await self._send_kafka(events)
                elif self.protocol == "zmq":
                    success = await self._send_zmq(events)
                else:
                    return False

                if success:
                    self.status = TransportStatus.HEALTHY
                    self.error_count = 0
                    return True

            except Exception as e:
                self.last_error = str(e)
                if attempt < max_attempts - 1:
                    await asyncio.sleep(backoff_seconds * (2 ** attempt))
                    continue

        self.error_count += 1
        if self.error_count > 3:
            self.status = TransportStatus.FAILED
        return False

    async def _send_http(self, events: List[Dict[str, Any]]) -> bool:
        """Send events via HTTP."""
        if not self.session or not self.formatter:
            return False

        try:
            # Format events using the configured formatter
            if len(events) == 1:
                formatted_data = self.formatter.format_event(events[0])
            else:
                formatted_data = self.formatter.format_batch(events)

            # Send as appropriate data type
            if isinstance(formatted_data, bytes):
                async with self.session.post(
                    self.destination,
                    data=formatted_data
                ) as response:
                    return response.status < 400
            else:
                async with self.session.post(
                    self.destination,
                    data=formatted_data
                ) as response:
                    return response.status < 400

        except Exception:
            return False

    async def _send_kafka(self, events: List[Dict[str, Any]]) -> bool:
        """Send events via Kafka."""
        if not self.kafka_producer or not self.formatter:
            return False

        try:
            topic = self.config.get("topic", "muxi-events")

            # Format and send each event
            for event in events:
                formatted_data = self.formatter.format_event(event)
                self.kafka_producer.send(topic, value=formatted_data)

            self.kafka_producer.flush()
            return True

        except Exception:
            return False

    async def _send_zmq(self, events: List[Dict[str, Any]]) -> bool:
        """Send events via ZeroMQ."""
        if not self.zmq_socket or not self.formatter:
            return False

        try:
            for event in events:
                formatted_data = self.formatter.format_event(event)
                if isinstance(formatted_data, str):
                    message = formatted_data.encode('utf-8')
                else:
                    message = formatted_data
                await self.zmq_socket.send(message)
            return True

        except Exception:
            return False

    async def close(self) -> None:
        """Clean up transport resources."""
        try:
            if self.session:
                await self.session.close()
                self.session = None

            if self.kafka_producer:
                self.kafka_producer.close()
                self.kafka_producer = None

            if self.zmq_socket:
                self.zmq_socket.close()
                self.zmq_socket = None

            if self.zmq_context:
                self.zmq_context.term()
                self.zmq_context = None

        except Exception:
            pass
