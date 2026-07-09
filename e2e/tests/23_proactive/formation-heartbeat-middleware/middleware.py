#!/usr/bin/env python3
"""Stdio middleware fixture with call auditing for the heartbeat e2e.

Same shape as the shipped template (contributing/templates/middleware.py)
plus one organization-flavored addition: every transformed request is
appended to ``middleware_calls.log`` next to this script as
``<route_class> <user_id>`` -- how the heartbeat e2e proves that
internally-originated requests traverse the middleware pipeline exactly
like external traffic.
"""

import json
import os
import sys

GROUPS = {
    "heartbeat-user": ["staff"],
    # "ghost-user" is deliberately absent: its heartbeat must be
    # rejected by rbac (fallback: false)
}

PAYLOAD_FIELDS = ("user_id", "message", "attachments", "metadata", "route_class")
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "middleware_calls.log")

TOOL = {
    "name": "middleware",
    "description": "Attaches groups from a static map and audits every call.",
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
}


def transform(arguments):
    payload = {field: arguments.get(field) for field in PAYLOAD_FIELDS}
    user_id = str(payload.get("user_id") or "").lower().strip()
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(f"{payload.get('route_class')} {user_id}\n")
    groups = GROUPS.get(user_id, [])
    if groups:
        payload["groups"] = list(groups)
    return payload


def handle(request):
    method = request.get("method")
    if method == "initialize":
        params = request.get("params") or {}
        return {
            "protocolVersion": params.get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "heartbeat-middleware-fixture", "version": "1.0.0"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [TOOL]}
    if method == "tools/call":
        params = request.get("params") or {}
        if params.get("name") != "middleware":
            raise ValueError(f"unknown tool: {params.get('name')!r}")
        payload = transform(params.get("arguments") or {})
        return {
            "content": [{"type": "text", "text": json.dumps(payload)}],
            "structuredContent": payload,
            "isError": False,
        }
    raise ValueError(f"unsupported method: {method!r}")


def main():
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
            continue
        response = {"jsonrpc": "2.0", "id": request_id}
        try:
            response["result"] = handle(request)
        except Exception as e:
            response["error"] = {"code": -32601, "message": str(e)}
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
