#!/usr/bin/env python3
"""One-file stdio MCP server simulating an async job service.

The fixture for the 26_watch e2e area (remote async tools): ``submit``
returns a job handle immediately (``{"job_id": ..., "status":
"queued"}``) and ``check_status`` flips to ``succeeded`` after N status
checks. The runtime uses ephemeral connections (a fresh process per
call), so job state lives in a JSON file passed via ``--state``.

Flags:
    --state PATH          job-state JSON file (required)
    --polls-to-done N     checks before a job reports succeeded
                          (default 2; 0 = never succeeds -- timeout tests)

Only the Python standard library is used. The stdio framing is
newline-delimited JSON-RPC 2.0, per the MCP specification (the same
skeleton as the shipped middleware template).
"""

import argparse
import json
import os
import sys

RESULT_URL = "https://img.fixture/fox.png"

TOOLS = [
    {
        "name": "submit",
        "description": (
            "Submit a render job. Returns immediately with a job identifier "
            "and a non-terminal status; poll check_status for the result."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"prompt": {"type": "string"}},
            "required": ["prompt"],
        },
    },
    {
        "name": "check_status",
        "description": (
            "Check the status of a submitted render job. Returns "
            "{status: queued|processing|succeeded, output?: url}."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    },
]


def load_state(path):
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (ValueError, OSError):
            return {}
    return {}


def save_state(path, state):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh)


def call_tool(name, arguments, state_path, polls_to_done):
    state = load_state(state_path)
    if name == "submit":
        job_id = f"job-{len(state) + 1}"
        state[job_id] = {"prompt": str(arguments.get("prompt", "")), "checks": 0}
        save_state(state_path, state)
        return {"job_id": job_id, "status": "queued"}
    if name == "check_status":
        job_id = str(arguments.get("job_id", ""))
        if job_id not in state:
            raise ValueError(f"unknown job: {job_id!r}")
        state[job_id]["checks"] += 1
        save_state(state_path, state)
        checks = state[job_id]["checks"]
        if polls_to_done > 0 and checks >= polls_to_done:
            return {
                "status": "succeeded",
                "output": RESULT_URL,
                "prompt": state[job_id]["prompt"],
                "checks": checks,
            }
        return {"status": "processing", "checks": checks}
    raise ValueError(f"unknown tool: {name!r}")


def handle(request, state_path, polls_to_done):
    method = request.get("method")
    if method == "initialize":
        params = request.get("params") or {}
        return {
            "protocolVersion": params.get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fixture-job-server", "version": "1.0.0"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        params = request.get("params") or {}
        payload = call_tool(
            params.get("name"), params.get("arguments") or {}, state_path, polls_to_done
        )
        return {
            "content": [{"type": "text", "text": json.dumps(payload)}],
            "structuredContent": payload,
            "isError": False,
        }
    raise ValueError(f"unsupported method: {method!r}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, help="job-state JSON file")
    parser.add_argument("--polls-to-done", type=int, default=2)
    args = parser.parse_args()

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
            response["result"] = handle(request, args.state, args.polls_to_done)
        except Exception as e:  # malformed request -> JSON-RPC error
            response["error"] = {"code": -32601, "message": str(e)}
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
