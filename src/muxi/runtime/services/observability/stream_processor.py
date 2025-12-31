import asyncio
from typing import Dict, Any, List, Optional
from .transports.base import BaseTransport, TransportStatus
from .health import HealthManager


class StreamProcessor:
    def __init__(self):
        self.transports: Dict[str, BaseTransport] = {}
        self.enabled = False
        self.event_queue = asyncio.Queue()
        self.processing_task = None
        self.health_manager = HealthManager()
        self.circuit_breaker_threshold = 3  # Failed attempts before circuit breaker

    async def initialize(self, streams_config: List[Dict[str, Any]]) -> None:
        """Initialize all configured transports."""
        for stream_config in streams_config:
            transport_type = stream_config.get("transport")
            if transport_type:
                transport = await self._create_transport(transport_type, stream_config)
                if transport:
                    transport_id = f"{transport_type}_{len(self.transports)}"
                    self.transports[transport_id] = transport

    async def _create_transport(
        self, transport_type: str, config: Dict[str, Any]
    ) -> Optional[BaseTransport]:
        """Create a transport instance based on type."""
        # Import transport implementations dynamically to avoid circular imports
        try:
            if transport_type == "stdout":
                from .transports.stdout import StdoutTransport

                transport = StdoutTransport(config)
            elif transport_type == "file":
                from .transports.file import FileTransport

                transport = FileTransport(config)
            elif transport_type == "stream":
                from .transports.stream import StreamTransport

                transport = StreamTransport(config)
            elif transport_type == "trail":
                # Trail is a preset that configures stream transport
                from .transports.stream import StreamTransport

                transport = StreamTransport(config)
            else:
                print(f"Unknown transport type: {transport_type}")
                return None

            # Initialize the transport
            if await transport.initialize():
                return transport
            else:
                print(f"Failed to initialize transport: {transport_type}")
                return None

        except ImportError as e:
            print(f"Failed to import transport {transport_type}: {e}")
            return None

    async def emit_event(self, event: Dict[str, Any]) -> None:
        """Queue event for processing."""
        if self.enabled:
            await self.event_queue.put(event)

    async def start(self) -> None:
        """Start event processing."""
        self.enabled = True
        self.processing_task = asyncio.create_task(self._process_events())

    async def stop(self) -> None:
        """Stop event processing."""
        self.enabled = False
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass

        # Close all transports
        for transport in self.transports.values():
            await transport.close()

    async def _process_events(self) -> None:
        """Process events from the queue with circuit breaker logic."""
        while self.enabled:
            try:
                # Wait for an event with timeout to allow periodic checks
                event = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)

                # Get healthy destinations from health manager
                all_destinations = [
                    transport.config.get("destination", f"transport_{transport_id}")
                    for transport_id, transport in self.transports.items()
                ]
                healthy_destinations = await self.health_manager.get_healthy_destinations(
                    all_destinations
                )

                # Send event to healthy transports only
                for transport_id, transport in self.transports.items():
                    destination = transport.config.get("destination", f"transport_{transport_id}")

                    # Circuit breaker: skip unhealthy destinations
                    if destination not in healthy_destinations:
                        continue

                    if transport.enabled and transport.status == TransportStatus.HEALTHY:
                        try:
                            success = await transport.send_event(event)
                            if success:
                                # Reset error count on success
                                transport.error_count = 0
                                # Update health status to healthy (reactive)
                                await self.health_manager.update_destination_health(
                                    destination, True, None
                                )
                            else:
                                # Handle send failure
                                await self._handle_transport_failure(
                                    transport, transport_id, destination, "Send failed"
                                )
                        except Exception as e:
                            # Handle exception
                            await self._handle_transport_failure(
                                transport, transport_id, destination, str(e)
                            )

            except asyncio.TimeoutError:
                # No events to process, continue loop
                continue
            except Exception as e:
                print(f"Error processing events: {e}")

    async def _handle_transport_failure(
        self, transport: BaseTransport, transport_id: str, destination: str, error: str
    ) -> None:
        """Handle transport failure with circuit breaker logic."""
        print(f"Error sending event via {transport_id}: {error}")
        transport.error_count += 1
        transport.last_error = error

        # Circuit breaker: mark as unhealthy after threshold failures
        if transport.error_count >= self.circuit_breaker_threshold:
            transport.status = TransportStatus.FAILED
            # Update health status (reactive)
            await self.health_manager.update_destination_health(
                destination, False, error, preserve_since=True
            )

    async def get_transport_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all transports."""
        status = {}
        for transport_id, transport in self.transports.items():
            status[transport_id] = {
                "enabled": transport.enabled,
                "status": transport.status.value,
                "error_count": transport.error_count,
                "last_error": transport.last_error,
            }
        return status

    async def close(self) -> None:
        """Close the stream processor and clean up resources."""
        self.enabled = False

        # Close all transports
        for transport in self.transports.values():
            try:
                await transport.close()
            except Exception as e:
                # Log error but continue cleanup
                print(f"Error closing transport: {e}")

        self.transports.clear()

    async def configure_streams(self, streams_config: List[Dict[str, Any]]) -> None:
        """
        Configure transports from formation stream configurations.

        Args:
            streams_config: List of processed stream configurations from formation
        """
        from .transports.stdout import StdoutTransport
        from .transports.file import FileTransport
        from .transports.stream import StreamTransport

        for stream_config in streams_config:
            try:
                transport_type = stream_config.get("type", "stdout")
                transport_id = stream_config.get("id", f"{transport_type}_{len(self.transports)}")

                # Create transport based on type
                if transport_type == "stdout":
                    transport = StdoutTransport(stream_config)
                elif transport_type == "file":
                    transport = FileTransport(stream_config)
                elif transport_type in ["stream", "http", "kafka", "zmq"]:
                    transport = StreamTransport(stream_config)
                else:
                    print(f"Unknown transport type: {transport_type}")
                    continue

                # Initialize and register transport
                if await transport.initialize():
                    self.transports[transport_id] = transport
                    print(f"Configured transport: {transport_id} ({transport_type})")
                else:
                    print(f"Failed to initialize transport: {transport_id}")

            except Exception as e:
                print(f"Error configuring stream {stream_config}: {e}")
                continue

    def is_running(self) -> bool:
        """Check if the stream processor is running."""
        return self.enabled
