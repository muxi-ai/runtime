#!/usr/bin/env python3
"""A deliberately misbehaving stdio middleware for fail-closed e2e tests.

Modes (mutually exclusive flags):
  (default)     valid handshake + contract, but every tools/call returns
                an error -- the runtime must reject the request (fail
                closed; rbac.fallback must NOT apply)
  --bad-tool    exposes a tool named 'transform' instead of 'middleware'
                -- the formation must FAIL to load (contract check)
  --malformed   tools/call returns a payload violating the request schema
                -- the runtime must reject the request (fail closed)
"""

import argparse
import json
import sys

PAYLOAD_FIELDS = ("user_id", "message", "attachments", "metadata", "route_class")


def tool_definition(name):
    properties = {
        "user_id": {"type": "string"},
        "message": {"type": "string"},
        "attachments": {"type": "array", "items": {"type": "object"}},
        "metadata": {"type": "object"},
        "route_class": {"type": "string"},
    }
    return {
        "name": name,
        "description": "Misbehaving middleware for fail-closed testing.",
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": list(PAYLOAD_FIELDS),
        },
    }


def handle(request, mode):
    method = request.get("method")
    if method == "initialize":
        params = request.get("params") or {}
        return {
            "protocolVersion": params.get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "broken-middleware", "version": "1.0.0"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        name = "transform" if mode == "bad-tool" else "middleware"
        return {"tools": [tool_definition(name)]}
    if method == "tools/call":
        if mode == "malformed":
            payload = {"verdict": "allow"}  # not the request schema
            return {
                "content": [{"type": "text", "text": json.dumps(payload)}],
                "structuredContent": payload,
                "isError": False,
            }
        return {
            "content": [{"type": "text", "text": "identity provider outage (simulated)"}],
            "isError": True,
        }
    raise ValueError(f"unsupported method: {method!r}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bad-tool", action="store_true")
    parser.add_argument("--malformed", action="store_true")
    args = parser.parse_args()
    mode = "bad-tool" if args.bad_tool else ("malformed" if args.malformed else "error")

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
            response["result"] = handle(request, mode)
        except Exception as e:
            response["error"] = {"code": -32601, "message": str(e)}
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
