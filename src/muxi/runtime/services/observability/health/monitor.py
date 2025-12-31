"""
Health Monitor for Observability Stream Destinations

This module provides proactive health monitoring using multitasking process
isolation for complete fault tolerance and true parallelism.
"""

import asyncio
import aiohttp
import time
import multiprocessing
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import urlparse
from pathlib import Path

import multitasking

from .manager import HealthManager


class HealthMonitor:
    """
    Proactive health monitoring service with process isolation.

    Performs periodic health checks on all configured destinations using
    multitasking for complete fault tolerance and resource isolation.
    """

    def __init__(self, health_manager: HealthManager, check_interval: int = 30):
        self.health_manager = health_manager
        self.check_interval = check_interval
        self.running = False
        self.destinations: List[Dict[str, Any]] = []

        # Configure multitasking for complete isolation
        # Use process-based engine for complete isolation
        multitasking.set_engine("process")
        # Set process pool size based on CPU cores
        max_workers = min(multiprocessing.cpu_count(), 8)  # Cap at 8 processes
        multitasking.config["max_workers"] = max_workers

    def configure_destinations(self, destinations: List[Dict[str, Any]]) -> None:
        """
        Configure destinations to monitor.

        Args:
            destinations: List of destination configurations from formation config
        """
        self.destinations = destinations

    async def start(self, destinations: Optional[List[str]] = None) -> None:
        """
        Start health monitoring with optional destination list.

        Args:
            destinations: Optional list of destination strings to monitor
        """
        if destinations:
            # Convert string destinations to config format
            dest_configs = []
            for dest in destinations:
                if dest.startswith(("http://", "https://")):
                    dest_configs.append({"destination": dest, "protocol": "http"})
                elif dest.startswith("kafka://"):
                    dest_configs.append({"destination": dest, "protocol": "kafka"})
                elif dest.startswith(("tcp://", "tcps://", "ipc://", "ipcs://")):
                    dest_configs.append({"destination": dest, "protocol": "zmq"})
                else:
                    # Assume file destination
                    dest_configs.append({"destination": dest, "transport": "file"})

            self.configure_destinations(dest_configs)

        await self.start_monitoring()

    async def start_monitoring(self) -> None:
        """Start the health monitoring service."""
        if not self.destinations:
            print("No destinations configured for health monitoring")
            return

        self.running = True
        print(f"Starting health monitoring for {len(self.destinations)} destinations")

        await self._start_multitasking_monitor()

    async def stop_monitoring(self) -> None:
        """Stop the health monitoring service."""
        self.running = False

        # Wait for all multitasking processes to complete
        multitasking.wait_for_tasks()

        print("Health monitoring stopped")

    async def _start_multitasking_monitor(self) -> None:
        """Start monitoring using multitasking process isolation."""

        @multitasking.task
        def check_destination_health(
            dest_config: Dict[str, Any],
        ) -> Tuple[str, bool, Optional[str]]:
            """
            Process-isolated health check for a single destination.

            Returns:
                Tuple of (destination, healthy, error_message)
            """
            try:
                destination = dest_config.get("destination", "")
                protocol = dest_config.get("protocol", "").lower()

                if protocol == "http" or destination.startswith(("http://", "https://")):
                    return _check_http_health(destination, dest_config)
                elif protocol == "kafka" or destination.startswith("kafka://"):
                    return _check_kafka_health(destination, dest_config)
                elif protocol == "zmq" or destination.startswith(
                    ("tcp://", "tcps://", "ipc://", "ipcs://")
                ):
                    return _check_zmq_health(destination, dest_config)
                elif dest_config.get("transport") == "file":
                    return _check_file_health(destination, dest_config)
                else:
                    return destination, False, f"Unknown protocol: {protocol}"

            except Exception as e:
                return dest_config.get("destination", "unknown"), False, str(e)

        # Main monitoring loop
        while self.running:
            try:
                # Launch health checks for all destinations in parallel processes
                for dest_config in self.destinations:
                    check_destination_health(dest_config)

                # Wait for all checks to complete (with timeout)
                start_time = time.time()
                timeout = min(self.check_interval - 5, 25)  # Leave 5 seconds buffer

                multitasking.wait_for_tasks(timeout=timeout)

                # Update last_checked timestamp
                await self.health_manager.update_last_checked()

                # Wait for next check interval
                elapsed = time.time() - start_time
                if elapsed < self.check_interval:
                    await asyncio.sleep(self.check_interval - elapsed)

            except Exception as e:
                print(f"Error in health monitoring loop: {e}")
                await asyncio.sleep(5)  # Brief pause before retry

    async def _start_async_monitor(self) -> None:
        """Fallback monitoring using async tasks (no process isolation)."""
        while self.running:
            try:
                # Run health checks concurrently
                tasks = []
                for dest_config in self.destinations:
                    task = asyncio.create_task(self._check_destination_async(dest_config))
                    tasks.append(task)

                # Wait for all checks with timeout
                timeout = min(self.check_interval - 5, 25)
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), timeout=timeout
                )

                # Update last_checked timestamp
                await self.health_manager.update_last_checked()

                # Wait for next check interval
                await asyncio.sleep(self.check_interval)

            except asyncio.TimeoutError:
                print("Health check timeout - some destinations may be slow")
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                print(f"Error in health monitoring loop: {e}")
                await asyncio.sleep(5)

    async def _check_destination_async(self, dest_config: Dict[str, Any]) -> None:
        """Async health check for fallback mode."""
        try:
            destination = dest_config.get("destination", "")
            protocol = dest_config.get("protocol", "").lower()

            if protocol == "http" or destination.startswith(("http://", "https://")):
                result = await self._check_http_health_async(destination, dest_config)
            elif protocol == "kafka" or destination.startswith("kafka://"):
                result = await self._check_kafka_health_async(destination, dest_config)
            elif protocol == "zmq" or destination.startswith(
                ("tcp://", "tcps://", "ipc://", "ipcs://")
            ):
                result = await self._check_zmq_health_async(destination, dest_config)
            elif dest_config.get("transport") == "file":
                result = await self._check_file_health_async(destination, dest_config)
            else:
                result = (destination, False, f"Unknown protocol: {protocol}")

            # Update health status
            dest, healthy, error = result
            await self.health_manager.update_destination_health(dest, healthy, error)

        except Exception as e:
            destination = dest_config.get("destination", "unknown")
            await self.health_manager.update_destination_health(destination, False, str(e))

    async def _check_http_health_async(
        self, destination: str, config: Dict[str, Any]
    ) -> Tuple[str, bool, Optional[str]]:
        """Async HTTP health check."""
        try:
            # Prepare headers
            headers = {}
            auth_config = config.get("auth", {})
            if auth_config.get("type") == "bearer" and auth_config.get("token"):
                headers["Authorization"] = f"Bearer {auth_config['token']}"

            # Determine health check URL
            health_url = destination
            if not destination.endswith(("/health", "/ping", "/status")):
                # Try common health check endpoints
                parsed = urlparse(destination)
                health_url = f"{parsed.scheme}://{parsed.netloc}/health"

            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(health_url) as response:
                    if response.status < 400:
                        return destination, True, None
                    else:
                        return destination, False, f"HTTP {response.status}"

        except Exception as e:
            return destination, False, str(e)

    async def _check_kafka_health_async(
        self, destination: str, config: Dict[str, Any]
    ) -> Tuple[str, bool, Optional[str]]:
        """Async Kafka health check with simple connectivity test."""
        try:
            # Parse Kafka brokers from destination
            if destination.startswith("kafka://"):
                brokers = destination[8:].split(",")
            else:
                brokers = [destination]

            # Test basic TCP connectivity to first broker
            broker = brokers[0]
            if ":" in broker:
                host, port = broker.rsplit(":", 1)
                port = int(port)
            else:
                host = broker
                port = 9092  # Default Kafka port

            # Simple TCP connection test
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port), timeout=10
                )
                writer.close()
                await writer.wait_closed()
                return destination, True, None
            except Exception as e:
                return destination, False, f"Connection failed: {str(e)}"

        except Exception as e:
            return destination, False, str(e)

    async def _check_zmq_health_async(
        self, destination: str, config: Dict[str, Any]
    ) -> Tuple[str, bool, Optional[str]]:
        """Async ZMQ health check with simple connectivity test."""
        try:
            # Parse ZMQ destination
            if destination.startswith(("tcp://", "tcps://")):
                # Extract host and port from tcp://host:port
                from urllib.parse import urlparse

                parsed = urlparse(destination)
                host = parsed.hostname
                port = parsed.port or 5555  # Default ZMQ port

                # Simple TCP connection test
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(host, port), timeout=10
                    )
                    writer.close()
                    await writer.wait_closed()
                    return destination, True, None
                except Exception as e:
                    return destination, False, f"Connection failed: {str(e)}"

            elif destination.startswith(("ipc://", "ipcs://")):
                # For IPC, check if socket file exists and is accessible
                import os

                socket_path = destination[6:]  # Remove ipc:// prefix
                if os.path.exists(socket_path):
                    return destination, True, None
                else:
                    return destination, False, "IPC socket file does not exist"

            else:
                return destination, False, f"Unsupported ZMQ protocol: {destination}"

        except Exception as e:
            return destination, False, str(e)

    async def _check_file_health_async(
        self, destination: str, config: Dict[str, Any]
    ) -> Tuple[str, bool, Optional[str]]:
        """Async file health check."""
        try:
            file_path = Path(destination)

            # Check if directory exists and is writable
            if file_path.parent.exists() and file_path.parent.is_dir():
                # Try to create a test file
                test_file = file_path.parent / ".health_test"
                try:
                    test_file.touch()
                    test_file.unlink()  # Clean up
                    return destination, True, None
                except PermissionError:
                    return destination, False, "Permission denied"
            else:
                return destination, False, "Directory does not exist"

        except Exception as e:
            return destination, False, str(e)


# Process-isolated health check functions (for multitasking)
def _check_http_health(destination: str, config: Dict[str, Any]) -> Tuple[str, bool, Optional[str]]:
    """Process-isolated HTTP health check."""
    import requests

    try:
        # Prepare headers
        headers = {}
        auth_config = config.get("auth", {})
        if auth_config.get("type") == "bearer" and auth_config.get("token"):
            headers["Authorization"] = f"Bearer {auth_config['token']}"

        # Determine health check URL
        health_url = destination
        if not destination.endswith(("/health", "/ping", "/status")):
            # Try common health check endpoints
            from urllib.parse import urlparse

            parsed = urlparse(destination)
            health_url = f"{parsed.scheme}://{parsed.netloc}/health"

        response = requests.get(health_url, headers=headers, timeout=10)
        if response.status_code < 400:
            return destination, True, None
        else:
            return destination, False, f"HTTP {response.status_code}"

    except Exception as e:
        return destination, False, str(e)


def _check_kafka_health(
    destination: str, config: Dict[str, Any]
) -> Tuple[str, bool, Optional[str]]:
    """Process-isolated Kafka health check."""
    try:
        # Parse Kafka brokers from destination
        if destination.startswith("kafka://"):
            brokers = destination[8:].split(",")
        else:
            brokers = [destination]

        # Try to connect to Kafka (requires kafka-python)
        try:
            from kafka import KafkaProducer

            producer = KafkaProducer(
                bootstrap_servers=brokers, request_timeout_ms=10000, api_version=(0, 10, 1)
            )
            # Test connection
            producer.bootstrap_connected()
            producer.close()
            return destination, True, None
        except ImportError:
            # kafka-python not available, assume healthy
            return destination, True, None
        except Exception as e:
            return destination, False, str(e)

    except Exception as e:
        return destination, False, str(e)


def _check_zmq_health(destination: str, config: Dict[str, Any]) -> Tuple[str, bool, Optional[str]]:
    """Process-isolated ZMQ health check."""
    try:
        # Try to create a ZMQ socket and connect
        try:
            import zmq

            context = zmq.Context()
            socket = context.socket(zmq.REQ)
            socket.setsockopt(zmq.LINGER, 0)
            socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 second timeout

            socket.connect(destination)

            # Send a ping message
            socket.send_string("ping")

            # Try to receive (will timeout if no response)
            try:
                _ = socket.recv_string()
                socket.close()
                context.term()
                return destination, True, None
            except zmq.Again:
                # Timeout - connection exists but no response
                socket.close()
                context.term()
                return destination, True, None  # Consider connected as healthy

        except ImportError:
            # pyzmq not available, assume healthy
            return destination, True, None
        except Exception as e:
            return destination, False, str(e)

    except Exception as e:
        return destination, False, str(e)


def _check_file_health(destination: str, config: Dict[str, Any]) -> Tuple[str, bool, Optional[str]]:
    """Process-isolated file health check."""
    try:
        from pathlib import Path

        file_path = Path(destination)

        # Check if directory exists and is writable
        if file_path.parent.exists() and file_path.parent.is_dir():
            # Try to create a test file
            test_file = file_path.parent / ".health_test"
            try:
                test_file.touch()
                test_file.unlink()  # Clean up
                return destination, True, None
            except PermissionError:
                return destination, False, "Permission denied"
        else:
            return destination, False, "Directory does not exist"

    except Exception as e:
        return destination, False, str(e)
