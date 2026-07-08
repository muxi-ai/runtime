"""
Slash command parsing and resolution (Proactiveness Phase 1).

Mechanism only: this module parses ``/command arguments`` messages and
resolves them against formation SOPs (every SOP is implicitly a command)
plus a built-in command registry that ships empty in Phase 1 (built-in
commands like ``/help`` and ``/jobs`` are a later phase; the registry is
the extension point they plug into).

The feature is opt-in via the formation-level ``commands:`` block:

    commands:
      enabled: true              # default true when the block is present
      aliases:
        tasks: weekly-report     # /tasks resolves like /weekly-report

Formations without a ``commands:`` block are completely unaffected:
``parse_commands_config`` returns None and messages that merely start
with ``/`` flow to the LLM unchanged.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

# A slash command is "/" + name + optional whitespace-separated arguments.
# The name charset matches trigger/transformer names; anything else (e.g.
# a filesystem path like "/usr/bin/env" or a lone "/") is NOT a command
# and flows through as a normal message.
_COMMAND_PATTERN = re.compile(r"^/([a-zA-Z0-9_-]+)(?:\s+(.*))?$", re.DOTALL)

_ALLOWED_COMMANDS_KEYS = {"enabled", "aliases"}
_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

# Extension point for built-in runtime commands (Phase 3 of the PRD).
# Maps command name -> handler; intentionally empty in Phase 1.
BUILTIN_COMMANDS: Dict[str, Callable] = {}


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


@dataclass
class CommandResolution:
    """The outcome of resolving a parsed command against the formation."""

    name: str  # Canonical command name after alias expansion
    message: str  # Message to run through the normal chat flow
    model: Optional[str] = None  # SOP-level model override
    bypass_approval: bool = False  # SOP-level workflow approval bypass


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

    return CommandsConfig(enabled=enabled, aliases=aliases)


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
    Resolve a parsed command against built-ins and formation SOPs.

    Resolution order (per the PRD): built-in commands first, then
    formation SOPs by name. Aliases are expanded before lookup.

    Args:
        command: The parsed slash command
        config: The formation's commands configuration
        sops: The formation's loaded SOPs (``overlord.sop_system.sops``)

    Returns:
        CommandResolution when the command matches an SOP, or None for
        unknown commands. Built-in handlers are a later phase; a matching
        BUILTIN_COMMANDS entry resolves to whatever message the handler
        returns.
    """
    name = config.aliases.get(command.name, command.name)

    builtin = BUILTIN_COMMANDS.get(name)
    if builtin is not None:
        return builtin(command)

    sop = (sops or {}).get(name)
    if sop is None:
        return None

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


def available_commands(
    config: CommandsConfig, sops: Optional[Dict[str, Dict[str, Any]]] = None
) -> Dict[str, str]:
    """
    List available commands (for unknown-command help and SDK listings).

    Returns:
        Dict of command name -> description (aliases included, pointing at
        their target's description)
    """
    commands: Dict[str, str] = {}
    for name in BUILTIN_COMMANDS:
        commands[name] = "built-in command"
    for sop_id, sop in (sops or {}).items():
        commands[sop_id] = sop.get("description") or ""
    for alias, target in config.aliases.items():
        if target in commands and alias not in commands:
            commands[alias] = commands[target]
    return commands
