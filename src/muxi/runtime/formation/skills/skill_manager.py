import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ...datatypes import observability
from .parser import SkillMetadata, load_skill_content, parse_skill_md


class SkillManager:
    """
    Manages skill discovery, catalog generation, and activation.

    Follows the Agent Skills standard progressive disclosure model:
    - Tier 1 (catalog): name + description loaded at startup
    - Tier 2 (instructions): full SKILL.md loaded on activate_skill call
    - Tier 3 (resources): scripts/references/assets listed on activation
    """

    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self.skills: Dict[str, SkillMetadata] = {}
        self.public_skills: List[str] = []
        self.agent_skills: Dict[str, List[str]] = {}
        self._content_cache: Dict[str, Any] = {}
        self._activated: Dict[str, Set[str]] = {}

    def load_public_skills(self, skill_names: List[str]) -> None:
        """Load formation-level (public) skills from the skills directory."""
        for name in skill_names:
            self._load_skill(name)
        self.public_skills = list(skill_names)

    def load_agent_skills(self, agent_id: str, skill_names: List[str]) -> None:
        """Load agent-specific (private) skills."""
        for name in skill_names:
            if name not in self.skills:
                self._load_skill(name)
        self.agent_skills[agent_id] = list(skill_names)

    def _load_skill(self, name: str) -> SkillMetadata:
        """Parse SKILL.md frontmatter for a single skill."""
        skill_dir = self.skills_dir / name
        skill_md = skill_dir / "SKILL.md"

        if not skill_dir.is_dir():
            raise ValueError(
                f"Skill '{name}' declared but directory not found: {skill_dir}"
            )
        if not skill_md.is_file():
            raise ValueError(
                f"Skill '{name}' missing SKILL.md: {skill_md}"
            )

        metadata, _body, warnings = parse_skill_md(skill_md)

        for warning in warnings:
            observability.observe(
                event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
                level=observability.EventLevel.WARNING,
                data={"skill_name": name, "warning": warning},
                description=f"Skill '{name}': {warning}",
            )

        self.skills[name] = metadata
        return metadata

    def get_available_skills(self, agent_id: str) -> List[str]:
        """Get skill names available to an agent (public + private, deduplicated)."""
        available = list(self.public_skills)
        for name in self.agent_skills.get(agent_id, []):
            if name not in available:
                available.append(name)
        return available

    def get_skill_descriptions(self, agent_id: str) -> List[str]:
        """Get skill descriptions for specialty enhancement."""
        descriptions = []
        for name in self.get_available_skills(agent_id):
            skill = self.skills.get(name)
            if skill:
                descriptions.append(skill.description)
        return descriptions

    def build_catalog_xml(self, agent_id: str) -> Optional[str]:
        """Build XML catalog for an agent's available skills.

        Returns None if agent has no skills.
        """
        available = self.get_available_skills(agent_id)
        if not available:
            return None

        entries = []
        for name in available:
            skill = self.skills.get(name)
            if skill:
                entries.append(
                    f"  <skill>\n"
                    f"    <name>{skill.name}</name>\n"
                    f"    <description>{skill.description}</description>\n"
                    f"  </skill>"
                )

        return (
            "<available_skills>\n"
            "The following skills provide specialized instructions for specific tasks.\n"
            "When a task matches a skill's description, call the activate_skill tool\n"
            "with the skill's name to load its full instructions.\n\n"
            + "\n".join(entries)
            + "\n</available_skills>"
        )

    def build_activate_skill_tool(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Build the activate_skill tool definition for an agent.

        Returns None if agent has no skills.
        """
        available = self.get_available_skills(agent_id)
        if not available:
            return None

        return {
            "type": "function",
            "function": {
                "name": "activate_skill",
                "description": (
                    "Load the full instructions for an available skill. "
                    "Call this when a task matches a skill's description in the catalog."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "enum": available,
                            "description": "Name of the skill to activate",
                        }
                    },
                    "required": ["skill_name"],
                },
            },
        }

    def is_activated(self, skill_name: str, session_id: str) -> bool:
        """Check if a skill is already activated in a session."""
        return skill_name in self._activated.get(session_id, set())

    def activate(self, skill_name: str, session_id: str) -> str:
        """Load full SKILL.md, mark as activated, return wrapped content."""
        if skill_name not in self.skills:
            return f"Error: Skill '{skill_name}' not found."

        if self.is_activated(skill_name, session_id):
            return (
                f"Skill '{skill_name}' is already active. "
                "Refer to the instructions already in your context."
            )

        metadata = self.skills[skill_name]

        if skill_name not in self._content_cache:
            self._content_cache[skill_name] = load_skill_content(metadata)

        content = self._content_cache[skill_name]
        wrapped = self._wrap_skill_content(content)

        self._activated.setdefault(session_id, set()).add(skill_name)

        return wrapped

    def _wrap_skill_content(self, content: Any) -> str:
        """Wrap skill content in structured XML tags."""
        parts = [f'<skill_content name="{content.metadata.name}">']
        parts.append(content.body)

        if content.resources:
            parts.append("\n<skill_resources>")
            for resource in content.resources:
                parts.append(f"  <file>{resource}</file>")
            parts.append("</skill_resources>")

        parts.append("</skill_content>")
        return "\n".join(parts)

    def get_skill_hash(self, skill_name: str) -> Optional[str]:
        """Compute SHA-256 hash of a skill directory for RCE cache validation."""
        if skill_name not in self.skills:
            return None

        metadata = self.skills[skill_name]
        hasher = hashlib.sha256()

        for f in sorted(metadata.base_dir.rglob("*")):
            if f.is_file():
                hasher.update(str(f.relative_to(metadata.base_dir)).encode())
                hasher.update(f.read_bytes())

        return f"sha256:{hasher.hexdigest()}"

    def get_all_skills_info(self) -> List[Dict[str, Any]]:
        """Get info for all loaded skills (for REST API)."""
        result = []
        for name, skill in self.skills.items():
            scope = "public" if name in self.public_skills else "private"
            result.append({
                "name": skill.name,
                "description": skill.description,
                "scope": scope,
                "has_scripts": any(
                    r.startswith("scripts/") for r in self._get_resources(name)
                ),
                "resource_count": len(self._get_resources(name)),
            })
        return result

    def _get_resources(self, skill_name: str) -> List[str]:
        """Get resources list, loading content if needed."""
        if skill_name in self._content_cache:
            return self._content_cache[skill_name].resources
        metadata = self.skills.get(skill_name)
        if not metadata:
            return []
        from .parser import _enumerate_resources
        return _enumerate_resources(metadata.base_dir)
