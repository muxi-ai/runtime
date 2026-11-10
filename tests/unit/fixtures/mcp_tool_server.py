#!/usr/bin/env python3
"""A small FastMCP server for the MCP transport tests.

Usage: mcp_tool_server.py stdio
       mcp_tool_server.py http|sse PORT

Tools:
- ``echo(text)`` returns ``text``.
- ``request_auth()`` returns the Authorization and X-API-Key headers the
  server received, so a test can see what the client sent.
- ``sleep(seconds)`` returns after ``seconds``, for timeout tests.
"""

import asyncio
import sys

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers

mcp = FastMCP("transport-test")


@mcp.tool
def echo(text: str) -> str:
    return text


@mcp.tool
def request_auth() -> dict:
    headers = get_http_headers(include={"authorization"})
    return {
        "authorization": headers.get("authorization", ""),
        "x-api-key": headers.get("x-api-key", ""),
    }


@mcp.tool
async def sleep(seconds: float) -> str:
    await asyncio.sleep(seconds)
    return "done"


if __name__ == "__main__":
    transport = sys.argv[1]
    if transport == "stdio":
        mcp.run(transport="stdio", show_banner=False)
    else:
        mcp.run(
            transport=transport,
            host="127.0.0.1",
            port=int(sys.argv[2]),
            show_banner=False,
            log_level="warning",
        )
