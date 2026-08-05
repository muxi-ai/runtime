#!/usr/bin/env python3
"""Deterministic failure-injection MCP server for async retry escalation e2e.

Exposes one tool, ``system_status_report``. Behavior is controlled by a
filesystem flag so the TEST decides when the "outage" ends -- no
randomness, no external services:

- control file ABSENT  -> the tool stalls (simulated outage). The
  formation's task_timeout is far shorter, so the executing task fails
  deterministically with a timeout -- an error that is retryable (it
  matches none of the non_replannable_error_patterns).
- control file PRESENT -> the tool returns instantly with a recognizable
  payload (RECOVERED-OK), so the escalated background attempt succeeds.

Each request is served on its own thread, so a stalled tools/call never
blocks later calls from the retry attempt.

The control file path is passed as argv[1] by the mcp server config.
"""

import json
import sys
import threading
import time
from pathlib import Path

CONTROL_FILE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/muxi_e2e_retry_control")
STALL_SECONDS = 90.0

_write_lock = threading.Lock()

TOOL = {
    "name": "system_status_report",
    "description": (
        "Fetch the current system status report from the monitoring endpoint. "
        "This is the only source of the system status."
    ),
    "inputSchema": {"type": "object", "properties": {}, "required": []},
}


def handle(request):
    method = request.get("method")
    if method == "initialize":
        params = request.get("params") or {}
        return {
            "protocolVersion": params.get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "report-tools", "version": "1.0.0"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [TOOL]}
    if method == "tools/call":
        if CONTROL_FILE.exists():
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "SYSTEM STATUS REPORT: all services operational. "
                            "verification-token=RECOVERED-OK"
                        ),
                    }
                ],
                "isError": False,
            }
        # Simulated outage: stall well past the formation's task_timeout so
        # the task fails deterministically by timeout (a retryable error).
        # Poll the control file so a mid-stall recovery still answers.
        deadline = time.time() + STALL_SECONDS
        while time.time() < deadline:
            if CONTROL_FILE.exists():
                return handle(request)
            time.sleep(0.5)
        return {
            "content": [
                {"type": "text", "text": "status endpoint unavailable: upstream timed out"}
            ],
            "isError": True,
        }
    raise ValueError(f"unsupported method: {method!r}")


def respond(request):
    request_id = request.get("id")
    if request_id is None:
        return  # notification (e.g. notifications/initialized)
    response = {"jsonrpc": "2.0", "id": request_id}
    try:
        response["result"] = handle(request)
    except Exception as e:
        response["error"] = {"code": -32601, "message": str(e)}
    with _write_lock:
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            continue
        threading.Thread(target=respond, args=(request,), daemon=True).start()


if __name__ == "__main__":
    main()
