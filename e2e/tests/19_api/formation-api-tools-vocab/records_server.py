#!/usr/bin/env python3
"""Stdio MCP stub with a semantic-tool catalog for tool-filter e2e tests.

Six tools spanning read / write / destructive verbs so the registry-level
allow+deny block, the agent-attachment override, and the group-level
cascade each have something distinct to act on. Responses are canned --
the tests only assert on tool *visibility*, not behaviour.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("records")


@mcp.tool()
def get_records(record_id: str = "all") -> str:
    """Get one record (or all records) from the records store."""
    return f"records for {record_id}: [alpha, beta]"


@mcp.tool()
def list_records() -> str:
    """List record identifiers in the records store."""
    return "record ids: [1, 2, 3]"


@mcp.tool()
def search_records(query: str) -> str:
    """Search records matching a query string."""
    return f"no records match {query!r}"


@mcp.tool()
def create_record(payload: str) -> str:
    """Create a new record from a payload string."""
    return f"created record from {payload!r}"


@mcp.tool()
def delete_records(record_id: str) -> str:
    """Delete a record by id (destructive)."""
    return f"deleted record {record_id}"


@mcp.tool()
def drop_database() -> str:
    """Drop the entire records database (destructive)."""
    return "database dropped"


if __name__ == "__main__":
    mcp.run()
