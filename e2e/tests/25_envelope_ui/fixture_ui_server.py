#!/usr/bin/env python3
"""One-file stdio MCP server returning an MCP Apps UI resource.

The fixture for the mcp_resource passthrough tests (Response Envelope
UI, P2): ``show_dashboard`` returns a text summary block for the model
PLUS an embedded resource whose URI uses the ``ui://`` scheme — the MCP
Apps convention for UI resources. The runtime must relay the resource
verbatim to the client as an ``mcp_resource`` widget and keep its
content out of the LLM-visible text.

Flags:
    --resource-bytes N    pad the UI resource to at least N bytes
                          (default 0 = the plain document; used by the
                          oversized-clamp test)

Only the Python standard library is used. The stdio framing is
newline-delimited JSON-RPC 2.0, per the MCP specification (the same
skeleton as the 26_watch fixture).
"""

import argparse
import json
import sys

DASHBOARD_URI = "ui://dashboard/sales.html"
DASHBOARD_MIME = "text/html"
DASHBOARD_HTML = (
    "<!doctype html><html><body><h1>Sales Dashboard</h1>"
    "<p>Revenue up 5% this quarter.</p>"
    "<div id='chart'>FIXTURE-CHART-7f3a</div></body></html>"
)
SUMMARY_TEXT = (
    "Dashboard summary: revenue is up 5% this quarter; " "3 of 4 regions are above target."
)

TOOLS = [
    {
        "name": "show_dashboard",
        "description": (
            "Show the sales dashboard. Returns a text summary of the "
            "current sales figures (and an interactive view for capable "
            "clients)."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    }
]


def dashboard_html(resource_bytes):
    """The fixture document, padded to at least ``resource_bytes``."""
    html = DASHBOARD_HTML
    if resource_bytes > len(html):
        html += "<!--" + "x" * (resource_bytes - len(html)) + "-->"
    return html


def handle(request, resource_bytes):
    method = request.get("method")
    if method == "initialize":
        params = request.get("params") or {}
        return {
            "protocolVersion": params.get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fixture-ui-server", "version": "1.0.0"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        params = request.get("params") or {}
        if params.get("name") != "show_dashboard":
            raise ValueError(f"unknown tool: {params.get('name')!r}")
        return {
            "content": [
                {"type": "text", "text": SUMMARY_TEXT},
                {
                    "type": "resource",
                    "resource": {
                        "uri": DASHBOARD_URI,
                        "mimeType": DASHBOARD_MIME,
                        "text": dashboard_html(resource_bytes),
                    },
                },
            ],
            "isError": False,
        }
    raise ValueError(f"unsupported method: {method!r}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource-bytes", type=int, default=0)
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
            response["result"] = handle(request, args.resource_bytes)
        except Exception as e:  # malformed request -> JSON-RPC error
            response["error"] = {"code": -32601, "message": str(e)}
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
