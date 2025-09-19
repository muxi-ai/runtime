"""
Environment-specific test configuration.
"""

import os
from typing import Dict, Any


class TestEnvironment:
    """Handle environment-specific test configuration."""

    @property
    def is_ci(self) -> bool:
        """Check if running in CI/CD environment."""
        return os.getenv("CI", "").lower() in ["true", "1", "yes"]

    @property
    def is_docker(self) -> bool:
        """Check if running in Docker container."""
        return (
            os.path.exists("/.dockerenv") or
            os.getenv("DOCKER_CONTAINER", "").lower() in ["true", "1", "yes"]
        )

    @property
    def is_local(self) -> bool:
        """Check if running locally."""
        return not self.is_ci and not self.is_docker

    def get_service_url(self, service: str) -> str:
        """Get service URL based on environment."""
        if self.is_docker:
            # Docker service names
            service_map = {
                "postgres": "postgres:5432",
                "faissx": "faissx:45678",
                "webhook": "webhook:8080",
                "a2a": "a2a-registry:8090",
            }
        else:
            # Local and CI use localhost
            service_map = {
                "postgres": "localhost:5432",
                "faissx": "localhost:45678",
                "webhook": "localhost:8080",
                "a2a": "localhost:8090",
            }

        return service_map.get(service, f"localhost:{self._default_port(service)}")

    def get_timeout_multiplier(self) -> float:
        """Get timeout multiplier based on environment."""
        if self.is_ci:
            return 2.0  # CI runners can be slow
        elif self.is_docker:
            return 1.5  # Docker adds some overhead
        else:
            return 1.0  # Local is baseline

    def get_parallel_workers(self) -> int:
        """Get number of parallel workers based on environment."""
        if self.is_ci:
            return 2  # GitHub Actions provides 2 cores
        elif self.is_docker:
            return 4  # Docker might have resource limits
        else:
            import multiprocessing

            return min(8, multiprocessing.cpu_count())

    @staticmethod
    def _default_port(service: str) -> int:
        """Get default port for service."""
        ports = {
            "postgres": 5432,
            "faissx": 45678,
            "webhook": 8080,
            "a2a": 8090,
        }
        return ports.get(service, 8000)

    def get_test_config(self) -> Dict[str, Any]:
        """Get complete test configuration for current environment."""
        return {
            "environment": "ci" if self.is_ci else "docker" if self.is_docker else "local",
            "parallel_workers": self.get_parallel_workers(),
            "timeout_multiplier": self.get_timeout_multiplier(),
            "services": {
                "postgres": self.get_service_url("postgres"),
                "faissx": self.get_service_url("faissx"),
                "webhook": self.get_service_url("webhook"),
                "a2a": self.get_service_url("a2a"),
            },
            "features": {
                "verbose_logging": self.is_local,
                "capture_screenshots": self.is_local,
                "performance_tracking": True,
                "cleanup_validation": not self.is_ci,  # Skip in CI for speed
            },
        }


# Global instance
test_env = TestEnvironment()
