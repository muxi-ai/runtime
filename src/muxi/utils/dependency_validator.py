"""
Formation Dependency Validation System

Validates service dependencies before Formation startup to ensure all required
dependencies are available and properly configured.
"""

from typing import Dict, Any, List
import importlib
import os

from ..datatypes.validation import ServiceDependency, ValidationResult


class DependencyValidator:
    """
    Validates Formation service dependencies before startup.

    Checks for:
    - Required Python packages
    - Service configuration dependencies
    - File system dependencies
    - Environment variable dependencies
    - Circular dependency detection
    """

    def __init__(self):
        self.service_dependencies = self._define_service_dependencies()

    def _define_service_dependencies(self) -> Dict[str, List[ServiceDependency]]:
        """Define dependencies for each Formation service."""
        return {
            "llm": [
                # OneLLM handles all LLM providers and their dependencies
                ServiceDependency("onellm", "package", description="Unified LLM interface"),
            ],
            "memory": [
                ServiceDependency("sqlite3", "package", description="SQLite database support"),
                ServiceDependency(
                    "psycopg2",
                    "package",
                    required=False,
                    description="PostgreSQL support for Memobase",
                ),
            ],
            "mcp": [
                ServiceDependency("websockets", "package", description="WebSocket support for MCP"),
                ServiceDependency(
                    "jsonrpc", "package", required=False, description="JSON-RPC support"
                ),
            ],
            "a2a": [
                ServiceDependency("aiohttp", "package", description="Async HTTP client/server"),
                ServiceDependency("websockets", "package", description="WebSocket support"),
            ],
            "secrets": [
                ServiceDependency("cryptography", "package", description="Encryption support"),
            ],
            "observability": [
                ServiceDependency(
                    "structlog", "package", required=False, description="Structured logging"
                ),
            ],
            "documents": [
                ServiceDependency("pypdf", "package", required=False, description="PDF processing"),
                ServiceDependency(
                    "python-docx", "package", required=False, description="Word document processing"
                ),
            ],
        }

    def validate_formation_dependencies(self, config: Dict[str, Any]) -> ValidationResult:
        """
        Validate all dependencies for a Formation configuration.

        Args:
            config: Formation configuration dictionary

        Returns:
            ValidationResult with validation status and details
        """
        errors = []
        warnings = []
        missing_dependencies = []
        circular_dependencies = []

        try:
            # Determine which services are enabled
            enabled_services = self._get_enabled_services(config)

            # Validate service dependencies
            for service_name in enabled_services:
                result = self._validate_service_dependencies(service_name, config)
                errors.extend(result.errors)
                warnings.extend(result.warnings)
                missing_dependencies.extend(result.missing_dependencies)

            # Check for circular dependencies
            circular_deps = self._detect_circular_dependencies(enabled_services, config)
            circular_dependencies.extend(circular_deps)

            # Add circular dependency errors
            for cycle in circular_deps:
                cycle_str = " -> ".join(cycle + [cycle[0]])
                errors.append(f"Circular dependency detected: {cycle_str}")

            # Validate configuration dependencies
            config_errors = self._validate_configuration_dependencies(config)
            errors.extend(config_errors)

            is_valid = len(errors) == 0 and len(circular_dependencies) == 0

        except Exception as e:
            errors.append(f"Dependency validation failed: {str(e)}")
            is_valid = False

        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            missing_dependencies=missing_dependencies,
            circular_dependencies=circular_dependencies,
        )

    def _get_enabled_services(self, config: Dict[str, Any]) -> List[str]:
        """Determine which services are enabled based on configuration."""
        enabled_services = []

        # Always enabled core services
        enabled_services.extend(["secrets"])

        # Check for service-specific configuration
        if config.get("llm"):
            enabled_services.append("llm")

        if config.get("memory"):
            enabled_services.append("memory")

        if config.get("mcp"):
            enabled_services.append("mcp")

        if config.get("a2a", {}).get("enabled", False):
            enabled_services.append("a2a")

        if config.get("logging"):
            enabled_services.append("observability")

        if config.get("document_processing"):
            enabled_services.append("documents")

        return enabled_services

    def _validate_service_dependencies(
        self, service_name: str, config: Dict[str, Any]
    ) -> ValidationResult:
        """Validate dependencies for a specific service."""
        errors = []
        warnings = []
        missing_dependencies = []

        if service_name not in self.service_dependencies:
            return ValidationResult(True, [], [], [], [])

        dependencies = self.service_dependencies[service_name]

        for dep in dependencies:
            if dep.type == "package":
                if not self._check_package_dependency(dep):
                    if dep.required:
                        errors.append(
                            f"❌ Required package '{dep.name}' not found for {service_name} service. "
                            f"Install with: pip install {dep.name}"
                        )
                        missing_dependencies.append(dep)
                    else:
                        warnings.append(
                            f"⚠️  Optional package '{dep.name}' not found for {service_name} service. "
                            f"Install with: pip install {dep.name}"
                        )

            elif dep.type == "config":
                if not self._check_config_dependency(dep, config):
                    if dep.required:
                        errors.append(
                            f"❌ Required configuration '{dep.name}' missing for {service_name} service. "
                            f"Add to your formation.afs: {dep.name}: <value>"
                        )
                        missing_dependencies.append(dep)
                    else:
                        warnings.append(
                            f"⚠️  Optional configuration '{dep.name}' missing for {service_name} service. "
                            f"Add to your formation.afs: {dep.name}: <value>"
                        )

            elif dep.type == "env":
                if not self._check_env_dependency(dep):
                    if dep.required:
                        errors.append(
                            f"Required environment variable '{dep.name}' not set for {service_name} service"
                        )
                        missing_dependencies.append(dep)
                    else:
                        warnings.append(
                            f"Optional environment variable '{dep.name}' not set for {service_name} service"
                        )

            elif dep.type == "file":
                if not self._check_file_dependency(dep):
                    if dep.required:
                        errors.append(
                            f"Required file '{dep.name}' not found for {service_name} service"
                        )
                        missing_dependencies.append(dep)
                    else:
                        warnings.append(
                            f"Optional file '{dep.name}' not found for {service_name} service"
                        )

        is_valid = len(errors) == 0
        return ValidationResult(is_valid, errors, warnings, missing_dependencies, [])

    def _check_package_dependency(self, dep: ServiceDependency) -> bool:
        """Check if a Python package dependency is available."""
        try:
            importlib.import_module(dep.name)
            return True
        except ImportError:
            return False

    def _check_config_dependency(self, dep: ServiceDependency, config: Dict[str, Any]) -> bool:
        """Check if a configuration dependency is met."""
        # Navigate nested config path (e.g., "llm.api_keys.openai")
        parts = dep.name.split(".")
        current = config

        for part in parts:
            if not isinstance(current, dict) or part not in current:
                return False
            current = current[part]

        return current is not None

    def _check_env_dependency(self, dep: ServiceDependency) -> bool:
        """Check if an environment variable dependency is met."""
        return os.getenv(dep.name) is not None

    def _check_file_dependency(self, dep: ServiceDependency) -> bool:
        """Check if a file dependency exists."""
        return os.path.exists(dep.name)

    def _detect_circular_dependencies(
        self, services: List[str], config: Dict[str, Any]
    ) -> List[List[str]]:
        """Detect circular dependencies between services."""
        # Build dependency graph
        graph = self._build_service_dependency_graph(services, config)

        # Find cycles using DFS
        visited = set()
        rec_stack = set()
        cycles = []

        def dfs(node: str, path: List[str]) -> None:
            if node in rec_stack:
                # Found a cycle
                cycle_start = path.index(node)
                cycle = path[cycle_start:]
                cycles.append(cycle)
                return

            if node in visited:
                return

            visited.add(node)
            rec_stack.add(node)

            for neighbor in graph.get(node, []):
                dfs(neighbor, path + [neighbor])

            rec_stack.remove(node)

        for service in services:
            if service not in visited:
                dfs(service, [service])

        return cycles

    def _build_service_dependency_graph(
        self, services: List[str], config: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        """Build a dependency graph between services."""
        graph = {service: [] for service in services}

        # Define service interdependencies
        if "llm" in services and "memory" in services:
            # Memory service may depend on LLM for embeddings
            graph["memory"].append("llm")

        if "a2a" in services and "llm" in services:
            # A2A service depends on LLM for communication
            graph["a2a"].append("llm")

        if "documents" in services and "llm" in services:
            # Document processing depends on LLM
            graph["documents"].append("llm")

        if "mcp" in services and "llm" in services:
            # MCP may depend on LLM for tool interactions
            graph["mcp"].append("llm")

        return graph

    def _validate_configuration_dependencies(self, config: Dict[str, Any]) -> List[str]:
        """Validate configuration-level dependencies."""
        errors = []

        # Check LLM configuration dependencies
        if config.get("llm"):
            llm_config = config["llm"]

            # Check if using test/mock models
            models = llm_config.get("models", [])
            is_test_model = any(
                model.get(capability, "").startswith(("test/", "mock/"))
                for model in models
                for capability in ["text", "vision", "audio", "documents", "embedding"]
            )

            # Require at least one API key (unless using test/mock models)
            api_keys = llm_config.get("api_keys", {})
            if not api_keys and not is_test_model:
                errors.append(
                    "❌ LLM service requires at least one API key in 'llm.api_keys'. "
                    "Add: llm.api_keys.openai: 'sk-your-key'"
                )

            # Require at least one model
            models = llm_config.get("models", [])
            if not models:
                errors.append(
                    "❌ LLM service requires at least one model in 'llm.models'. "
                    "Add: llm.models: [{name: 'gpt-4', provider: 'openai'}]"
                )

        # Check memory configuration dependencies
        if config.get("memory"):
            memory_config = config["memory"]
            memory_type = memory_config.get("type")

            if memory_type == "memobase":
                if not memory_config.get("connection_string"):
                    errors.append("Memobase memory type requires 'connection_string' configuration")

        # Check A2A configuration dependencies
        if config.get("a2a", {}).get("enabled"):
            a2a_config = config["a2a"]

            # Check for inbound configuration if inbound is enabled
            if a2a_config.get("inbound", {}).get("enabled"):
                inbound_config = a2a_config.get("inbound", {})
                if not inbound_config.get("port"):
                    errors.append("A2A inbound service requires 'port' configuration")

        return errors

    def get_installation_suggestions(self, missing_deps: List[ServiceDependency]) -> List[str]:
        """Generate installation suggestions for missing dependencies."""
        suggestions = []

        package_deps = [dep for dep in missing_deps if dep.type == "package"]
        if package_deps:
            packages = [dep.name for dep in package_deps]
            pip_install = f"pip install {' '.join(packages)}"
            suggestions.append(f"Install missing packages: {pip_install}")

        config_deps = [dep for dep in missing_deps if dep.type == "config"]
        if config_deps:
            for dep in config_deps:
                suggestions.append(f"Add missing configuration: {dep.name}")

        env_deps = [dep for dep in missing_deps if dep.type == "env"]
        if env_deps:
            for dep in env_deps:
                suggestions.append(f"Set environment variable: export {dep.name}=<value>")

        return suggestions
