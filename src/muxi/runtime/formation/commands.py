"""
Slash command parsing and resolution (Proactiveness Phases 1 and 3).

Mechanism only: this module parses ``/command arguments`` messages and
resolves them against formation SOPs (every SOP is implicitly a command)
plus the ``BUILTIN_COMMANDS`` registry of runtime commands (``/help``,
``/jobs``, ...). Built-in handlers live in ``builtin_commands.py`` and are
loaded lazily on first resolution.

The feature is opt-in via the formation-level ``commands:`` block:

    commands:
      enabled: true              # default true when the block is present
      aliases:
        tasks: jobs              # /tasks resolves like /jobs
      builtin:
        reset: false             # hide a specific built-in command

Formations without a ``commands:`` block are completely unaffected:
``parse_commands_config`` returns None and messages that merely start
with ``/`` flow to the LLM unchanged.

Resolution precedence (after alias expansion): formation SOPs first, then
built-ins. A formation SOP with the same name as a built-in shadows it --
formation-author overrides always win (deliberate deviation from the PRD
sketch, which checked built-ins first; shadowing plus the ``builtin:``
disable map gives authors full control without any new mechanism).
"""

import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional

# A slash command is "/" + name + optional whitespace-separated arguments.
# The name charset matches trigger/transformer names; anything else (e.g.
# a filesystem path like "/usr/bin/env" or a lone "/") is NOT a command
# and flows through as a normal message.
_COMMAND_PATTERN = re.compile(r"^/([a-zA-Z0-9_-]+)(?:\s+(.*))?$", re.DOTALL)

_ALLOWED_COMMANDS_KEYS = {"enabled", "aliases", "builtin"}
_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


@dataclass
class BuiltinCommand:
    """A built-in runtime slash command.

    ``handler`` is an async callable receiving a ``BuiltinCommandContext``
    (defined in ``builtin_commands.py``) and returning the plain-text reply
    (text-only in v1). Handlers must be deterministic (no LLM round-trip)
    and only touch the calling user's own state.
    """

    name: str
    description: str
    usage: str  # One-line usage hint shown by /help (e.g. "/jobs [pause <id>]")
    handler: Callable[..., Awaitable[str]]


# Registry of built-in runtime commands (Phase 3 of the proactiveness PRD).
# Populated by ``builtin_commands.py`` at import time; loaded lazily via
# ``_load_builtins`` so importing this module stays dependency-free.
BUILTIN_COMMANDS: Dict[str, BuiltinCommand] = {}

_BUILTINS_LOADED = False


def _load_builtins() -> None:
    """Populate BUILTIN_COMMANDS by importing the handler module once."""
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED:
        return
    _BUILTINS_LOADED = True
    from . import builtin_commands  # noqa: F401  (registers handlers on import)


def register_builtin(command: BuiltinCommand) -> None:
    """Register a built-in command (used by ``builtin_commands.py``)."""
    BUILTIN_COMMANDS[command.name] = command


@dataclass
class ParsedCommand:
    """A parsed slash command."""

    name: str
    args: str = ""


@dataclass
class CommandsConfig:
    """Parsed and validated ``commands:`` formation block."""

    enabled: bool = True
    aliases: Dict[str, str] = field(default_factory=dict)
    # Per-built-in enable map (name -> bool); absent names default to True,
    # so built-ins are available whenever the commands feature is enabled.
    builtin: Dict[str, bool] = field(default_factory=dict)


@dataclass
class CommandResolution:
    """The outcome of resolving a parsed command against the formation."""

    name: str  # Canonical command name after alias expansion
    message: str  # Message to run through the normal chat flow (SOP path)
    model: Optional[str] = None  # SOP-level model override
    bypass_approval: bool = False  # SOP-level workflow approval bypass
    builtin: Optional[BuiltinCommand] = None  # Set when a built-in matched


def builtin_enabled(config: CommandsConfig, name: str) -> bool:
    """Whether a built-in command is enabled for this formation."""
    return bool(config.builtin.get(name, True))


def parse_commands_config(raw: Any) -> Optional[CommandsConfig]:
    """
    Parse the formation-level ``commands:`` block.

    Args:
        raw: The raw ``commands`` value from the formation config (or None)

    Returns:
        CommandsConfig, or None when the block is absent (inert)

    Raises:
        ValueError: On any structural problem, with a descriptive message
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("'commands' must be a mapping")

    unknown = set(raw.keys()) - _ALLOWED_COMMANDS_KEYS
    if unknown:
        raise ValueError(
            f"unknown 'commands' key(s): {sorted(unknown)}. "
            f"Allowed keys: {sorted(_ALLOWED_COMMANDS_KEYS)}"
        )

    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("'commands.enabled' must be a boolean")

    aliases: Dict[str, str] = {}
    raw_aliases = raw.get("aliases") or {}
    if not isinstance(raw_aliases, dict):
        raise ValueError("'commands.aliases' must be a mapping of alias -> command name")
    for alias, target in raw_aliases.items():
        if not isinstance(alias, str) or not _NAME_PATTERN.match(alias):
            raise ValueError(
                f"invalid command alias {alias!r}: must contain only letters, numbers, "
                "hyphens, and underscores"
            )
        if not isinstance(target, str) or not _NAME_PATTERN.match(target):
            raise ValueError(
                f"invalid alias target {target!r} for alias '{alias}': must contain only "
                "letters, numbers, hyphens, and underscores"
            )
        aliases[alias] = target

    builtin: Dict[str, bool] = {}
    raw_builtin = raw.get("builtin") or {}
    if not isinstance(raw_builtin, dict):
        raise ValueError("'commands.builtin' must be a mapping of built-in name -> boolean")
    if raw_builtin:
        _load_builtins()
    for name, value in raw_builtin.items():
        if not isinstance(name, str) or name not in BUILTIN_COMMANDS:
            raise ValueError(
                f"unknown built-in command {name!r} in 'commands.builtin'. "
                f"Built-in commands: {sorted(BUILTIN_COMMANDS)}"
            )
        if not isinstance(value, bool):
            raise ValueError(f"'commands.builtin.{name}' must be a boolean")
        builtin[name] = value

    return CommandsConfig(enabled=enabled, aliases=aliases, builtin=builtin)


def parse_slash_command(message: str) -> Optional[ParsedCommand]:
    """
    Parse a message into a slash command, if it is one.

    A message is a slash command when (after stripping surrounding
    whitespace) it starts with ``/`` followed by a valid command name and
    optionally whitespace plus arguments. Everything else returns None:
    ``/``, ``//x``, ``/usr/bin/env``, and ``/name!`` are all normal
    messages. Arguments may span multiple lines and keep their internal
    formatting.

    Args:
        message: The raw user message

    Returns:
        ParsedCommand, or None when the message is not a slash command
    """
    if not isinstance(message, str):
        return None
    stripped = message.strip()
    if not stripped.startswith("/"):
        return None
    match = _COMMAND_PATTERN.match(stripped)
    if not match:
        return None
    args = (match.group(2) or "").strip()
    return ParsedCommand(name=match.group(1), args=args)


def resolve_command(
    command: ParsedCommand,
    config: CommandsConfig,
    sops: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Optional[CommandResolution]:
    """
    Resolve a parsed command against formation SOPs and built-ins.

    Resolution order: aliases expand first, then formation SOPs by name,
    then the built-in registry. A formation SOP shadows a built-in of the
    same name (formation-author overrides win); a built-in disabled via
    ``commands.builtin`` is invisible.

    Args:
        command: The parsed slash command
        config: The formation's commands configuration
        sops: The formation's loaded SOPs (``overlord.sop_system.sops``)

    Returns:
        CommandResolution, or None for unknown commands. SOP matches carry
        the rewritten chat message; built-in matches carry the
        ``BuiltinCommand`` descriptor for the caller to execute directly
        (no LLM round-trip).
    """
    _load_builtins()
    name = config.aliases.get(command.name, command.name)

    sop = (sops or {}).get(name)
    if sop is not None:
        # Rewrite to an explicit SOP invocation rather than inlining the SOP
        # content: the chat pipeline's request analyzer resolves explicit SOP
        # requests directly (bypassing semantic SOP search), so the named SOP
        # is the one that executes -- inlined content could semantically match
        # a different SOP.
        message = f'Execute the "{name}" SOP.'
        if command.args:
            message = f"{message}\n\nCommand arguments:\n{command.args}"

        return CommandResolution(
            name=name,
            message=message,
            model=sop.get("model"),
            bypass_approval=bool(sop.get("bypass_approval", False)),
        )

    builtin = BUILTIN_COMMANDS.get(name)
    if builtin is not None and builtin_enabled(config, name):
        return CommandResolution(name=name, message="", builtin=builtin)

    return None


def available_commands(
    config: CommandsConfig, sops: Optional[Dict[str, Dict[str, Any]]] = None
) -> Dict[str, str]:
    """
    List available commands (for /help, unknown-command hints, and SDK
    listings).

    Returns:
        Dict of command name -> description. Built-ins appear unless
        disabled; formation SOP descriptions win over a built-in of the
        same name (shadowing). Aliases point at their target's description.
    """
    _load_builtins()
    commands: Dict[str, str] = {}
    for name, builtin in BUILTIN_COMMANDS.items():
        if builtin_enabled(config, name):
            commands[name] = builtin.description
    for sop_id, sop in (sops or {}).items():
        commands[sop_id] = sop.get("description") or ""
    for alias, target in config.aliases.items():
        if target in commands and alias not in commands:
            commands[alias] = commands[target]
    return commands
