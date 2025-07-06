# MCP Tool Calling Tests

This directory contains test files created during the implementation of MCP tool calling functionality in agents.

## Test Files

- `test_agent_tool_calling.py` - Tests agent integration with mock MCP tools
- `test_direct_llm_tools.py` - Tests OneLLM directly with tool calling
- `test_llm_debug.py` - Debug test for LLM service tool handling
- `test_mcp_direct.py` - Direct MCP service testing without formation
- `test_mcp_minimal.py` - Minimal MCP test with formation
- `test_mcp_quick.py` - Quick MCP test for debugging
- `test_simple_mcp.py` - Simple test to verify MCP tools are passed to LLM
- `test_tool_calling_debug.py` - Debug tool calling with both direct LLM and agent

## Purpose

These tests were created during the session on January 5, 2025, to debug and implement MCP tool calling. They demonstrate:

1. How to pass tools to the LLM in OpenAI function calling format
2. How agents discover and format MCP tools
3. How the LLM service handles tool call responses
4. How agents execute tool calls and return results

## Status

The implementation is working - agents now properly invoke MCP tools. These tests can be used as reference for how the tool calling system works.