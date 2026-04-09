# Changelog

## 0.20260409.4 - Recover Workbook Identifiers from Prior MCP Results

### Bug Fixes

- **Multi-step MS365/Excel workflows could still lose the named workbook identifier after earlier lookup steps** -- When prior MCP calls returned large payloads, repair planning could latch onto a parent/root record or an overly broad summary instead of the workbook itself. Fix: extract matching structured records from prior results, preserve the relevant workbook entry in planning context, and deterministically reuse identifiers such as `driveItemId` for downstream Excel calls.
- **Repair planning could still reject the right fix when it stayed on the same tool chain** -- If the best recovery was to keep the same final tool but add a missing discovery step first, the runtime could treat the repaired plan as unchanged and stop. Fix: compare repaired plans more carefully, accept meaningful same-tool-chain repairs, and auto-insert a missing lookup step when replanning still skips it.

### Tests

- **Expanded planning helper regression coverage** -- Extended `tests/unit/test_agent_planning_helpers.py` to verify workbook identifier recovery from large prior MCP payloads, acceptance of meaningful same-tool-chain repairs, and automatic discovery-step insertion for missing Excel/MS365 identifiers.
- **Random e2e regression sniff tests** -- Ran 5 random standalone e2e tests before release confidence checking, with all 5 passing across `multimodal`, `knowledge`, `orchestration`, and `clarification`.

## 0.20260409.3 - Prefer Local Tools Over Self-Delegation

### Bug Fixes

- **Agents could delegate a tool step back to themselves instead of executing it locally** -- In some multi-step MS365/Excel workflows, the planner marked a step like `list-excel-worksheets` as `can_i_do_this: false` even though that tool was already in the current agent's own toolset. The runtime trusted that flag, converted the step into a delegated handoff, and triggered the A2A loop detector instead of letting the local repair-planning path build the required discovery chain. Fix: normalize any step whose tool is already present in the current agent's available tool list to `can_i_do_this: true`, keep it in `my_steps`, and prevent self-delegation.

### Tests

- **Focused planning helper coverage** -- Extended `tests/unit/test_agent_planning_helpers.py` to verify that locally available tools are always kept as local execution steps even when the planner initially marks them as non-executable.

## 0.20260409.2 - Repair Planning for Missing Tool Identifiers

### Bug Fixes

- **Sequential MCP workflows could still stop after the first missing identifier** -- The earlier guardrail correctly refused to call tools with unresolved required parameters such as `driveItemId`, but execution still stopped at that point because the runtime had no way to repair a bad one-step plan into the required discovery chain. Fix: add a single repair-planning pass that feeds the failed tool, missing parameters, current tool chain, and any prior tool results back into the planner so it can insert prerequisite lookup steps before retrying the workflow.
- **The planner did not get enough schema signal to choose discovery chains reliably** -- Planning context mostly exposed tool names and short descriptions, which made it too easy for the LLM to choose tools like `list-excel-worksheets` without realizing they require identifiers from earlier lookup steps. Fix: include each tool's required parameter names in the planning prompt so the planner can better infer when a prerequisite discovery step is needed.
- **Planner-supplied parameters could be dropped before execution** -- `_finalize_execution_plan()` rebuilt `my_steps` from `steps` but discarded explicit parameters from the plan, forcing later inference even when the planner had already provided useful arguments such as `driveId` or `searchQuery`. Fix: preserve planner-supplied parameters when normalizing `my_steps`.

### Tests

- **Focused planning helper coverage** -- Extended `tests/unit/test_agent_planning_helpers.py` to verify planner-supplied parameters are preserved, required params are surfaced in the planning prompt, and repair-planning is triggered when execution discovers a missing identifier.
- **Random e2e regression sniff tests** -- Ran 5 random standalone e2e tests before release confidence checking, with all 5 passing.

## 0.20260409.1 - Planner Guardrails for Identifier Discovery & Tool Error Reporting

### Bug Fixes

- **Planning could still invent or accept unresolved required identifiers** -- When a tool required a concrete ID such as a drive item, the planner could still accept blank/default values from LLM parameter inference or skip directly to the action step without a real lookup. Fix: teach planning prompts to require identifier-discovery steps, reject unresolved required parameter values during inference, and surface an explicit planning error when required tool inputs cannot be determined.
- **Handled MCP/tool failures could still look like successful execution in observability** -- Some tool calls returned structured error payloads instead of raising exceptions, but the agent still emitted success-shaped completion events for those results. Fix: detect error-shaped tool payloads consistently in both direct tool invocation and planning execution, record them as failures in observability, and avoid treating those planned steps as successful completions.

### Tests

- **Focused planning helper regression coverage** -- Extended `tests/unit/test_agent_planning_helpers.py` to verify blank required string parameters are rejected, MCP error payloads are detected correctly, and tool-call completion events report `success=False` when the underlying tool returns an error result.
- **Random e2e regression sniff tests** -- Ran 5 random standalone e2e tests before release confidence checking, with all 5 passing across `memory`, `mcp`, `artifacts`, `knowledge`, and `clarification`.

## 0.20260409.0 - Faster Persistent Memory Recall & Profile Lookups

### Bug Fixes

- **Profile and memory recall could be slower than necessary** -- Requests that searched across multiple memory collections could recompute the same embedding and fan out into extra lookups, adding avoidable latency before context was assembled. Fix: persistent memory search now uses a single multi-collection query where supported and otherwise reuses one query embedding across fallback searches.
- **Broad profile questions could miss the fastest available path** -- Requests like “what do you know about me?” could jump into heavier semantic recall even when recent profile facts or cached synopsis data were already enough. Fix: restore lightweight user-scoped reads for synopsis/profile data and surface recent profile facts before broader semantic search.
- **Large PostgreSQL-backed memory stores could degrade more than necessary** -- Persistent memory tables were missing cheap lookup and vector index paths as data grew. Fix: add best-effort PostgreSQL indexes for user/collection filtering and semantic search, while keeping index creation failures non-fatal and warning-only.

### Tests

- **Focused memory performance coverage** -- Added unit coverage for multi-collection ranking and top-k stability, profile fast-path behavior, and non-fatal PostgreSQL index creation handling.
- **Live validation** -- Full unit suite and targeted memory end-to-end tests passed, and a 5,000-row benchmark user confirmed faster unified semantic recall and cheap profile lookups.
- **Random e2e regression sniff tests** -- Ran 10 random standalone e2e tests before release confidence checking, with all 10 passing across `foundation`, `memory`, `multimodal`, `orchestration`, `clarification`, `scheduling`, `api`, and `skills`.

## 0.20260408.2 - Chat SSE Keepalive During Slow Setup

### Bug Fixes

- **Successful chat requests could still time out at the client before any response bytes arrived** -- `/v1/chat` and `/v1/audiochat` awaited `overlord.chat()` / `overlord.audiochat()` before yielding the first SSE chunk. Slow pre-stream work (user resolution, memory/context enhancement, embedding warm-up, routing, and tool setup) and long gaps between streamed items could leave the HTTP connection idle long enough for clients or proxies to time out even though the backend request eventually succeeded. Fix: wrap streaming responses in a keepalive generator that emits immediate and periodic SSE comment frames during stream setup and between token gaps, while preserving the existing `token` and `done` event contract.

### Tests

- **Focused keepalive coverage for streaming chat endpoints** -- Added `tests/unit/test_chat_sse_keepalive.py` to verify keepalive emission during slow stream setup and delayed token gaps, and reran `e2e/tests/19_api/test_19e1_chat_streaming.py` to confirm `/v1/chat` still streams correctly end-to-end.

## 0.20260408.1 - Specialist Routing Follow-through & Direct Response Date Preservation

### Bug Fixes

- **Broad user-defined assistants could still absorb specialist service requests** -- The first routing guardrail only corrected LLM selections when the chosen agent was literally `muxi-generalist`. Formations that used a developer-defined broad agent such as `assistant` could still route ambiguous MS365 requests like "What is my current user profile?" away from the specialist. Fix: generalize the post-LLM override to any non-specialist agent and score specialist agents using agent-specific MCP tool names and descriptions in addition to their routing metadata.
- **Delegated A2A specialists could still skip MCP planning** -- When a broad agent delegated work to a specialist, the specialist received `is_a2a_task=True` and bypassed planning entirely, which meant it could answer from model prior instead of invoking the specialist MCP tools. Fix: only bypass planning for A2A tasks when no tools are available; when tools exist, plan normally but disable any further delegation and strip `delegate_steps` deterministically.
- **Direct planning responses could still rewrite exact service dates** -- The previous date-preservation fix covered workflow synthesis, but direct planning-based agent responses still assembled tool results without a final guardrailed synthesis step. Fix: add an agent-side planning-response synthesis prompt that preserves exact dates, weekdays, times, and ranges from tool results.
- **Modern MCP structured output could lose canonical timestamp fields** -- `process_structured_output()` flattened modern MCP responses into plain text and could discard `structuredContent`, removing machine-readable fields such as exact received timestamps before final response synthesis. Fix: preserve `structured_content` in processed MCP results and join all text blocks instead of keeping only the first one.

### Tests

- **Focused unit coverage for routing, delegated A2A planning, and MCP structured output preservation** -- Added `tests/unit/test_agent_planning_helpers.py` and `tests/unit/test_mcp_protocol_features.py`, and extended `tests/unit/test_agent_router.py` to verify tool-aware specialist overrides, deterministic delegate-step stripping when delegation is disabled, planning-response date guardrails, and preservation of structured MCP content.
- **Random e2e regression sniff tests** -- Ran 5 random standalone e2e tests before release confidence checking, with all 5 passing.

## 0.20260408.0 - Routing Follow-through & Date-Preservation Hardening

### Bug Fixes

- **`muxi-generalist` could still win despite a clearly better domain match** -- Even after the earlier routing metadata improvements, the LLM router could still return `muxi-generalist` for requests that strongly matched a developer-supplied agent such as an MS365/profile assistant. Fix: keep normal LLM routing, but when the LLM selects `muxi-generalist`, run a lightweight deterministic overlap check across the other available agents and override the result only when a non-`muxi-generalist` agent is a clearly stronger match.
- **Routing heuristic was harder to audit than necessary** -- The fallback scoring logic mixed several weighting rules without explaining why each existed, which made future tuning riskier. Fix: factor the scoring into `_score_available_agents()`, document the scoring rules, add inline comments for each signal, and update the routing prompt to explicitly state that `muxi-generalist` should be used only as a fallback when no other available agent is a strong match.
- **User-defined broad assistants could still absorb specialist requests** -- The first routing guardrail only corrected LLM selections when the chosen agent was literally `muxi-generalist`. Formations that used a developer-defined broad agent like `assistant` still routed ambiguous MS365 requests (for example "What is my current user profile?") to the wrong agent. Fix: generalize the post-LLM override to any non-specialist agent and enrich routing metadata with agent-specific MCP tool names/descriptions so specialist tool intent can win even when the user omits explicit service keywords.
- **Workflow synthesis could rewrite exact email/calendar dates into relative labels** -- Final workflow synthesis and synthesis-task prompts told the LLM to be coherent and concise, but gave no instruction to preserve absolute dates and times from prior task results. This allowed models to rewrite concrete values like `Tuesday, April 7, 2026` into relative language such as `today`, which is especially dangerous for briefings, emails, and calendar summaries. Fix: add explicit date-preservation guardrails to both the workflow synthesis prompt and workflow task prompt so absolute dates, weekdays, times, and ranges are kept exactly as written unless the source data already uses relative wording.
- **Delegated A2A tasks could still skip tool planning** -- When a broad agent delegated work to a specialist, the specialist received `is_a2a_task=True` and bypassed planning entirely, which meant it never invoked MCP tools even when it had the right tools to answer the request. Fix: only bypass planning for A2A tasks when no tools are available; when tools exist, plan normally but disable any further delegation and strip `delegate_steps` deterministically.
- **Planning-based direct responses could still lose exact timestamps** -- Yesterday's date-preservation fix covered workflow synthesis, but direct agent planning responses still assembled raw tool results without a final guardrailed synthesis step. Fix: add an agent-side planning-response synthesis prompt that preserves exact dates/times and uses structured MCP results as source material.
- **Modern MCP structured output discarded machine-readable fields** -- `process_structured_output()` flattened MCP responses down to a text string and dropped `structuredContent`, which could remove exact timestamps and other canonical data before the final response was written. Fix: preserve `structured_content` in processed MCP results and join all content text blocks instead of keeping only the first one.

### Tests

- **Focused unit coverage for `muxi-generalist` override behavior** -- Extended `tests/unit/test_agent_router.py` to verify that `muxi-generalist` is overridden for a strong MS365/profile request but retained for broad requests like "Tell me a joke".
- **Focused unit coverage for tool-aware specialist overrides** -- Extended `tests/unit/test_agent_router.py` to verify that a user-defined broad `assistant` is overridden when specialist MCP tool hints make the domain match clear.
- **Focused unit coverage for delegated A2A planning guardrails** -- Added `tests/unit/test_agent_planning_helpers.py` covering: A2A planning bypass only when no tools exist, planning-response synthesis prompts preserving exact dates, and deterministic stripping of `delegate_steps` when delegation is disabled.
- **Focused unit coverage for MCP structured output preservation** -- Added `tests/unit/test_mcp_protocol_features.py` to verify that `structuredContent` and all text blocks are preserved in processed MCP results.
- **Focused unit coverage for date-preservation prompt guardrails** -- Added `tests/unit/test_workflow_date_preservation_prompts.py` to verify that workflow synthesis and synthesis-task prompts explicitly preserve absolute dates/times and keep prior-step date strings intact.
- **Random e2e regression sniff tests** -- Ran 25 random standalone e2e tests across routing-adjacent and unrelated areas (`topic_tagging`, `api`, `skills`, `mcp`, `knowledge`, `memory`, `clarification`, `async`, `formatting`, `streaming`, `multimodal`, `triggers`, and `artifacts`) with all tests passing.

## 0.20260407.0 - Specialist Routing & HTTP MCP Request Lifecycle Hardening

### Bug Fixes

- **Specialist agent metadata was ignored during Overlord routing** -- The routing prompt and fallback heuristic only considered `agent_id` and `description`, even though the overlord had already loaded richer metadata such as `role`, `specialties`, and nested `specialization.*`. This caused specialist agents (for example MS365-focused agents) to lose ambiguous domain requests to the default generalist unless the user's wording was extremely explicit. Fix: normalize `specialization.domain` and `specialization.keywords` into routing metadata at load time, surface `role`, `specialties`, specialization domain, and specialization keywords in the routing prompt, and teach the heuristic fallback to prefer specialists when metadata overlaps the request.
- **Routing cache leaked agent choices across sessions** -- `AgentRouter` cached decisions by raw message string only. Short follow-up turns like `"yes"` or `"continue"` could reuse a routing decision from a different session, overriding the intended session context. Fix: cache keys are now built from `(session_id, normalized_message)` and follow-up routing uses the last agent only within the same session.
- **Current-request extraction dropped multiline context before routing** -- When the enhanced prompt contained `=== CURRENT REQUEST ===`, the overlord only extracted the first `User:` line for routing. Additional lines that clarified the domain could be silently discarded before agent selection. Fix: the router now preserves the full current-request block until the next section marker.
- **HTTP MCP tool calls ignored per-request timeouts** -- `StreamableHTTPTransport` and `HTTPSSETransport` enforced timeouts during connect/init, but raw `session.call_tool()`, `list_tools()`, `list_resources()`, and `list_prompts()` calls were not wrapped with `asyncio.wait_for()`. HTTP requests could therefore outlive the configured timeout and stall for minutes. Fix: both HTTP transports now enforce `timeout or self.request_timeout` around every MCP SDK operation.
- **HTTP SSE transport hardcoded multi-minute read timeouts** -- The SSE transport used `timeout=60` and `sse_read_timeout=300` regardless of the configured request timeout, creating a large mismatch between formation config and actual behavior. Fix: connect/init now use the configured timeout and the SSE read timeout is derived from that request timeout instead of a fixed 5-minute value.
- **Live MCP reconnects ignored explicit transport type** -- MCP registration stored the resolved/configured `transport_type`, but live reconnects always went back through auto/fallback transport selection. This could re-enter streamable-vs-SSE detection on every reconnect even when the formation had already chosen a transport. Fix: `MCPServerClient` now preserves explicit transport type during reconnects and the factory respects explicit `streamable_http` / `http_sse` requests directly.
- **Client disconnects left poisoned pooled HTTP MCP connections behind** -- When a streaming chat disconnected, the outer SSE response was cancelled but the underlying MCP request was not tied to the overlord request lifecycle. A long-running HTTP MCP call could remain alive on a pooled connection and wedge later requests behind the same stale session or per-server lock. Fix: thread `request_id` and `CancellationToken` through the MCP service/handler path, add `MCPService.cancel_requests_for_request()`, close bad pooled live connections on cancellation, and invoke that cleanup from the chat stream generator's disconnect path.

### Tests

- **Focused routing and HTTP MCP lifecycle unit coverage** -- Added `tests/unit/test_agent_router.py` to cover specialist metadata in routing prompts, session-scoped cache behavior, and specialist fallback preference. Added `tests/unit/test_mcp_http_request_lifecycle.py` to cover HTTP transport timeout enforcement, explicit transport-type reconnects, request tracking propagation, and pooled-connection cancellation cleanup.

## 0.20260403.0 - MCP Accept Header & Agent Context Fixes

### Dependencies

- **Bump faissx to >= 0.20260403.0** -- This version includes improved data persistence between restarts, ensuring vector store state survives formation restarts without data loss.

### Bug Fixes

- **Strict MCP servers reject transport detection with 406 Not Acceptable** -- FastMCP and other strict HTTP MCP servers enforce content negotiation and reject requests with the default `Accept: */*` header, returning a `406 Not Acceptable` with `"Client must accept application/json"`. The transport detector's ping request used aiohttp's default headers, so these servers were never recognised as reachable endpoints. Fix: the detector now sends `Accept: application/json, text/event-stream, */*` explicitly, satisfying both strict JSON-only servers and streaming SSE servers. Credit: community contribution (PR #139).

## 0.20260402.0 - Workflow Tool-Call Reliability & Date Awareness

### Bug Fixes

- **Workflow tasks inherit full conversation history, causing tool call simulation** -- Agents are long-lived and accumulate conversation history across direct-chat and workflow executions. When a workflow task was dispatched, the agent called `chat_with_tools` with the entire accumulated `self._messages` history — including prior sessions where MCP tools had been called. The LLM, seeing that history, would reproduce prior tool call shapes as XML text content (e.g. `<ms365_list_todo_tasks>`) rather than issuing fresh structured API function calls against the registered tool schemas. The MUXI tool loop only handles structured API tool calls; XML in text content is treated as the response and passed to downstream steps as data. Fix: when `is_workflow_task` is True, the initial `chat_with_tools` call uses an isolated context of [system message(s) + current task prompt only]. Subsequent calls within the tool loop still receive the full working context so real tool results flow correctly between iterations.
- **LLM uses training-data date instead of system date** -- The model consistently computed "today" as an incorrect historical date regardless of the actual system date, because no temporal context was present in the agent's context. Fix: the system message is now prepended with `It is now <weekday, Month DD, YYYY HH:MM (TZ)>.` on every `process_message` call. The prefix is replaced fresh each request so long-running agents never serve a stale date. Applies to direct chat, workflow tasks, and A2A calls alike.
- **Tool name observability missing for workflow task LLM calls** -- When tools were passed to `chat_with_tools`, no log entry confirmed which tool names actually reached the LLM. Fix: a DEBUG-level observability event now logs `tool_count` and `tool_names` immediately before each `chat_with_tools` call, visible in server logs when `log_level: debug` is set.

## 0.20260401.1 - SOP Workflow: Synthesis Bypass Fix & Hallucination Guard

### Bug Fixes

- **`synthesis: false` returns raw metadata dict instead of response text** -- When a SOP declares `synthesis: false`, the overlord skips the LLM synthesis pass and returns the last successful task's output directly. The extraction path called `raw_output.get("content", str(raw_output))`, but `_parse_task_response` wraps agent output under `{"main": {"result": "...", ...}}`. The fallback `str(raw_output)` serialised the entire nested dict, producing a JSON blob instead of the actual response. Fix: the extraction now checks `raw_output["main"]["result"]` first, then `raw_output.get("content")`, then falls back to `str(raw_output)`.
- **Directive tags leak into task description for heading-format SOPs** -- The deterministic SOP parser correctly stripped `[agent:name]`, `[mcp:tool]`, `[parallel]` etc. from step body text, but not from the heading title (e.g. `### Step 1: Fetch calendar events [agent:ms365-assistant] [parallel]`). The full heading text — including all directive brackets — was included verbatim in the task description passed to the agent. Fix: the heading extractor now strips directive tags from `step_title` before constructing `full_desc`, matching the behaviour of the numbered-list extractor.
- **Workflow task agents generate pseudo-XML tool calls instead of real calls** -- When executing a workflow task, some models recognise the task description as mapping to known MCP/tool patterns and generate `<use_mcp_tool>` XML output in the response text rather than issuing a structured API tool call. The MUXI tool loop only handles structured function calls from the LLM API; XML in the response text is treated as the task result and passed to downstream steps as data, causing downstream agents to receive fabricated XML as "prior step results". Fix: `_create_task_prompt` now appends an explicit instruction to use available tools directly and not simulate, fabricate, or generate pseudo-tool-call XML.
- **Workflow tasks inherit full conversation history, causing tool call simulation** -- Agents are long-lived and accumulate conversation history across direct-chat and workflow executions. When a workflow task was dispatched, the agent called `chat_with_tools` with the entire accumulated `self._messages` history — including prior sessions where ms365 or other MCP tools were actually called. Claude Sonnet, seeing this history, would "continue the pattern" by generating `<ms365_list_todo_tasks>` XML in text content (matching prior tool call shapes from training data) rather than issuing a fresh structured API function call against the registered tool schemas. Fix: when `is_workflow_task` is True, the initial `chat_with_tools` call uses an isolated context of [system message(s) + current task prompt only]. Subsequent calls in the tool loop still use `self._messages` so real tool results flow correctly between iterations.
- **LLM uses training-data date instead of system date** -- The model consistently computed "today" as 2025-01-10 (approximate training cutoff) regardless of the actual system date, because no date context was present in the agent's context. Fix: the system message is now prepended with `It is now <weekday, Month DD, YYYY HH:MM>.` on every `process_message` call. The prefix is replaced fresh each request so long-running agents never serve a stale date. Applies to direct chat, workflow tasks, and A2A calls alike.
- **Tool name observability missing for workflow task LLM calls** -- When tools were passed to `chat_with_tools`, there was no log entry showing which tool names reached the LLM. Debugging the hallucination required log correlation across multiple events. Fix: a DEBUG-level observability event now logs `tool_count` and `tool_names` immediately before each `chat_with_tools` call, visible in server logs when `log_level: debug` is set.

## 0.20260401.0 - Skill Secrets, SOP Synthesis Fix & Workflow Data Flow

### New Features

- **`${{ secrets.X }}` interpolation in skill instructions** -- Skills can now reference formation secrets directly in their `SKILL.md` body using the same syntax used everywhere else in MUXI. The runtime scans all skill files (`SKILL.md`, `scripts/`, `references/`, `assets/`) for secret references at load time, stores the list in `SkillMetadata.required_secrets`, and interpolates them before injecting the skill body into the agent's context on activation. Missing secrets are logged as warnings at startup without blocking formation load.
- **Secret env injection for bundled skill scripts** -- Scripts inside a skill's `scripts/` directory cannot use `${{ }}` syntax directly (they are executed as regular programs). Instead, the runtime resolves the skill's required secrets and passes them as environment variables to the RCE subprocess via the existing `env` field on `POST /skill/{id}/run`. Keys map directly from secret name to env var name (`${{ secrets.NOTION_KEY }}` → `NOTION_KEY`). Secrets are passed only to the subprocess environment -- they are never written to disk, never cached by the RCE service, and are gone when the process exits.

  > [!WARNING]
  > **Skills RCE must not be publicly exposed if passing variables dynamically** -- Because the `env` field on execution requests carries plaintext secret values, the HTTP channel between the runtime and `skills-rce` is only safe within a trusted network boundary (same host, Docker network, or private network - which is how the MUXI Server is using it). This restriction is now documented in the skills-rce README and in the skills concept docs.

### Tests

- **29 new unit tests for skill secrets** -- Added `tests/unit/skills/test_skill_secrets.py` covering: `scan_secret_refs()` (various patterns, nested directories, deduplication, whitespace tolerance, uppercase normalization), `required_secrets` populated on `SkillMetadata` after parse, `activate_async()` with and without a secrets manager, `validate_secrets()` (all present / some missing / no manager), `resolve_skill_env()` (full resolution / missing secrets omitted / no manager), and `set_secrets_manager()` late binding.
- **E2E test for secret injection via RCE** -- Added `e2e/tests/21_skills/test_21c3_skill_secrets_env.py`. Verifies: `required_secrets` is populated at parse time; `activate_async()` resolves `${{ secrets.SKILL_TEST_GREETING }}` to its actual value in the injected content; `resolve_skill_env()` builds the correct env map; the RCE subprocess receives the secret as an environment variable and the script outputs the expected value; the script fails without the env injection (proving injection is the mechanism).

### Bug Fixes

- **SOP synthesis step fails with truncated instructions** -- The deterministic SOP parser capped step body text at 500 characters in both the numbered-list and heading-format extractors. Synthesis steps routinely carry structured output specs (JSON field definitions, format rules, output constraints) that exceed this limit. The truncation produced a task prompt ending in `....`, which caused the executing agent to error on the first attempt with `retry_count: 1`. Fix: removed the 500-character cap from both extractors. SOP step descriptions are task instructions, not summaries — they must be passed verbatim.
- **Parallel SOP steps return no data to synthesis agent** -- `_collect_task_inputs` correctly gathered dependency outputs into `execution_context["inputs"]`, but `_create_task_prompt` serialised them as a raw nested JSON blob: `{"from_task_1": {"main": {"result": "...", "status": "success", ...}}}`. The synthesis agent received the metadata wrapper, not the actual content, and reported "the previous tool calls didn't return results that I can see" before falling back to hallucination. Fix: `_create_task_prompt` now extracts `main.result` from each dependency output and presents it under a clear `## Results from prior steps / ### Task N` heading so the synthesis agent receives the raw step data directly.

## 0.20260331.0 - SOP Reliability & Workflow Hardening

### Bug Fixes

- **Template-mode SOP steps silently dropped** -- When a SOP with `mode: template` was executed, its steps were fed through the generic LLM decomposer, which could hallucinate backward dependencies, produce duplicate task IDs, or drop steps entirely during regex parsing. Any malformed output caused `validate_workflow_dag()` to fire a false "contains cycles" warning, after which `_fix_workflow_cycles()` would rewrite the entire task list into an arbitrary sequential chain—silently destroying the original step structure. Fix: `TaskDecomposer` now attempts a deterministic markdown parser for template-mode SOPs before calling the LLM. The parser handles the real SOP format (`1. **Title** [agent:name]` numbered lists under a `## Steps` section) and falls back to `## Step N` heading format for non-standard SOPs. It extracts `[agent:name]`, `[mcp:tool/action]`, and `[parallel]` directives, deduplicates MCP tool references, and builds a valid DAG with fan-in dependencies for parallel step groups. The LLM path is used only when fewer than 2 steps are found.
- **LLM-decomposed task IDs not extracted from standard output format** -- `_parse_task_block()` silently discarded the task ID value when it appeared as the first bare line of a block (the natural result of splitting on `**Task_ID**: `), always falling back to a randomly generated ID. This caused dependency cross-references between tasks to never resolve, making the phantom-dependency stripping (below) incorrectly strip all inter-task dependencies. Fix: the parser now detects a bare `task_N`-pattern first line and uses it as the task ID, which enables both duplicate detection and dependency resolution to work correctly for standard LLM output.
- **LLM-decomposed workflows drop steps via duplicate task IDs** -- When the LLM emitted two task blocks with the same `Task_ID`, the second silently overwrote the first in the task dict. Fix: `_parse_llm_decomposition()` now detects duplicate IDs, logs a warning, and keeps the first occurrence.
- **LLM-decomposed workflows trigger false cycle detection via phantom dependencies** -- When the LLM referenced a task ID that was never parsed (e.g. because its block failed), `validate_workflow_dag()` treated the unresolved reference as a cycle and called `_fix_workflow_cycles()`, which linearised the entire workflow. Fix: after parsing all task blocks, dependency lists are filtered to remove references to non-existent task IDs before the workflow is constructed, so the DAG validator only sees genuine cycles.
- **SOP workflows incorrectly flip to async mode** -- The async heuristic (`total_complexity * 0.5 minutes` vs a 30-second default threshold) was applied to all workflows including SOP-driven ones. A 4-task SOP with average complexity 3 estimated 6 minutes of execution, flipping to async and returning a job ID to the user instead of a result. SOPs with `bypass_approval: true` are pre-approved synchronous workflows where the user is waiting for an answer. Fix: SOPs with `bypass_approval: true` now force `use_async=False` before the complexity heuristic runs.
- **libpoppler not discoverable in SIF containers (take 2, correct fix)** -- The previous fix (v0.20260330.0) appended system library paths to `LD_LIBRARY_PATH` in `docker-entrypoint.sh`, but the server spawns SIF containers via `singularity exec ... python -m muxi.runtime.utils.run_formation`, bypassing the Docker entrypoint entirely. Additionally, the SIF detection used only `SINGULARITY_CONTAINER`, which is not set by Apptainer 1.0+ (which sets `APPTAINER_CONTAINER` instead). Fix: the `LD_LIBRARY_PATH`, `HF_HUB_OFFLINE`, and `TRANSFORMERS_OFFLINE` setup is now applied at the top of `run_formation.py` before any library imports, and the SIF detection checks `APPTAINER_CONTAINER` (Apptainer 1.0+), `SINGULARITY_CONTAINER` (SingularityCE / legacy), and `MUXI_SIF_MODE=1` (explicit override).

### Tests

- **40 new unit tests for SOP and workflow fixes** -- Added `tests/unit/test_sop_deterministic_parser.py` covering: deterministic SOP parser against real formation SOP files (customer onboarding, incident response, system report), parallel step detection and fan-in dependency building, graceful fallback when fewer than 2 steps are found, heading-format fallback, MCP tool server name extraction (slash handling), duplicate task ID rejection, phantom dependency stripping, SIF environment variable setup (all three detection modes), and async bypass logic for `bypass_approval` SOPs.

## 0.20260330.1 - MCP Connection Keep-Alive (connection_ttl)

### New Features

- **MCP connection keep-alive with TTL** -- MCP tool calls no longer reconnect/disconnect for every invocation. After tool discovery (which still disconnects), the first tool call establishes a connection that is kept alive and reused for subsequent calls. Each call resets the idle timer. A background reaper closes connections that have been idle longer than `connection_ttl` (default: 300 seconds / 5 minutes). Frequently-used servers stay connected indefinitely; idle servers close automatically. Set `connection_ttl: 0` for legacy ephemeral behavior (connect/execute/disconnect per call). Configurable globally under `mcp.connection_ttl` and per-server via `connection_ttl` in individual MCP server files. Connections are keyed by `(server_id, credentials_hash)` so different users never share a connection. All live connections are closed on formation shutdown.

## 0.20260330.0 - Response Latency Fixes & SIF Library Discovery

### Bug Fixes

- **Workflow synthesis times out on large SOP results** -- The `_synthesize_workflow_results` method created a synthesis LLM instance with the default 30-second timeout. When SOPs fetched large amounts of data (calendar events, emails, tasks), the combined context exceeded what the LLM could process in 30 seconds, causing a timeout followed by up to 3 retries with exponential backoff -- producing the 120-175 second silent gaps observed in production. The error surfaced as a generic synthesis failure, obscuring the real cause. Fix: increased the synthesis LLM timeout from 30s (default) to 120s, matching the adaptive timeout ceiling.
- **User identifier resolved from database 8 times per request** -- When `RequestContext.internal_user_id` was unavailable (fallback path), every memory collection operation called `resolve_user_identifier()` with `kv_cache=None`, hitting the database for the same immutable identifier-to-ID mapping repeatedly within a single request. Fix: added an in-process cache on `LongTermMemory._resolve_user_id_async()` that persists for the formation's lifetime, since the mapping is immutable once created.
- **PDF thumbnail generation fails in SIF containers** -- `libpoppler.so` was not discoverable inside SIF/Apptainer containers because Apptainer sets `LD_LIBRARY_PATH` to only `/.singularity.d/libs`, hiding system libraries installed via `apt-get` in the Docker image. Fix: the entrypoint now appends standard system library paths (`/usr/lib`, `/usr/lib/x86_64-linux-gnu`, `/usr/lib/aarch64-linux-gnu`) to `LD_LIBRARY_PATH` when running in SIF mode.

## 0.20260329.0 - MCP HTTP Transport CPU Busy-Loop Workaround

### Bug Fixes

- **MCP `type: http` servers cause 90%+ idle CPU** -- After the first tool call via an HTTP MCP server (streamable or SSE transport), the runtime process pinned a CPU core permanently with no active requests. Root cause is an upstream bug in `modelcontextprotocol/python-sdk` ([#1805](https://github.com/modelcontextprotocol/python-sdk/issues/1805)): the SDK's memory object streams use a zero-buffer capacity, so tasks blocked on `send()` during context teardown cannot be cooperatively cancelled. AnyIO's `_deliver_cancellation()` reschedules itself via `call_soon()` every event loop tick, producing an infinite busy-loop. Workaround: `StreamableHTTPTransport._cleanup()` and `HTTPSSETransport._cleanup()` now close `read_stream` and `write_stream` via `aclose()` before calling the SDK's `__aexit__()` methods. Since MUXI holds references to the same stream objects passed to `ClientSession`, closing them early causes internal tasks to receive `ClosedResourceError` and exit cooperatively, leaving no blocked tasks for AnyIO to spin on. The upstream fix (PR [#2147](https://github.com/modelcontextprotocol/python-sdk/pull/2147)) is confirmed working but not yet merged; this workaround will become a harmless no-op once it ships.

## 0.20260326.3 - Generative UI Skill

### New Features

- **Built-in `generative-ui` skill** - Added a new built-in skill that teaches agents when and how to create self-contained interactive HTML widgets, dashboards, diagrams, and visual explainers. The skill is designed to work with the existing `generate_file` tool and steers agents toward single-file `.html` artifacts with inline CSS/JS, responsive layouts, and dark-mode-friendly visuals.

### Tests

- **Unit coverage for `generative-ui`** - Added built-in skill loading, catalog, activation, metadata, and no-scripts assertions to `tests/unit/skills/test_skills.py`.
- **E2E test for RCE-backed HTML widget generation** - Added `e2e/tests/21_skills/test_21c2_generative_ui_rce.py` to verify that the skill activates correctly and produces an interactive `.html` artifact through the RCE-backed `generate_file` path.

## 0.20260326.1 - MCP Error Handling & Session-Aware Routing

### Bug Fixes

- **MCP tool completion events report success for errors** - When an MCP server returned `isError: true` in a structured response (e.g., 404 from Microsoft Graph API), the `process_structured_output` method fell through to the legacy code path because it only handled object-style results (with `hasattr`), not dict-style results from streamable HTTP transport. The completion event logged `success: true` and `is_error: false` despite the actual error. Fix: added dict result handling before the object-style path, correctly propagating the `isError` flag.
- **Follow-up messages routed to wrong agent** - When a user said "mark Make dinner as not important" (routed correctly to ms365-assistant), then followed up with "change Make dinner to normal", the routing LLM had no session context and routed to muxi-generalist instead. The generalist created a plan that delegated back to ms365-assistant but lost the conversation context. Fix: added session-aware routing -- the agent router tracks the last agent per session and includes a session context hint in the routing prompt, biasing follow-up messages toward the same agent.
- **Formation-level MCP connection fails when server not yet ready** - When an HTTP MCP server (e.g., ms365-mcp) was declared in `formation.afs` under `mcp.servers`, formation init tried to connect immediately. If the external MCP process hadn't finished starting, the connection probe failed and the server was skipped. Agent-level MCP worked because it connects lazily at tool-call time. Fix: added a single retry with a 3-second wait for HTTP MCP servers during formation init.
- **XML parameter extraction misses individual parameter tags** - The `_extract_json_from_response` method only handled Anthropic's `<parameter name="arguments">{...}</parameter>` wrapper format. When the LLM returned individual `<parameter name="key">value</parameter>` tags (the more common XML tool-call pattern), extraction failed and the tool call was skipped after retry. Fix: added extraction of individual parameter tags, building a dict from name/value pairs with JSON parsing for nested values.

## 0.20260326.0 - Planning Truncation & Tool Chain Reconciliation

### Bug Fixes

- **Planning response truncated, dropping prerequisite tools** - The `_plan_before_execution()` LLM call used `max_tokens=1000`, which was too small for multi-step plans when many MCP tools are registered (e.g., 83 MS365 tools). The LLM compressed 3-step plans into 2 steps to fit, dropping prerequisite lookup tools (`list-todo-task-lists` before `list-todo-tasks`). Parameter inference then guessed display names (e.g., "Завдання") instead of actual IDs, causing `ErrorInvalidIdMalformed` from the Microsoft Graph API. Fix: removed the `max_tokens` cap entirely -- the LLM naturally stops when the JSON is complete.
- **my_steps diverges from steps array** - When the LLM produced a `steps` array with correct tool chaining but a `my_steps` array with missing prerequisite steps, the execution engine used the incomplete `my_steps`. Fix: added a reconciliation step that rebuilds `my_steps` from the canonical `steps` array when `steps` contains more `can_i_do_this=true` entries than `my_steps`.

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
