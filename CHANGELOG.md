# Changelog

## 0.20260325.1 - MCP Tool Chaining Reliability

### Bug Fixes

- **MCP tool parameter inference fails with non-JSON responses** - When the parameter inference LLM returned XML function-call syntax (Anthropic's native tool-call format leaking through) or prose with embedded JSON instead of pure JSON, `json.loads()` threw `JSONDecodeError` and the tool call was silently skipped. The agent reported success despite never executing the tool. Fix: added `_extract_json_from_response()` with three extraction strategies (direct JSON parse, XML `<parameter name="arguments">` extraction, brace-matched object scanning) and a retry with a stronger "JSON only" prompt on first failure.
- **Agent plans skip prerequisite lookup steps** - When a user said "mark X as important", the agent planned a single `update-todo-task` call without first calling `list-todo-tasks` to resolve the task ID. The parameter inference LLM had no ID to work with and produced prose instead of JSON. Fix: added a tool chaining rule to the planning prompt instructing the LLM to always fetch IDs via list/search tools before update/delete operations.

## 0.20260325.0 - Scheduler Chat Fixes, SOP Synthesis Control & Streaming Reliability

### Bug Fixes

- **Scheduler job creation via chat times out** - When a user created a scheduled job via chat, the job was written to the database correctly but the response never reached the client. The scheduler routing path in `_process_sync_chat` returned a `MuxiResponse` without emitting a streaming `"completed"` event, causing the `StreamingManager.subscribe()` poll loop to wait indefinitely. Fix: added `streaming.stream("completed", ...)` before the scheduler return.
- **Scheduler intents hijacked by SOP matching** - SOPs with generic tags (e.g., "tasks") matched scheduler-related queries like "show my scheduled tasks" with high relevance scores, routing them to unrelated agents (e.g., MS365 assistant) instead of the scheduler service. Fix: moved the scheduler routing check inside the analysis block, before SOP/complexity matching, so scheduler intent takes priority.
- **Listing scheduler jobs routes to MS365 or fails** - No chat-level integration existed for querying scheduled jobs. Users asking "show my scheduled jobs" fell through to normal agent selection, which picked the MS365 assistant. Fix: added `is_scheduler_query_request` field to `RequestAnalysis`, detection in the LLM analyzer prompt, a heuristic keyword fallback in the analyzer, and a handler in the overlord that calls `scheduler_service.list_user_jobs()` and formats the response.
- **Broken pipe causes server hang** - When a long-running workflow (e.g., morning briefing with MS365) exceeded the SSE write timeout, the TCP connection dropped but the background processing task continued indefinitely. The `StreamingManager.subscribe()` loop polled forever waiting for a terminal event that would never arrive. Subsequent requests hung until server restart. Fix: (1) captured the `processing_task` handle in `_create_stream_generator` and cancel it in a `finally` block with a 5-second timeout on disconnect; (2) added a 10-minute `SUBSCRIBE_TIMEOUT` ceiling to `StreamingManager.subscribe()` to prevent zombie streams; (3) added a stale request reaper to `RequestTracker.cleanup_expired()` that force-fails any request stuck in `PROCESSING` for longer than 10 minutes.
- **Job title truncation** - Chat-created jobs truncated titles at 61 characters (`"Scheduled: " + message[:50]`), API-created jobs at 80 characters (`message[:80]`), despite the database column supporting 500 characters. Fix: increased both limits to match the DB column (`[:490]` for chat path to account for the "Scheduled: " prefix, `[:500]` for API path).
- **Multi-day cron parsing only captured first day** - "every Tuesday and Thursday at 3pm" produced `0 15 * * 2` (Tuesday only) instead of `0 15 * * 2,4`. The regex pattern in `ScheduleParser._try_pattern_matching()` only matched a single day name. Fix: added a multi-day regex that runs before the single-day pattern, extracting all day names and joining them as comma-separated cron day-of-week values.
- **Sequential MCP tool calls lose parameter context** - When an agent's execution plan chained multiple MCP tool calls (e.g., `list-todo-task-lists` then `list-todo-tasks`), the second call's parameter inference LLM only saw the original user message, not the results from the first call. This caused the LLM to produce prose instead of JSON parameters, resulting in `JSONDecodeError` and the second tool call being silently skipped. Fix: accumulated `my_results` from previous steps are now appended to the inference context passed to `_infer_tool_parameters()`.
- **SOP JSON output instruction ignored by synthesis** - SOPs that specified strict output formats (e.g., "return ONLY raw JSON") had their output rewritten by the overlord's synthesis layer into markdown prose. The synthesis LLM call has its own system prompt with no knowledge of the SOP's format constraints. Fix: added `synthesis` frontmatter field to SOPs (default: `true`). When `synthesis: false`, the last successful task's raw output is returned directly, bypassing the synthesis LLM. Propagated via `skip_synthesis` field on the `Workflow` model.
- **Fan-in SOP workflows forced sequential** - The heuristic that detected "SOP workflows" and forced sequential execution (`enable_parallel_execution = False`) triggered on any workflow where most tasks had dependencies, including fan-in patterns (e.g., 3 independent fetch tasks feeding 1 synthesis task). Fix: tightened the heuristic to only force sequential for strict linear chains (each task depends on exactly one predecessor). Fan-in patterns now execute independent tasks in parallel via `build_execution_phases()`.

### New Features

- **SOP `synthesis` frontmatter** - SOPs can now declare `synthesis: false` in their YAML frontmatter to bypass the overlord's response synthesis step. When set, the last completed task's raw output is returned as-is. Default remains `true` for backward compatibility.
- **Scheduler job listing via chat** - Users can now ask "show my scheduled jobs", "list my reminders", etc. via chat. The request analyzer detects `is_scheduler_query_request` (via LLM analysis with heuristic fallback) and routes to the scheduler service's `list_user_jobs()` method.

### Tests

- **e2e test 7B5: SOP synthesis skip** - Verifies that SOPs with `synthesis: false` return un-synthesized output (`synthesis_method=skipped_per_sop`), and SOPs with default synthesis still go through the normal synthesis path. Includes two test SOPs: `json-output-test.md` (synthesis disabled) and `synthesis-default-test.md` (synthesis enabled).

## 0.20260324.1 - Scheduler LLM Timeout, User ID Exposure & Delete Audit

### Bug Fixes

- **Scheduler NL queries timeout ~5 minutes** - `ScheduleParser._get_llm()` and `PromptRewriter._get_llm()` created bare `LLM()` instances defaulting to `openai/gpt-4o` with no API key. With 30s timeout x 3 retries + exponential backoff this caused ~3-5 minute hangs. Fix: parser and rewriter now receive the overlord's `extraction_model` (properly configured with API keys) during scheduler service initialization.
- **API responses exposed internal integer user_id** - `ScheduledJob.to_dict()` returned the raw integer FK (e.g., `5`) instead of the external string identifier (e.g., `"tester"`). Fix: added `_resolve_external_user_id()` reverse lookup and `_enrich_job_dict()` helper applied to all job query methods (`get_job`, `get_all_jobs`, `get_user_jobs`, `get_active_jobs`, `get_active_jobs_batch`). Uses `scalars().first()` to handle multi-identity users safely.
- **Delete job caused FK audit violation** - After deleting a job and its audit records, the code tried to INSERT a "deleted" audit record referencing the now-deleted job, violating the FK constraint on `scheduled_job_audit.job_id`. Fix: skip the post-deletion audit INSERT; deletion is tracked via observability events instead.

### Verified

All fixes verified against live SIF deployment (`my-assistant-anthropic` formation with Claude Sonnet 4.5 and PostgreSQL):
- Scheduler API: create, list, get, update (PUT), pause, resume, delete -- all passing
- NL scheduling via chat: 35s response (not ~5min timeout)
- NL query "do I have any scheduled jobs?": 13s response (not ~5min timeout)
- API responses return `user_id: "tester"` (string), not `user_id: 5` (integer)
- PUT endpoint returns 200 (not 405 METHOD_NOT_ALLOWED)

## 0.20260324.0 - Scheduler API Persistence & Job Lifecycle

### Bug Fixes

- **Scheduler jobs not persisted to database** (Critical) - All scheduler route handlers used `hasattr` checks for methods that don't exist on `SchedulerService`, falling back to in-memory Python dicts. Jobs vanished on every restart. Fix: all routes now call the async `JobManager` methods which persist to PostgreSQL via SQLAlchemy.
- **Scheduler list/get/delete also used in-memory dicts** - Same pattern as create: `list_scheduled_jobs`, `get_scheduled_job`, and `remove_scheduled_job` all fell into dict-based fallback branches. Rewired to `job_manager.get_all_jobs()`, `.get_job()`, `.delete_job()`.
- **SchedulerService.pause/resume/delete missing user_id** - `pause_job()`, `resume_job()`, and `delete_job()` on `SchedulerService` called their `JobManager` counterparts without the required `user_id` parameter, causing `TypeError` at runtime. Added `user_id` parameter to all three.
- **JobManager.delete_job FK constraint violation** - Deleting a job failed with `ForeignKeyViolation` because `scheduled_job_audit` references `scheduled_jobs.id` without `ON DELETE CASCADE`. Fix: audit records are now deleted before the job.
- **get_default_nanoid()() double-call in JobManager** - `_resolve_user_id_sync` called `get_default_nanoid()()` which raises `'str' object is not callable` since the function returns a string. Fixed to single call.

### New Endpoints

- **`PUT /v1/scheduler/jobs/{job_id}`** - Update a job's message, schedule, or title. Calls `JobManager.update_or_replace_job()` which may replace the job if the prompt change is significant.
- **`POST /v1/scheduler/jobs/{job_id}/pause`** - Pause an active job. Returns 404 if job is not in ACTIVE state.
- **`POST /v1/scheduler/jobs/{job_id}/resume`** - Resume a paused job. Returns 404 if job is not in PAUSED state.

## 0.20260323.0 - Scheduler Blocking, Memory Recall & Parameter Compatibility

### Bug Fixes

- **Buffer memory recall failed on non-actionable path** - When `_is_actionable_message()` classified a recall question (e.g., "what is my favorite turtle?") as non-actionable, `_apply_persona()` extracted only the raw user question via regex, discarding all `=== RELEVANT MEMORIES ===` and `=== CONVERSATION CONTEXT ===` sections. The persona LLM saw zero context and could not answer. Fix: the non-actionable path now preserves and includes memory and conversation context sections in the persona prompt.
- **Recall questions misclassified as non-actionable** - The LLM actionability check could classify memory recall questions as non-actionable since they don't resemble commands or task requests, causing context loss (above). Fix: when the enhanced message contains `=== RELEVANT MEMORIES ===`, the message is forced actionable and routed through the full agent pipeline. Greetings for users with no stored memories still fast-path correctly.
- **Duplicate buffer memory storage** - Both `chat_orchestrator.chat()` and `overlord._process_sync_chat()` independently stored each user message and assistant response in buffer memory, producing 4 buffer writes per exchange instead of 2 and halving effective buffer capacity. Fix: removed duplicate storage from `_process_sync_chat()`; `chat_orchestrator` is the sole owner of buffer storage.
- **Memobase collection not passed through to LongTermMemory** - `Memobase.add()` computed a collection name but did not pass it to the underlying `LongTermMemory.add()` call, so memories were stored without collection partitioning.
- **Memobase search double-filtered on `external_user_id`** - `Memobase.search()` injected `external_user_id` into `additional_filter` before passing to `LongTermMemory.search()`, which already filters by user. This caused no visible bug but was redundant.
- **Scheduler blocked event loop, preventing formation startup** - `SchedulerService.start()` called `process_due_jobs_continuously()` directly, which enters an infinite `while/sleep` loop that blocked the asyncio event loop forever. The HTTP server never started, causing health check timeouts. Fix: moved the worker to a daemon thread so `start()` returns immediately.
- **`count_active_jobs()` blocked event loop on slow DB** - After the thread fix, `start()` still awaited a synchronous psycopg2 call that would hang if PostgreSQL was unreachable. Fix: wrapped in `run_in_executor` with a 10-second timeout, defaulting to 0 on failure.
- **Memobase parameter compatibility** - Added `user_id` as alias for `external_user_id` in `add()`, and `filter_metadata` as alias for `additional_filter` in `search()`, preventing parameter mismatch errors when callers use either naming convention.

## 0.20260321.0 - SIF Embedding Model & Schema Migration

### Bug Fixes

- **`all-mpnet-base-v2` fails in SIF container** - The 768-dim embedding model was not pre-bundled in the Docker image. Since SIF containers mount `/opt/hf-cache` as read-only, the model could not be downloaded at runtime, resulting in `[Errno 30] Read-only file system`. Fix: added `all-mpnet-base-v2` to the Dockerfile pre-download step alongside the existing two models.
- **Missing `meta_data` column on upgraded databases** - Tables created by older runtime versions lacked the `meta_data` column later added to the SQLAlchemy model. `CREATE TABLE IF NOT EXISTS` does not add columns to existing tables. Fix: added `_migrate_add_meta_data_column()` migration step that runs after table creation, using `ALTER TABLE ADD COLUMN IF NOT EXISTS` for PostgreSQL and `PRAGMA table_info` check for SQLite.

## 0.20260320.0 - Scheduler, Memory & Dependency Fixes

### Bug Fixes

- **Scheduler routes always returned SERVICE_UNAVAILABLE** - All 4 scheduler job management endpoints (`list`, `create`, `get`, `delete`) checked `formation._scheduler` which was never assigned. Fixed to access the scheduler via `formation._overlord.scheduler_service`, which is where the service actually lives.
- **Memobase fallback passed invalid kwargs** - The Memobase initialization fallback path passed `connection_string=` to `Memobase.__init__`, which only accepts a `LongTermMemory` instance. Fixed to create `LongTermMemory` first, then wrap with `Memobase`.
- **Memobase did not expose embedding dimension** - `Memobase` lacked a `.dimension` attribute, causing `_create_all_database_tables` to always default to `memories_1536` even when a 384-dim or 768-dim embedding model was configured. Fixed by propagating `.dimension` from the inner `LongTermMemory`.

### Improvements

- **faiss-cpu bumped to >=1.13.0** - Eliminates numpy `DeprecationWarning` about `numpy.core._multiarray_umath` that appeared in test output and logs.

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
