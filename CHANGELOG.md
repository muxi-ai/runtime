# Changelog

## 0.20260319.0 - Dependency Security & PostgreSQL Fix

### Bug Fixes

- **Missing `asyncpg` dependency** - The async PostgreSQL driver (`asyncpg`) was used in `db.py` but never declared in `pyproject.toml`. In vanilla installs it could be present transitively, but in SIF containers (which only install declared dependencies) it caused an `ImportError` on startup with PostgreSQL persistent memory. Fix: added `asyncpg>=0.29.0` to dependencies. (Fixes #128)

### Security

- **pypdf** bumped to `>=6.9.1` — fixes CVE-2026-33123 (DoS via crafted PDF stream decoding).
- **PyJWT** pinned `>=2.12.0` — fixes CVE-2026-32597 (unknown `crit` header acceptance).
- **pyasn1** pinned `>=0.6.3` — fixes CVE-2026-30922 (unbounded recursion DoS).

### Improvements

- **Proof evidence capture** - E2E test runners (`run_all_tests.py`, `run_random_tests.py`) now capture per-test terminal recordings via `@automaze/proof` CLI, grouped by area with per-area markdown reports. Gracefully degrades when proof CLI is not installed.

## 0.20260313.0 - SQLite Memory & SIF Reliability

### Bug Fixes

- **SQLiteMemory search in single-user mode** - Memory retrieval silently failed because `search()` and `_search_internal()` referenced a nonexistent `default_user_id` attribute. In single-user mode (`user_id=None`), this caused an `AttributeError` caught by a broad `except`, returning empty results. Memories were stored correctly but never retrieved. Fix: when `user_id` is None, search all users in the formation (4-way SQL branching for collection/user combinations).
- **Embedding model missing from SIF** - The `all-MiniLM-L6-v2` model (used by SQLiteMemory for local embeddings) was not pre-downloaded during Docker build. Only `paraphrase-multilingual-MiniLM-L12-v2` was cached. At runtime inside read-only SIF containers, HuggingFace Hub failed with `[Errno 30] Read-only file system`. Fix: pre-download both models at build time.
- **HuggingFace cache writes in read-only SIF** - Even with models pre-downloaded, HuggingFace Hub attempted to write `.no_exist` cache files to `/opt/hf-cache/`, failing on read-only SIF filesystems. Fix: set `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` in the container entrypoint, conditional on running inside a Singularity/Apptainer container (`SINGULARITY_CONTAINER` or `MUXI_SIF_MODE=1`).
- **`auto_decomposition` default override** - The overlord config hardcoded `auto_decomposition=True` at line 2670, overriding the constructor's `False` default. Fix: defaults to `self.enable_workflow_by_default`.
- **sqlite-vec ELFCLASS32 on aarch64** - The `sqlite-vec==0.1.6` PyPI wheel ships a 32-bit ARM binary on aarch64 (known upstream bug). Fix: compile sqlite-vec from amalgamation source (`v0.1.7-alpha.10`) in the Dockerfile builder stage for aarch64.

## 0.20260312.0 - Formation Init Hook & MCP Path Diagnostics

### New Features

- **Formation `init` hook** - New top-level `init:` field runs a shell command before any services are initialized. Use for environment setup: creating directories, installing tools, seeding data. Runs with 120s timeout, cwd = formation directory, fails fast on non-zero exit.
  ```yaml
  init: "mkdir -p /tmp/workspace"
  ```
- **MCP path-existence hints** - When a command-type MCP server fails with "Connection closed", the runtime checks if any args look like filesystem paths that don't exist and prints a diagnostic hint pointing to the `init` hook.

## 0.20260311.0 - Agent Skills & MCP Reliability

### New Features

- **Agent Skills** - Implementation of the [Agent Skills specification](https://agentskills.io/specification). Skills are declared via `SKILL.md` files in `skills/` directories, loaded at startup with progressive disclosure (metadata only until activation), and injected into agent system prompts and planning prompts as a markdown catalog.
  - **Three-layer isolation** ensures agents only see and activate authorized skills: catalog filtering, tool enum restriction, and planning prompt scoping.
  - **Built-in `file-generation` skill** for artifact generation via RCE.
  - **REST API**: `GET /v1/skills`, `GET /v1/skills/{name}`, `GET /v1/agents/{agent_id}/skills`.
- **RCE execution** - Agents can execute skill scripts via a remote code execution server (`muxi/skills-rce`). Hash-based cache busting, zip upload, non-blocking warm-up on startup.
  - New `run_skill` tool registered for agents with script-bearing skills.
  - Formation config: `rce: { url: "http://...", token: "..." }`.

### Improvements

- **MCP streamable HTTP transport timeouts** - All MCP SDK async operations are now wrapped with `asyncio.wait_for()` (30s connect, 10s cleanup). Invalid auth tokens fail in <1s instead of hanging indefinitely.
- **Credential selection flow** - Fixed 7 bugs in multi-credential MCP flows: sync KV operations for pending clarification state, proper credential caching via `_cache_selected_credential` helper, cache-aware clarification skip to prevent re-asking, string/dict type handling for available credentials, and proactive/reactive mode unification.
- **Skill dispatch extraction** - Skill tool handling extracted from `agent.py` into `skill_dispatch.py` for cleaner separation of concerns.

### Bug Fixes

- Fixed `WorkingMemory` truthiness bug: `__len__` returns 0 when buffer is empty, making `not buffer_memory` evaluate True. All guards now use `is None` checks.
- Fixed fire-and-forget `_set_pending_clarification` not completing before response returned to user. Credential paths now use synchronous awaited variants.
- Fixed auth template lookup using non-existent `mcp_svc.servers` instead of `mcp_svc.server_configs[server_id]["stored_credentials"]`.
- Fixed e2e test 4e2 (multi-user permissions): broader assertions, self-contained prompts to avoid security analyzer false positives.
- Fixed e2e test 11_a_2 (format consistency): reduced LLM calls from 12 to 8 to avoid timeout, self-contained prompts to prevent clarification triggers.

## 0.20260306.1 - Explicit Component Declaration

### Breaking Changes

- **Explicit component declaration** - Auto-discovery of agents, MCP servers, and A2A services from subdirectories has been replaced with explicit manifest-based declaration. Components must now be listed in `formation.yaml` to be loaded. Files in `agents/`, `mcp/`, `a2a/` directories are definitions only -- they are inert unless referenced by the manifest.
- **`active` field removed** - The `active: true/false` field on agents, MCP servers, and A2A services is no longer recognized. Remove it from all component files.

### New Features

- **String ID references** - Formation manifests now support string IDs that resolve against subdirectory files:
  ```yaml
  agents:
    - support-agent        # Resolves to agents/support-agent.yaml
    - id: "inline-agent"   # Inline dict definition still supported
      role: "assistant"
  ```
- **Agent-level MCP references** - Agents can reference formation-level MCP servers by string ID in their `mcp_servers` field, instead of duplicating the full config inline.

### Improvements

- **Deferred secrets accumulation** - Secrets from component files are only added to `secrets_in_use` when the component is actually declared in the manifest, preventing undeclared files from polluting secret tracking.
- **Duplicate ID detection** - Duplicate component IDs are now caught at multiple levels: within subdirectory files (two files with same `id:`), within the manifest (same string ID listed twice), and across string/dict entries (string "foo" + inline `{id: "foo"}`).
- **Fail-fast on invalid types** - Non-string/non-dict entries in component lists raise `ValueError` immediately instead of being silently ignored.
- **Unresolved MCP refs fail hard** - `runtime_agent_processor.py` raises `ValueError` for unresolved string MCP IDs instead of logging a warning and silently dropping them.

## 0.20260306.0 - MCP, Performance & Better Async DX

### New Features

- **MCP Server Interface** - The runtime now exposes an MCP (Model Context Protocol) server at `/mcp`, auto-generated from existing REST endpoints via `FastMCP.from_fastapi()`. External MCP clients (Claude Desktop, Cursor, custom agents) can interact with formations using the standard MCP protocol. 33 client tools are exposed with clean names (`chat`, `list_sessions`, `get_request_status`, etc.); admin/health/internal endpoints are excluded. MCP clients must provide `X-Muxi-Client-Key` in their transport headers -- auth works exactly the same as the REST API. Route maps are generated dynamically from `operation_id`, so new client endpoints are picked up automatically. Requires `fastmcp>=3.0.0`.
- **Polling-only async** - Async requests no longer require a webhook URL. When no webhook is configured, the response includes `"delivery": "polling"` with the poll URL. Clients can poll `GET /v1/requests/{request_id}` to retrieve the result when ready.
- **Result payload in request status** - `GET /v1/requests/{request_id}` now returns the full `result` field for completed requests, enabling webhook-free async workflows.
- **Per-request async threshold** - `threshold_seconds` can now be passed per chat request to override the formation-level async decision threshold. Same pattern as the existing per-request `webhook_url` override.
- **Per-request webhook URL in ChatRequest** - `webhook_url` is now accepted directly in the chat request body, wired through to the overlord (previously only available via formation config or triggers).

### Improvements

- **RequestTracker TTL retention** - Completed, failed, and cancelled requests are retained in memory for 5 minutes instead of being removed immediately. A background cleanup task purges expired requests automatically. This gives clients a grace window to poll for results even if the webhook fails.
- **Parallelized context enhancement** - User synopsis fetch, long-term memory search, and buffer memory search now run concurrently via `asyncio.gather()` instead of sequentially, saving ~300-500ms per request.
- **Early greeting fast-path** - Simple greetings and acknowledgments (`hi`, `hello`, `hey`, `thanks`, `ok`, etc.) skip context enhancement and LLM actionability check entirely when no prior assistant question exists, reducing response time from ~4.4s to ~2.4s.
- **Empty-query buffer search fast-path** - `WorkingMemory.search()` with an empty query now returns recency results immediately without triggering lazy initialization of the embedding model, eliminating a ~1.8s overhead on first call.
- **Random e2e test runner** - New `e2e/run_random_tests.py` picks N random tests for quick regression sniff-tests (`python run_random_tests.py 10`).
- **orjson for JSON serialization** - Replaced stdlib `json` with `orjson` (via `utils/fastjson.py` drop-in wrapper) across all 57 source files. 6x faster `dumps`, 2.4x faster `loads`, reducing GIL contention under concurrent load.

## 0.20260302.0 - Dynamic Embedding Dimensions

### Breaking Changes

- The static `memories` table has been replaced by dimension-specific tables (`memories_384`, `memories_768`, `memories_1536`, etc.). Existing databases with a bare `memories` table require a one-time rename: `ALTER TABLE memories RENAME TO memories_1536;`

### New Features

- **Dynamic embedding dimensions** - Formations can now use any embedding model regardless of its output dimension. The runtime automatically creates and manages dimension-specific memory tables (`memories_{dim}`), so a 384-dim local model and a 1536-dim OpenAI model can coexist in the same database without conflicts.
- **Local embedding model support** - Added `local/` prefix for embedding models (e.g., `local/all-MiniLM-L6-v2`, `local/all-mpnet-base-v2`). The runtime downloads and runs these models locally via `sentence-transformers`, with no API key required.
- **Embedding migration script** - New `scripts/migrate_embeddings.py` re-embeds memories from one dimension to another (e.g., 1536 to 384) without data loss. Source table is preserved.
- **SQLite local embedding fallback** - SQLite-backed formations now fall back to local embeddings automatically instead of raising an error when no API-based embedding model is configured.

### Improvements

- **Memory model factory** - `get_memory_model(dimension)` dynamically generates SQLAlchemy ORM models per dimension, replacing the hardcoded `Memory` class.
- **Knowledge handler dimension resolution** - The knowledge handler now derives embedding dimensions from the formation config rather than assuming 1536.
- **`search_text()` uses dynamic table names** - Raw SQL in `long_term.py` now references `self.MemoryModel.__tablename__` instead of a hardcoded table name.

### Bug Fixes

- Fixed all raw SQL references to bare `memories` table across 11 e2e test files and 1 runtime file
- Fixed FK constraint violations during test cleanup when legacy `memories` table was absent
- Fixed FAISS buffer crash (SIGSEGV) in e2e tests caused by rapid sequential message adds at sub-second intervals
- Fixed safety-critical memory recall test (8d1) with improved extraction wait time and retry logic

## 0.20260201.0 - Initial Public Release

### Core Features

- **LLM-Agnostic** - Support for OpenAI, Anthropic, Google, Azure, AWS Bedrock, Ollama, and any OpenAI-compatible endpoint with automatic failover
- **Formation Engine** - Declarative YAML-based agent configuration with hot-reload support
- **Overlord Orchestration** - Central coordinator for multi-agent systems with intelligent routing
- **Intelligent Task Decomposition** - Automatic breakdown of complex requests into executable subtasks
- **Agent Collaboration (A2A)** - Inter-agent communication within and across formations

### Memory & Context

- **Three-Tier Memory** - Buffer (FIFO + vector), persistent (PostgreSQL/SQLite), and vector (FAISSx) memory systems
- **Multi-Tenant Isolation** - Complete session isolation with per-user credential management
- **LLM Response Caching** - Semantic caching with 70%+ cost savings on repeated queries

### Integrations

- **MCP Protocol** - Access to 1,000+ tools (GitHub, Slack, Stripe, databases, APIs) with efficient schema indexing
- **Multimodal Support** - Native handling of images, PDFs, audio, and video with vision model integration
- **Webhook Triggers** - Event-driven execution from external systems

### Output & Delivery

- **Artifact Generation** - Create documents, spreadsheets, presentations, and visualizations on demand
- **Real-Time Streaming** - Token-by-token response delivery with WebSocket and SSE support
- **Async Operations** - Background processing with webhook notifications for long-running tasks

### Operations

- **Natural Language Scheduling** - Recurring and one-time tasks with intelligent datetime parsing
- **Observability** - 349 typed events across 5 categories with multiple transport and formatter options
- **Resilience Layer** - Automatic retry, circuit breakers, and graceful degradation
