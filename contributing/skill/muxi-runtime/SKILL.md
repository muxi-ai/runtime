---
name: muxi-runtime
description: >
  Deep knowledge of the MUXI Runtime codebase (Python, ~300 files, ~119K lines).
  Use when working on runtime code: formations, overlord, memory systems,
  LLM layer, MCP, observability, scheduler, secrets, server/API, skills, RCE,
  or e2e tests. Knows initialization order, data flows, gotchas, and testing patterns.
license: Apache-2.0
metadata:
  author: ran
  version: "1.1"
---

# MUXI Runtime

The MUXI Runtime is the Python formation execution environment -- FastAPI-based,
packaged as SIF containers. Repo root: the current working directory (or wherever
the `mental-model.md` and `AGENTS.md` files live).

## Primary Source of Truth

**Before doing any work on the runtime codebase, read these two files:**

1. **`mental-model.md`** (~3800 lines) -- complete architectural mental model:
   - Formation lifecycle, initialization order, key methods
   - Overlord architecture, chat flow, agent routing, clarification
   - Memory system (working, persistent, memobase, embeddings)
   - LLM layer (OneLLM, capabilities, caching, resilience)
   - MCP system (transports, tool execution, credential resolution)
   - Server/API (FastAPI, routes, auth, streaming)
   - Observability (349 events, two-tier logging, transports)
   - Other services (scheduler, secrets, A2A, telemetry)
   - Skills system (parser, SkillManager, catalog injection, isolation model)
   - RCE client (hash-based caching, warm-up, run_skill dispatch)
   - Testing infrastructure (E2E Docker, 21 test areas, patterns)
   - Key data flows (request processing, formation loading, secrets)
   - Lessons Learned appendix (real bugs and fixes from E2E testing)

2. **`AGENTS.md`** -- coding standards, testing discipline, workflow rules,
   troubleshooting cheatsheet, and hard rules checklist.

## When to Consult What

| Task | Read |
|------|------|
| Understanding a subsystem | `mental-model.md` -- find the relevant section |
| Adding/modifying a service | `mental-model.md` Section 1 (init order) + relevant section |
| Debugging a failure | `mental-model.md` Lessons Learned appendix |
| Writing tests | `mental-model.md` Section 9 (testing) + `AGENTS.md` testing standards |
| Code style, conventions | `AGENTS.md` |
| E2E test setup | `mental-model.md` Section 9 (Docker services, patterns, secrets) |

## Quick Navigation (mental-model.md sections)

1. Formation Lifecycle -- `load()`, `_prepare_services()`, initialization order
2. Overlord Architecture -- `chat()` flow, routing, clarification two-level lookup
3. Memory System -- three-tier architecture, embedding resolution, memobase
4. LLM Layer -- OneLLM, capability resolution, cache, resilience
5. MCP System -- transports, tool execution, credential resolution flow
6. Server / API -- FastAPI routes, auth, streaming, conversation logging
7. Observability -- event system, EventLogger, transports, validation
8. Other Services -- scheduler, A2A, secrets, streaming, telemetry
9. Testing Infrastructure -- E2E Docker, 21 areas, 3 test patterns
10. Key Data Flows -- full request-to-response, formation load, secrets interpolation
Appendix: Lessons Learned -- indexed by date, real bugs and their fixes

## Running Tests

- **Unit tests:** `python3 -m pytest tests/unit/ -q`
- **E2E tests:** Standalone scripts (not pytest). Use `cd e2e && python run_all_tests.py`
  or `cd e2e/tests/<area> && python test_<name>.py` for individual tests.
- **Lint/format:** Black (line length 100), isort (profile=black), Ruff & Flake8 (line length 120)
