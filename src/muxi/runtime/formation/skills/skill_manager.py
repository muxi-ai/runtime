import hashlib
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ...datatypes import observability
from ...services import observability as svc_observability
from .parser import SkillMetadata, load_skill_content, parse_skill_md

BUILTIN_SKILLS_DIR = Path(__file__).parent / "builtin"


class SkillManager:
    """
    Manages skill discovery, catalog generation, and activation.

    Follows the Agent Skills standard progressive disclosure model:
    - Tier 1 (catalog): name + description loaded at startup
    - Tier 2 (instructions): full SKILL.md loaded on activate_skill call
    - Tier 3 (resources): scripts/references/assets listed on activation
    """

    def __init__(self, skills_dir: Optional[Path] = None, secrets_manager=None):
        self.skills_dir = skills_dir
        self.skills: Dict[str, SkillMetadata] = {}
        self.public_skills: List[str] = []
        self.agent_skills: Dict[str, List[str]] = {}
        self._content_cache: Dict[str, Any] = {}
        self._activated: OrderedDict[str, Set[str]] = OrderedDict()
        self._activated_max = 10_000
        self._active_execution_context: OrderedDict[Tuple[str, str], Dict[str, Any]] = OrderedDict()
        self._active_execution_context_max = 10_000
        self._builtin_skills: List[str] = []
        self._secrets_manager = secrets_manager
        self._request_grants: OrderedDict[str, Dict[str, Set[str]]] = OrderedDict()
        self._request_grants_max = 10_000

    def load_builtin_skills(self, disabled: Optional[List[str]] = None) -> List[str]:
        """Load built-in skills shipped with the runtime.

        Built-in skills are always public (all agents see them).

        Args:
            disabled: List of built-in skill names to skip.

        Returns:
            List of loaded built-in skill names.
        """
        disabled = disabled or []
        loaded: List[str] = []
        if not BUILTIN_SKILLS_DIR.is_dir():
            return loaded

        for skill_dir in sorted(BUILTIN_SKILLS_DIR.iterdir()):
            if not skill_dir.is_dir():
                continue
            name = skill_dir.name
            if name in disabled or name in self.skills:
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                continue
            try:
                metadata, _body, warnings = parse_skill_md(skill_md)
                for warning in warnings:
                    svc_observability.observe(
                        event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
                        level=observability.EventLevel.WARNING,
                        data={"skill_name": name, "warning": warning},
                        description=f"Built-in skill '{name}': {warning}",
                    )
                self.skills[name] = metadata
                self._builtin_skills.append(name)
                if name not in self.public_skills:
                    self.public_skills.append(name)
                loaded.append(name)
            except Exception as e:
                svc_observability.observe(
                    event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={"skill_name": name, "error": str(e)},
                    description=f"Failed to load built-in skill '{name}': {e}",
                )
        return loaded

    def load_public_skills(self, skill_names: List[str]) -> None:
        """Load formation-level (public) skills from the skills directory."""
        for name in skill_names:
            self._load_skill(name)
        for name in skill_names:
            if name not in self.public_skills:
                self.public_skills.append(name)

    def load_agent_skills(self, agent_id: str, skill_names: List[str]) -> None:
        """Load agent-specific (private) skills."""
        for name in skill_names:
            if name not in self.skills:
                self._load_skill(name)
        self.agent_skills[agent_id] = list(skill_names)

    def _load_skill(self, name: str) -> SkillMetadata:
        """Parse SKILL.md frontmatter for a single skill."""
        if not self.skills_dir:
            raise ValueError(f"Skill '{name}' declared but no skills directory configured")
        skill_dir = self.skills_dir / name
        skill_md = skill_dir / "SKILL.md"

        if not skill_dir.is_dir():
            raise ValueError(f"Skill '{name}' declared but directory not found: {skill_dir}")
        if not skill_md.is_file():
            raise ValueError(f"Skill '{name}' missing SKILL.md: {skill_md}")

        metadata, _body, warnings = parse_skill_md(skill_md)

        for warning in warnings:
            svc_observability.observe(
                event_type=observability.ErrorEvents.CONFIGURATION_ERROR,
                level=observability.EventLevel.WARNING,
                data={"skill_name": name, "warning": warning},
                description=f"Skill '{name}': {warning}",
            )

        self.skills[name] = metadata
        return metadata

    def grant_request_skills(self, request_id: str, agent_id: str, names: list) -> None:
        """Transiently grant skills to an agent for a single request lifecycle.

        The grant is NOT persisted to public_skills or agent_skills; it only
        widens get_available_skills/build_*_tool when the same request_id is
        passed back in.  revoke_request_skills must be called in a finally block.
        """
        if not request_id:
            return
        bucket = self._request_grants.setdefault(request_id, {})
        agent_set = bucket.setdefault(agent_id, set())
        for n in names:
            if n in self.skills:
                agent_set.add(n)
        if len(self._request_grants) > self._request_grants_max:
            self._request_grants.popitem(last=False)

    def revoke_request_skills(self, request_id: str) -> None:
        """Remove all transient grants for a request_id."""
        self._request_grants.pop(request_id, None)

    def get_available_skills(self, agent_id: str, request_id: Optional[str] = None) -> List[str]:
        """Get skill names available to an agent (public + private + request grants, deduplicated)."""
        available = list(self.public_skills)
        for name in self.agent_skills.get(agent_id, []):
            if name not in available:
                available.append(name)
        if request_id:
            for name in self._request_grants.get(request_id, {}).get(agent_id, set()):
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
                entries.append(f"- **{skill.name}**: {skill.description}")

        return (
            "## Available Skills\n\n"
            "You have access to specialized skills that provide detailed instructions "
            "for specific tasks. BEFORE working on a task that matches a skill below, "
            "you MUST first call the activate_skill tool with the skill name to load "
            "its full instructions into your context.\n\n" + "\n".join(entries)
        )

    def build_activate_skill_tool(
        self, agent_id: str, request_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Build the activate_skill tool definition for an agent.

        Returns None if agent has no skills.
        """
        available = self.get_available_skills(agent_id, request_id=request_id)
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

    def build_run_skill_tool(
        self, agent_id: str, request_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Build the run_skill tool definition for an agent.

        Only available when:
        - Agent has skills with scripts/ directories
        - RCE client is configured on the overlord

        Returns None if no executable skills are available.
        """
        available = self.get_available_skills(agent_id, request_id=request_id)
        # Exclude file-generation from run_skill (uses generate_file tool instead)
        executable = [n for n in available if self.has_scripts(n) and n != "file-generation"]
        if not executable:
            return None

        script_list = []
        for name in executable:
            resources = self._get_resources(name)
            scripts = [r for r in resources if r.startswith("scripts/")]
            if scripts:
                script_list.append(f"{name}: {', '.join(scripts)}")

        return {
            "type": "function",
            "function": {
                "name": "run_skill",
                "description": (
                    "Execute a command inside a skill's sandboxed environment. "
                    "The skill directory is mounted read-only; any files created by "
                    "the command are returned as artifacts. "
                    "Available skill scripts:\n" + "\n".join(f"  - {s}" for s in script_list)
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "enum": executable,
                            "description": "Name of the skill to execute against",
                        },
                        "command": {
                            "type": "string",
                            "description": (
                                "Shell command to run (e.g., 'python3 scripts/run.py input.csv'). "
                                "Paths are relative to the skill root directory."
                            ),
                        },
                    },
                    "required": ["skill_name", "command"],
                },
            },
        }

    def has_scripts(self, skill_name: str) -> bool:
        """Check if a skill has any scripts/ files."""
        resources = self._get_resources(skill_name)
        return any(r.startswith("scripts/") for r in resources)

    def is_activated(self, skill_name: str, session_id: str) -> bool:
        """Check if a skill is already activated in a session."""
        return skill_name in self._activated.get(session_id, set())

    def set_secrets_manager(self, secrets_manager) -> None:
        """Attach a SecretsManager instance for secret interpolation."""
        self._secrets_manager = secrets_manager

    def activate(self, skill_name: str, session_id: str) -> str:
        """Load full SKILL.md, mark as activated, return wrapped content (sync, no interpolation)."""
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
        if len(self._activated) > self._activated_max:
            self._activated.popitem(last=False)

        return wrapped

    async def activate_async(
        self, skill_name: str, session_id: str, agent_id: Optional[str] = None
    ) -> str:
        """Load full SKILL.md, interpolate ${{ secrets.X }} in body, mark as activated."""
        if skill_name not in self.skills:
            return f"Error: Skill '{skill_name}' not found."

        if self.is_activated(skill_name, session_id):
            if agent_id:
                await self.activate_execution_context(skill_name, agent_id, session_id)
            return (
                f"Skill '{skill_name}' is already active. "
                "Refer to the instructions already in your context."
            )

        metadata = self.skills[skill_name]

        if skill_name not in self._content_cache:
            self._content_cache[skill_name] = load_skill_content(metadata)

        content = self._content_cache[skill_name]
        body = content.body

        if self._secrets_manager and metadata.required_secrets:
            try:
                body = await self._secrets_manager.interpolate_secrets(body)
            except Exception as e:
                svc_observability.observe(
                    event_type=svc_observability.ErrorEvents.CONFIGURATION_ERROR,
                    level=svc_observability.EventLevel.WARNING,
                    data={"skill_name": skill_name, "error": str(e)},
                    description=f"Skill '{skill_name}': secret interpolation failed: {e}",
                )

        wrapped = self._wrap_skill_content_body(content, body)

        self._activated.setdefault(session_id, set()).add(skill_name)
        if len(self._activated) > self._activated_max:
            self._activated.popitem(last=False)

        if agent_id:
            await self.activate_execution_context(skill_name, agent_id, session_id)

        return wrapped

    async def validate_secrets(self, skill_name: str) -> List[str]:
        """Return names of secrets referenced by a skill that are missing from the store.

        Called during formation init to surface configuration problems early.
        Does not block startup — returns an empty list if no secrets manager is set.
        """
        if not self._secrets_manager:
            return []
        metadata = self.skills.get(skill_name)
        if not metadata or not metadata.required_secrets:
            return []
        missing = []
        for name in metadata.required_secrets:
            try:
                value = await self._secrets_manager.get_secret(name)
                if value is None:
                    missing.append(name)
            except Exception:
                missing.append(name)
        return missing

    async def resolve_skill_env(self, skill_name: str) -> Dict[str, str]:
        """Resolve all secrets referenced by a skill into an env map for subprocess injection.

        Keys are secret names as-is (e.g. NOTION_KEY), values are plaintext.
        Missing secrets are omitted; a warning is logged for each.
        """
        env: Dict[str, str] = {}
        if not self._secrets_manager:
            return env
        metadata = self.skills.get(skill_name)
        if not metadata or not metadata.required_secrets:
            return env
        for name in metadata.required_secrets:
            try:
                value = await self._secrets_manager.get_secret(name)
                if value is not None:
                    env[name] = value
                else:
                    svc_observability.observe(
                        event_type=svc_observability.ErrorEvents.CONFIGURATION_ERROR,
                        level=svc_observability.EventLevel.WARNING,
                        data={"skill_name": skill_name, "secret_name": name},
                        description=(
                            f"Skill '{skill_name}': secret '{name}' not found in secrets store"
                        ),
                    )
            except Exception as e:
                svc_observability.observe(
                    event_type=svc_observability.ErrorEvents.CONFIGURATION_ERROR,
                    level=svc_observability.EventLevel.WARNING,
                    data={"skill_name": skill_name, "secret_name": name, "error": str(e)},
                    description=f"Skill '{skill_name}': failed to resolve secret '{name}': {e}",
                )
        return env

    async def _interpolate_execution_context_value(self, value: Any) -> Any:
        """Recursively interpolate secret references inside execution context values."""
        if isinstance(value, dict):
            return {
                key: await self._interpolate_execution_context_value(nested_value)
                for key, nested_value in value.items()
            }
        if isinstance(value, list):
            return [await self._interpolate_execution_context_value(item) for item in value]
        if isinstance(value, str) and self._secrets_manager:
            return await self._secrets_manager.interpolate_secrets(value)
        return value

    async def resolve_skill_execution_context(self, skill_name: str) -> Dict[str, Any]:
        """Resolve a skill's runtime-only execution context."""
        metadata = self.skills.get(skill_name)
        if not metadata or not metadata.execution_context:
            return {}

        try:
            resolved = await self._interpolate_execution_context_value(metadata.execution_context)
            return resolved if isinstance(resolved, dict) else {}
        except Exception as e:
            svc_observability.observe(
                event_type=svc_observability.ErrorEvents.CONFIGURATION_ERROR,
                level=svc_observability.EventLevel.WARNING,
                data={"skill_name": skill_name, "error": str(e)},
                description=(f"Skill '{skill_name}': execution context interpolation failed: {e}"),
            )
            return dict(metadata.execution_context)

    @staticmethod
    def _execution_context_key(agent_id: str, session_id: str) -> Tuple[str, str]:
        """Build the storage key for active execution context."""
        return (agent_id or "", session_id or "default")

    def get_active_execution_context(self, agent_id: str, session_id: str) -> Dict[str, Any]:
        """Return the merged active execution context for an agent/session."""
        key = self._execution_context_key(agent_id, session_id)
        return dict(self._active_execution_context.get(key, {}))

    async def activate_execution_context(
        self,
        skill_name: str,
        agent_id: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """Resolve and store a skill's execution context for one agent/session."""
        if not agent_id:
            return {}

        resolved_context = await self.resolve_skill_execution_context(skill_name)
        if not resolved_context:
            return self.get_active_execution_context(agent_id, session_id)

        key = self._execution_context_key(agent_id, session_id)
        merged_context = {
            **self._active_execution_context.get(key, {}),
            **resolved_context,
        }
        self._active_execution_context[key] = merged_context
        self._active_execution_context.move_to_end(key)
        if len(self._active_execution_context) > self._active_execution_context_max:
            self._active_execution_context.popitem(last=False)

        return dict(merged_context)

    def _wrap_skill_content(self, content: Any) -> str:
        """Wrap skill content in structured XML tags."""
        return self._wrap_skill_content_body(content, content.body)

    def _wrap_skill_content_body(self, content: Any, body: str) -> str:
        """Wrap skill content with a pre-supplied body string."""
        parts = [f'<skill_content name="{content.metadata.name}">']
        parts.append(body)

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
            if name in self._builtin_skills:
                scope = "builtin"
            elif name in self.public_skills:
                scope = "public"
            else:
                scope = "private"
            result.append(
                {
                    "name": skill.name,
                    "description": skill.description,
                    "scope": scope,
                    "has_scripts": any(r.startswith("scripts/") for r in self._get_resources(name)),
                    "resource_count": len(self._get_resources(name)),
                    "has_execution_context": bool(skill.execution_context),
                }
            )
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
