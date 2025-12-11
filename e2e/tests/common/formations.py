"""
Formation management utilities for E2E tests.

Supports three formation sharing patterns:
1. Runtime modification - Single formation, modified at runtime
2. Shared directory - Multiple YAMLs in same directory
3. Separate formations - Complete isolation per test
"""

import shutil
from pathlib import Path
from typing import Optional, Dict, Any


class FormationPattern:
    """Constants for formation patterns."""

    RUNTIME = "runtime"  # Pattern 1: Runtime modification
    SHARED = "shared"  # Pattern 2: Shared dir with multiple YAMLs
    SEPARATE = "separate"  # Pattern 3: Complete separation


# Test area to pattern mapping
TEST_PATTERNS = {
    # Pattern 1: Runtime modification (56% of tests)
    "1_foundation": FormationPattern.RUNTIME,
    "artifacts": FormationPattern.RUNTIME,
    "9_async": FormationPattern.RUNTIME,
    "10_streaming": FormationPattern.RUNTIME,
    "11_formatting": FormationPattern.RUNTIME,
    "12_scheduling": FormationPattern.RUNTIME,
    # Pattern 2: Shared directory with multiple YAMLs (23% of tests)
    "2_memory": FormationPattern.SHARED,
    "4_mcp": FormationPattern.SHARED,
    "knowledge": FormationPattern.SHARED,
    # Pattern 3: Completely separate formations (21% of tests)
    "3_multimodal": FormationPattern.SEPARATE,
    "orchestration": FormationPattern.SEPARATE,
    "clarification": FormationPattern.SEPARATE,
}


class FormationManager:
    """Manages formation configurations for E2E tests."""

    # Base path for common formations
    BASE_PATH = Path(__file__).parent / "formation_templates"

    # Template types
    TEMPLATES = {
        "standard": "base/standard",
        "minimal": "base/minimal",
        "complex": "base/complex",
    }

    @classmethod
    def get_formation_path(
        cls,
        test_area: str,
        pattern: str,
        yaml_name: Optional[str] = None,
        test_name: Optional[str] = None,
    ) -> Path:
        """
        Get the appropriate formation path based on pattern.

        Args:
            test_area: Test area (e.g., "2_memory", "4_mcp")
            pattern: Formation pattern ("runtime", "shared", "separate")
            yaml_name: YAML filename for shared pattern (e.g., "formation-buffer-local.yaml")
            test_name: Test name for separate pattern

        Returns:
            Path to formation directory or YAML file
        """
        base_path = Path(__file__).parent.parent / test_area

        if pattern == FormationPattern.RUNTIME:
            # Pattern 1: Single shared formation directory
            return base_path / "formations" / "formation-base"

        elif pattern == FormationPattern.SHARED:
            # Pattern 2: Shared directory with multiple YAMLs
            formation_dir = base_path / "formations" / f"formation-{test_area.split('_')[1]}"
            if yaml_name:
                return formation_dir / yaml_name
            return formation_dir

        elif pattern == FormationPattern.SEPARATE:
            # Pattern 3: Completely separate formations
            if not test_name:
                raise ValueError("Separate pattern requires test_name parameter")
            return base_path / "formations" / f"formation-{test_name}"

        else:
            raise ValueError(f"Unknown formation pattern: {pattern}")

    @classmethod
    def setup_runtime_formation(cls, test_area: str, template: str = "standard") -> Path:
        """
        Set up a runtime-modifiable formation.

        Args:
            test_area: Test area (e.g., "1_foundation")
            template: Template to use (standard/minimal/complex)

        Returns:
            Path to the formation directory
        """
        formation_dir = Path(__file__).parent.parent / test_area / "formations" / "formation-base"
        formation_dir.mkdir(parents=True, exist_ok=True)

        # Copy template
        template_path = cls.BASE_PATH / cls.TEMPLATES[template]
        if template_path.exists():
            # Copy formation.afs
            template_yaml = template_path / "formation.afs"
            if template_yaml.exists():
                shutil.copy2(template_yaml, formation_dir / "formation.afs")

            # Copy agents if present
            agents_src = template_path / "agents"
            if agents_src.exists():
                agents_dst = formation_dir / "agents"
                if agents_dst.exists():
                    shutil.rmtree(agents_dst)
                shutil.copytree(agents_src, agents_dst)

        # Copy secrets and key
        cls.setup_secrets(formation_dir)

        return formation_dir

    @classmethod
    def setup_shared_formation(
        cls, test_area: str, yaml_configs: Dict[str, Dict], template: str = "minimal"
    ) -> Path:
        """
        Set up a shared formation directory with multiple YAMLs.

        Args:
            test_area: Test area (e.g., "2_memory")
            yaml_configs: Dict mapping YAML names to their specific configs
            template: Base template to use

        Returns:
            Path to the formation directory
        """
        area_name = test_area.split("_")[1] if "_" in test_area else test_area
        formation_dir = (
            Path(__file__).parent.parent / test_area / "formations" / f"formation-{area_name}"
        )
        formation_dir.mkdir(parents=True, exist_ok=True)

        # Copy base template
        template_path = cls.BASE_PATH / cls.TEMPLATES[template]

        # Copy agents directory if exists
        agents_src = (
            template_path / "agents" if template_path.exists() else cls.BASE_PATH / "agents"
        )
        if agents_src.exists():
            agents_dst = formation_dir / "agents"
            if not agents_dst.exists():
                shutil.copytree(agents_src, agents_dst)

        # Create each YAML configuration
        for yaml_name, config in yaml_configs.items():
            yaml_path = formation_dir / yaml_name
            # This would write the actual YAML config
            # For now, just copy template and modify
            if template_path.exists():
                template_yaml = template_path / "formation.afs"
                if template_yaml.exists():
                    shutil.copy2(template_yaml, yaml_path)

        # Copy secrets and key
        cls.setup_secrets(formation_dir)

        return formation_dir

    @classmethod
    def setup_separate_formation(
        cls,
        test_area: str,
        test_name: str,
        formation_config: Dict[str, Any],
        template: str = "minimal",
    ) -> Path:
        """
        Set up a completely separate formation for a test.

        Args:
            test_area: Test area (e.g., "orchestration")
            test_name: Specific test name
            formation_config: Complete formation configuration
            template: Base template to use

        Returns:
            Path to the formation directory
        """
        formation_dir = (
            Path(__file__).parent.parent / test_area / "formations" / f"formation-{test_name}"
        )
        formation_dir.mkdir(parents=True, exist_ok=True)

        # Copy base template
        template_path = cls.BASE_PATH / cls.TEMPLATES[template]
        if template_path.exists():
            for item in template_path.iterdir():
                if item.is_file():
                    shutil.copy2(item, formation_dir)
                elif item.is_dir() and item.name in ["agents", "sops", "workflows"]:
                    dst = formation_dir / item.name
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(item, dst)

        # Write custom configuration
        # This would write the actual formation_config to YAML

        # Copy secrets and key
        cls.setup_secrets(formation_dir)

        return formation_dir

    @classmethod
    def setup_secrets(cls, formation_dir: Path):
        """
        Create symlinks to shared secrets and key files.

        Args:
            formation_dir: Target formation directory
        """
        # Paths to original secrets in tests/assets/
        secrets_src = Path(__file__).parent.parent.parent.parent / "assets" / "secrets.enc"
        key_src = Path(__file__).parent.parent.parent.parent / "assets" / ".key"

        # Create symlinks (not copies) to maintain single source of truth
        secrets_dst = formation_dir / "secrets.enc"
        key_dst = formation_dir / ".key"

        if not secrets_dst.exists() and secrets_src.exists():
            # Calculate relative path for symlink
            try:
                # Count levels from formation_dir to tests/ root
                levels_up = len(
                    formation_dir.relative_to(Path(__file__).parent.parent.parent).parts
                )
                rel_path = Path(*[".."] * levels_up) / "assets" / "secrets.enc"
                secrets_dst.symlink_to(rel_path)
            except (OSError, ValueError):
                # Fallback to copy if symlink fails
                shutil.copy2(secrets_src, secrets_dst)

        if not key_dst.exists() and key_src.exists():
            try:
                levels_up = len(
                    formation_dir.relative_to(Path(__file__).parent.parent.parent).parts
                )
                rel_path = Path(*[".."] * levels_up) / "assets" / ".key"
                key_dst.symlink_to(rel_path)
            except (OSError, ValueError):
                # Fallback to copy if symlink fails
                shutil.copy2(key_src, key_dst)

    @classmethod
    def get_runtime_overrides(cls, test_type: str) -> Dict[str, Any]:
        """
        Get common runtime overrides for a test type.

        Args:
            test_type: Type of test (e.g., "memory", "mcp", "workflow")

        Returns:
            Dictionary of runtime overrides
        """
        overrides = {}

        if test_type == "memory":
            overrides = {"memory": {"buffer_size": 10, "auto_extract": True}}
        elif test_type == "mcp":
            overrides = {"mcp": {"timeout": 30}}
        elif test_type == "workflow":
            overrides = {"llm": {"auto_decomposition": True, "complexity_threshold": 5.0}}
        elif test_type == "async":
            overrides = {"async": {"webhook_url": "http://localhost:8080/webhook"}}
        elif test_type == "clarification":
            overrides = {"clarification": {"enabled": True, "max_turns": 3}}

        return overrides

    @classmethod
    def list_shared_yamls(cls, formation_dir: Path) -> list:
        """
        List all YAML files in a shared formation directory.

        Args:
            formation_dir: Path to formation directory

        Returns:
            List of YAML filenames
        """
        if not formation_dir.exists():
            return []

        return sorted(
            [
                f.name
                for f in formation_dir.iterdir()
                if f.suffix in [".yaml", ".yml"] and f.name.startswith("formation-")
            ]
        )
