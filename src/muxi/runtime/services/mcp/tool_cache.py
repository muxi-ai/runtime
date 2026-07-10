# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        MCP Tool Result Cache
# Description:  Short-lived in-process cache for MCP tool invocation results
# Role:         Reduces redundant remote tool calls during a single workflow
# Usage:        Wrapped by Agent.invoke_tool around MCP service calls
#
# This module provides a small, deliberately conservative response cache for
# MCP tool invocations. The cache is keyed on a deterministic combination of
# formation_id, tool_name, server_id, user_id, and a canonical hash of the
# tool parameters. It never caches mutating tools (writes, sends, deletes),
# error responses, or built-in artifact / skill tools that always have side
# effects.
#
# Design intent:
#   * Match the LLM response cache pattern (module-level dict, MD5 key, TTL).
#   * Default-deny: an unknown tool name is treated as non-cacheable so we
#     can never silently serve stale data for a write/mutator we forgot to
#     classify.
#   * Formation-scoped: keys carry the formation_id so two formations running
#     in the same process never share results, even if their MCP setups are
#     identical.
#   * User-scoped: keys carry user_id so per-user tools (mailboxes, vaults,
#     anything credential-bound) cannot cross-contaminate.
#   * Process-local only: no Redis, no shared store. The cache is entirely
#     ephemeral and dies with the runtime process.
#
# This is intentionally a thin module rather than a class; it follows the
# same style as services.llm.llm._response_cache to keep the mental model
# consistent across services.
# =============================================================================

import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

# 5 minute TTL matches the LLM response cache window. Tool calls in the
# same chat session are typically completed within this window, while
# anything older is unlikely to still be relevant.
_TOOL_CACHE_TTL = 300

# (timestamp, value) — we use a tuple to keep parity with the LLM cache.
_tool_cache: Dict[str, Tuple[float, Any]] = {}

# Lightweight in-process counters for observability; never persisted.
_stats = {
    "hits": 0,
    "misses": 0,
    "stores": 0,
    "skipped": 0,
}

# Tools that always have side effects and must never be cached.
_NEVER_CACHE_NAMES = frozenset(
    {
        "generate_file",  # always produces a fresh artifact
        "activate_skill",  # state mutation on the skill manager
        "run_skill",  # arbitrary code execution
        "delegate_coding",  # spawns a tracked background delegation
    }
)

# Verb tokens that strongly imply a write / mutation. Matched against
# the first (and any) underscore-separated token of the tool name to
# avoid substring false positives like "_add" matching "address".
_MUTATOR_VERBS = frozenset(
    {
        "create",
        "update",
        "delete",
        "remove",
        "write",
        "send",
        "post",
        "push",
        "modify",
        "edit",
        "upload",
        "save",
        "store",
        "insert",
        "execute",
        "set",
        "add",
        "run",
        "do",
        "make",
        "build",
        "submit",
        "publish",
        "rename",
        "move",
        "copy",  # copy mutates the target side
        "patch",
        "drop",
        "destroy",
        "purge",
        "kill",
        "stop",
        "start",
        "restart",
        "trigger",
        "dispatch",
        "emit",
    }
)

# Verb tokens that strongly imply a safe read.
_READ_VERBS = frozenset(
    {
        "read",
        "get",
        "list",
        "search",
        "fetch",
        "query",
        "find",
        "lookup",
        "view",
        "show",
        "retrieve",
        "describe",
        "browse",
        "scan",
        "inspect",
        "head",
        "peek",
        "stat",
        "ls",
        "cat",
        "info",
        "count",
        "status",
        "check",
        "validate",
        "verify",
        "test",
        "ping",
        "exists",
    }
)


def _tokenize(name: str) -> List[str]:
    """Tokenize snake_case and camelCase names into lowercase tokens.

    Examples:
        read_file       -> ["read", "file"]
        readFile        -> ["read", "file"]
        github_listRepo -> ["github", "list", "repo"]
        lookup_address  -> ["lookup", "address"]
    """
    # Convert camelCase boundaries into underscores, then split.
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name)
    return [t for t in snake.lower().split("_") if t]


def is_cacheable(tool_name: Optional[str]) -> bool:
    """Determine whether a tool's result is safe to cache.

    The classifier inspects the leading verb token first (most MCP tool
    names follow a verb_object convention) and falls back to scanning
    all tokens. Mutator verbs take precedence over read verbs so a name
    like ``create_list`` is correctly treated as a mutator.

    Default-deny: tools matching neither vocabulary are not cached.
    Skipping cache only costs latency; serving a stale write result
    can produce incorrect application behavior.
    """
    if not tool_name:
        return False

    if tool_name in _NEVER_CACHE_NAMES:
        return False

    tokens = _tokenize(tool_name)
    if not tokens:
        return False

    # Leading verb is the strongest signal.
    if tokens[0] in _MUTATOR_VERBS:
        return False
    if tokens[0] in _READ_VERBS:
        return True

    # Fallback: any non-leading mutator token still disqualifies (e.g.
    # "github_create_issue" — "github" is the namespace, "create" is
    # the verb). Mutators always win over reads.
    for t in tokens[1:]:
        if t in _MUTATOR_VERBS:
            return False
    for t in tokens[1:]:
        if t in _READ_VERBS:
            return True

    return False


def make_key(
    formation_id: str,
    tool_name: str,
    parameters: Optional[Dict[str, Any]],
    server_id: Optional[str],
    user_id: Optional[Any],
) -> str:
    """Compute a deterministic cache key from invocation context.

    Parameters are canonicalized via JSON with sorted keys so dict ordering
    differences (which Python preserves but doesn't otherwise normalize)
    don't produce cache misses for semantically identical calls.
    """
    try:
        canonical_params = json.dumps(parameters or {}, sort_keys=True, default=str)
    except (TypeError, ValueError):
        # If parameters contain something we cannot serialize deterministically,
        # treat the call as non-cacheable by returning a unique key.
        return f"uncacheable:{time.time_ns()}"

    raw = "|".join(
        [
            formation_id or "default",
            tool_name or "",
            server_id or "",
            str(user_id) if user_id is not None else "",
            canonical_params,
        ]
    )
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def get(key: str) -> Optional[Any]:
    """Retrieve a cached result if present and unexpired."""
    entry = _tool_cache.get(key)
    if entry is None:
        _stats["misses"] += 1
        return None

    timestamp, value = entry
    if time.time() - timestamp > _TOOL_CACHE_TTL:
        # Expired — drop and report a miss so the caller refetches.
        del _tool_cache[key]
        _stats["misses"] += 1
        return None

    _stats["hits"] += 1
    return value


def set(
    key: str, value: Any
) -> None:  # noqa: A001 (shadowing builtin is intentional / module-scoped)
    """Store a result with the current timestamp."""
    _tool_cache[key] = (time.time(), value)
    _stats["stores"] += 1


def note_skipped() -> None:
    """Record that a call bypassed the cache (mutator / non-cacheable)."""
    _stats["skipped"] += 1


def stats() -> Dict[str, int]:
    """Return a copy of the running counters."""
    return dict(_stats)


def clear() -> None:
    """Reset cache + counters. Used by tests and runtime shutdown hooks."""
    _tool_cache.clear()
    for k in _stats:
        _stats[k] = 0


def size() -> int:
    """Return the number of currently cached entries (for tests)."""
    return len(_tool_cache)
