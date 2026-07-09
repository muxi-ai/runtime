#!/usr/bin/env python3
"""One-file stdio request middleware for MUXI formations.

This is the shipped template example for the formation ``middleware:``
block (request-middleware PRD): an MCP server over stdio exposing exactly
one tool named ``middleware``. It receives the full request payload
(user_id, message, attachments, metadata, route_class -- never groups
inbound) and returns the same-shaped payload with ``groups`` attached
from a static user -> groups map.

Declare it in formation.afs:

    middleware:
      command: "./middleware.py"
      timeout: 2s

    rbac:
      fallback: false          # or a group name, e.g. "public"

Replace the map (or the lookup) with whatever your organization uses --
your DB, WorkOS, LDAP. Respond fast: the runtime never caches middleware
answers; caching is this process's job if it needs one.

Optionally pass ``args: ["--map", "groups.json"]`` to read the user ->
groups map from a JSON file next to the formation instead of the
embedded example map. This is also how the runtime's e2e suite uses this
exact file as its test fixture.

Only the Python standard library is used. The stdio framing is
newline-delimited JSON-RPC 2.0, per the MCP specification.
"""

import argparse
import json
import os
import sys

# ---------------------------------------------------------------------
# Membership source: a static map, the simplest possible resolver.
# ---------------------------------------------------------------------

EXAMPLE_GROUPS = {
    "alice@example.com": ["hr"],
    "bob@example.com": ["finance"],
    "carol@example.com": ["engineering"],
    "dave@example.com": ["engineering", "project-atlas"],
}

# The request payload contract. groups is response-only.
PAYLOAD_FIELDS = ("user_id", "message", "attachments", "metadata", "route_class")

TOOL = {
    "name": "middleware",
    "description": (
        "Transforms a MUXI request payload: attaches the caller's groups "
        "from a static membership map."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "message": {"type": "string"},
            "attachments": {"type": "array", "items": {"type": "object"}},
            "metadata": {"type": "object"},
            "route_class": {"type": "string"},
        },
        "required": list(PAYLOAD_FIELDS),
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "message": {"type": "string"},
            "attachments": {"type": "array", "items": {"type": "object"}},
            "metadata": {"type": "object"},
            "route_class": {"type": "string"},
            "groups": {"type": "array", "items": {"type": "string"}},
        },
        "required": list(PAYLOAD_FIELDS),
    },
}


def transform(arguments, groups_map):
    """The middleware itself: request payload in, request payload out."""
    payload = {field: arguments.get(field) for field in PAYLOAD_FIELDS}
    groups = groups_map.get(str(payload.get("user_id") or "").lower().strip(), [])
    if groups:
        payload["groups"] = list(groups)
    return payload


# ---------------------------------------------------------------------
# Minimal MCP stdio server (JSON-RPC 2.0, newline-delimited)
# ---------------------------------------------------------------------


def load_groups_map(map_path):
    """Load the user -> groups map.

    Read on EVERY call when a --map file is given: the runtime never
    caches middleware answers, and neither does this template -- editing
    the map takes effect on the next request.
    """
    groups_map = EXAMPLE_GROUPS
    if map_path:
        with open(map_path, "r", encoding="utf-8") as fh:
            groups_map = json.load(fh)
    return {str(k).lower().strip(): v for k, v in groups_map.items()}


def handle(request, map_path):
    """Return the JSON-RPC result for one request, or None for notifications."""
    method = request.get("method")

    if method == "initialize":
        params = request.get("params") or {}
        return {
            "protocolVersion": params.get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "muxi-middleware-template", "version": "1.0.0"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [TOOL]}
    if method == "tools/call":
        params = request.get("params") or {}
        if params.get("name") != "middleware":
            raise ValueError(f"unknown tool: {params.get('name')!r}")
        payload = transform(params.get("arguments") or {}, load_groups_map(map_path))
        return {
            "content": [{"type": "text", "text": json.dumps(payload)}],
            "structuredContent": payload,
            "isError": False,
        }
    raise ValueError(f"unsupported method: {method!r}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--map",
        dest="map_path",
        default=None,
        help="Path to a JSON file mapping user_id -> [group, ...] "
        "(defaults to the embedded example map)",
    )
    args = parser.parse_args()

    map_path = args.map_path
    if map_path and not os.path.isabs(map_path):
        # Resolve relative to this script so the formation directory is
        # the natural home for the map file.
        map_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), map_path)
    load_groups_map(map_path)  # fail fast on a missing/invalid map

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            continue
        request_id = request.get("id")
        if request_id is None:
            continue  # notification (e.g. notifications/initialized)
        response = {"jsonrpc": "2.0", "id": request_id}
        try:
            response["result"] = handle(request, map_path)
        except Exception as e:  # malformed request -> JSON-RPC error
            response["error"] = {"code": -32601, "message": str(e)}
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
