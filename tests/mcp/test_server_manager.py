"""
MCP Test Server Manager for managing the three test servers during integration testing.
"""

import os
import subprocess
import asyncio
import aiohttp
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass


@dataclass
class ServerConfig:
    """Configuration for a test server."""
    name: str
    type: str  # "stdio", "http_sse", "streamable_http"
    command: Optional[List[str]] = None
    url: Optional[str] = None
    port: Optional[int] = None
    expected_tools: List[str] = None
    expected_resources: List[str] = None
    expected_templates: List[str] = None
    expected_prompts: List[str] = None
    supports_sampling: bool = False
    auth_env: Dict[str, str] = None

    def __post_init__(self):
        if self.expected_tools is None:
            self.expected_tools = []
        if self.expected_resources is None:
            self.expected_resources = []
        if self.expected_templates is None:
            self.expected_templates = []
        if self.expected_prompts is None:
            self.expected_prompts = []
        if self.auth_env is None:
            self.auth_env = {}


class MCPTestServerManager:
    """Manager for MCP test servers."""

    def __init__(self):
        self.running_servers: Dict[str, subprocess.Popen] = {}
        self.server_configs = self._create_server_configs()

    def _create_server_configs(self) -> Dict[str, ServerConfig]:
        """Create server configurations based on actual implementations."""
        return {
            "stdio": ServerConfig(
                name="Stdio MCP Server (Full MCP 2024-11-05 Compliance)",
                type="stdio",
                command=["python", "mcp-testing-servers/stdio.py"],
                expected_tools=["fs_ops", "sys_info", "text_completion"],
                expected_resources=[
                    "file://server_config.json",
                    "file://performance_metrics.csv",
                    "memory://active_sessions"
                ],
                expected_templates=["api_response_template", "data_analysis_template"],
                expected_prompts=["code_review", "data_analysis"],
                supports_sampling=True,
                auth_env={
                    "MCP_STDIO_AUTH_ENABLED": "false",
                    "MCP_STDIO_AUTH_TOKEN": "test-token-123"
                }
            ),
            "http_sse": ServerConfig(
                name="HTTP + SSE MCP Server (MCP 2024-11-05 + Resources + Prompts)",
                type="http_sse",
                command=["python", "mcp-testing-servers/sse.py", "--host", "localhost", "--port", "8001"],
                url="http://localhost:8001",
                port=8001,
                expected_tools=["data_proc", "http_client"],
                expected_resources=[],  # Resources supported but specific URIs vary
                expected_templates=[],  # Templates supported but specific names vary
                expected_prompts=[],    # Prompts supported but specific names vary
                supports_sampling=False,
                auth_env={
                    "MCP_HTTP_AUTH_ENABLED": "false",
                    "MCP_HTTP_AUTH_TOKEN": "http-test-token-456"
                }
            ),
            "streamable_http": ServerConfig(
                name="Streamable HTTP MCP Server (Full MCP 2025-03-26 Compliance)",
                type="streamable_http",
                command=["python", "mcp-testing-servers/streaming.py", "--host", "localhost", "--port", "8002"],
                url="http://localhost:8002",
                port=8002,
                expected_tools=["rt_data_gen", "async_tasks", "text_completion"],
                expected_resources=[
                    "file://server_config.json",
                    "file://performance_metrics.csv",
                    "memory://active_sessions",
                    "stream://system_logs"
                ],
                expected_templates=[
                    "api_response_template",
                    "data_analysis_template",
                    "streaming_event_template"
                ],
                expected_prompts=["code_review", "data_analysis", "troubleshooting"],
                supports_sampling=True,
                auth_env={
                    "MCP_STREAM_AUTH_ENABLED": "false",
                    "MCP_STREAM_AUTH_TOKEN": "stream-bearer-token-789"
                }
            )
        }

    def get_server_config(self, server_type: str) -> Optional[ServerConfig]:
        """Get configuration for a specific server type."""
        return self.server_configs.get(server_type)

    def get_all_server_types(self) -> List[str]:
        """Get list of all server types."""
        return list(self.server_configs.keys())

    async def start_server(self, server_type: str, auth_enabled: bool = False, timeout: int = 10) -> bool:
        """Start a test server."""
        if server_type in self.running_servers:
            return True

        config = self.get_server_config(server_type)
        if not config:
            raise ValueError(f"Unknown server type: {server_type}")

        try:
            # Set up environment variables
            env = os.environ.copy()
            for key, value in config.auth_env.items():
                if "ENABLED" in key:
                    env[key] = "true" if auth_enabled else "false"
                else:
                    env[key] = value

            # Start the server process
            process = subprocess.Popen(
                config.command,
                stdin=subprocess.PIPE if config.type == "stdio" else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd=os.getcwd()  # Ensure we're in the runtime directory
            )

            # For HTTP servers, wait for them to start up
            if config.type != "stdio":
                await asyncio.sleep(3)

                # Verify the server is responding
                if not await self._wait_for_http_server(config.url, timeout):
                    process.terminate()
                    try:
                        # Wait for process to terminate and capture output safely
                        stdout, stderr = process.communicate(timeout=5)
                        stderr_text = stderr.decode() if stderr else ""
                    except subprocess.TimeoutExpired:
                        process.kill()
                        stdout, stderr = process.communicate()
                        stderr_text = stderr.decode() if stderr else ""
                    raise RuntimeError(f"Server {server_type} failed to respond: {stderr_text}")

            # Check if process is still running
            if process.poll() is None:
                self.running_servers[server_type] = process
                print(f"✅ Started {config.name}")
                return True
            else:
                # Process has terminated - capture output safely
                stdout, stderr = process.communicate()
                stderr_text = stderr.decode() if stderr else ""
                raise RuntimeError(f"Server {server_type} failed to start: {stderr_text}")

        except Exception as e:
            print(f"❌ Failed to start {server_type} server: {e}")
            return False

    async def _wait_for_http_server(self, url: str, timeout: int) -> bool:
        """Wait for HTTP server to become available."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                async with aiohttp.ClientSession() as session:
                    # Try to connect to the server
                    async with session.get(f"{url}/health", timeout=2) as response:
                        if response.status == 200:
                            return True
            except Exception:
                pass
            await asyncio.sleep(0.5)
        return False

    async def stop_server(self, server_type: str):
        """Stop a running server."""
        if server_type in self.running_servers:
            process = self.running_servers[server_type]
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            del self.running_servers[server_type]
            config = self.get_server_config(server_type)
            print(f"🛑 Stopped {config.name if config else server_type}")

    async def stop_all_servers(self):
        """Stop all running servers."""
        for server_type in list(self.running_servers.keys()):
            await self.stop_server(server_type)

    def is_server_running(self, server_type: str) -> bool:
        """Check if a server is currently running."""
        if server_type not in self.running_servers:
            return False
        return self.running_servers[server_type].poll() is None

    async def health_check(self, server_type: str) -> bool:
        """Perform health check on a server."""
        if not self.is_server_running(server_type):
            return False

        config = self.get_server_config(server_type)
        if not config:
            return False

        if config.type == "stdio":
            # For stdio, just check if process is running
            return True
        else:
            # For HTTP servers, check health endpoint
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{config.url}/health", timeout=5) as response:
                        return response.status == 200
            except Exception:
                return False

    async def get_server_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all servers."""
        status = {}
        for server_type in self.get_all_server_types():
            config = self.get_server_config(server_type)
            is_running = self.is_server_running(server_type)
            health_ok = await self.health_check(server_type) if is_running else False

            status[server_type] = {
                "name": config.name,
                "type": config.type,
                "running": is_running,
                "healthy": health_ok,
                "url": config.url,
                "port": config.port,
                "expected_tools": config.expected_tools,
                "supports_sampling": config.supports_sampling
            }

        return status

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - stop all servers."""
        await self.stop_all_servers()
