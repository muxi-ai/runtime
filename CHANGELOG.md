# Changelog

## v0.20260421.0

## v0.20260421.0

### Native migration to a2a-sdk 1.0

`a2a-sdk 1.0.0` (released 2026-04-20) is a breaking rewrite of Google's Agent-to-Agent SDK. The top-level `A2AClient` helper is gone, enums moved to `SCREAMING_SNAKE_CASE`, `Part` types were flattened into a protobuf `oneof`, `AgentCard.url` was replaced by `supported_interfaces[]`, and `AgentCapabilities` became a fixed-field protobuf message (no per-capability metadata dict). v0.20260420.1 pinned `a2a-sdk<1.0` as an emergency stop; this release replaces every call site with the native 1.0 API. The migration touches 10 production files plus a new helpers module and is accompanied by a full unit + integration + e2e test harness.

- **`services/a2a/_sdk_helpers.py` (new)** -- centralizes the protobuf glue so no other file has to know about it. Exports `make_text_part`, `make_data_part`, `make_message`, `parts_to_muxi_list`, `muxi_part_to_sdk`, `dict_to_struct`, plus constants for `Role`, `TaskState`, and the `Part.content` oneof. The 1.0 `Part.data` field requires `google.protobuf.Value(struct_value=Struct)` rather than a raw dict; `Message.metadata` accepts a `Struct` directly; `MessageToDict` is used for all SDK -> MUXI shape conversions. Every other A2A file now imports from this module instead of reimplementing the glue.
- **`services/a2a/models_adapter.py` (rewrite)** -- the old `isinstance(part, TextPart)` / `.capabilities.items()` code silently returned empty parts against both 0.3 (RootModel-wrapped parts) and 1.0 (protobuf parts). Rewritten to route capability metadata through `AgentCard.skills[]` with tag-encoded metadata plus a `_muxi_metadata` sentinel skill for MUXI-specific extensions, and to derive `url` from `supported_interfaces[0].url`. This fixes three silent-failure modes documented as xfail markers in the test harness: the Part isinstance bug, the `AgentCapabilities` dict bug, and the per-capability metadata drop.
- **`services/a2a/auth/outbound.py` (rewrite `create_scheme`)** -- `APIKeySecurityScheme` renamed its fields (`api_key`/`header_name` -> `name`/`location`). Credentials are no longer stored on the scheme object at all; the auth manager now keeps a `_credentials` side-map keyed by scheme id. `HTTPAuthSecurityScheme` is used for bearer auth with a fixed `scheme="bearer"`.
- **`services/a2a/server.py` (rewrite)** -- the 1.0 SDK removed `SendMessageSuccessResponse` / `JSONRPCError` wrapper types in favor of a plain dict JSON-RPC envelope. Introduced `_jsonrpc_error` / `_jsonrpc_success` helpers and switched to dict-shape part parsing (`parts: [{"text": ...}]` rather than strict protobuf construction) to avoid 1.0's strict oneof validation rejecting incoming requests from older clients.
- **`services/a2a/client.py` (rewrite)** -- `A2AClient` is gone. The `A2AService` facade now wraps `create_client(url)` for each call and iterates `async for StreamResponse in client.send_message(request)`, collecting payloads by oneof tag (`task` / `message` / `status_update` / `artifact_update`).
- **`services/a2a/registry_client.py` (rewrite)** -- the previous health check used `A2AClient.send_message(health_check_message)` and inspected the error string for "method not allowed" / 405. Replaced with a plain `httpx.AsyncClient.get("/health", timeout=5)` that treats any <500 response as healthy (handles registries that don't implement `/health` but are otherwise reachable). The `sdk_clients` dict is kept as an empty `Dict[str, Any]` for API compatibility; registry traffic uses the shared httpx client directly.
- **`services/a2a/agent_transport.py` (rewrite)** -- 1.0's `ClientTransport.send_message` takes `SendMessageRequest` and returns `SendMessageResponse` (non-streaming), not `MessageSendParams`. The AgentTransport now builds a `SendMessageResponse(message=reply)` after dispatching to the internal handler.
- **`formation/overlord/a2a_messaging.py` (rewrite)** -- external routing now goes through `create_client(url)` + `async for StreamResponse`. Preserves the service-id matching logic that maps MUXI destinations to external registry endpoints. `a2a.client.middleware.ClientCallContext` moved to `a2a.client.ClientCallContext`.
- **`formation/overlord/a2a_coordinator.py` (rewrite external-routing block)** -- mirrors the `a2a_messaging` pattern. Collects the first `message` or `task` payload from the StreamResponse iterator and returns early; ensures the client is closed in a `finally`. `SendMessageRequest` no longer accepts `id`/`params` fields — the request is built with `message=` and `metadata=` directly.
- **`formation/overlord/overlord.py` (rewrite `_initialize_a2a_client_factory`)** -- `ClientFactory.register` now takes a `TransportProducer` callable of shape `(AgentCard, str, ClientConfig) -> ClientTransport` rather than a transport instance. The overlord wraps a singleton `AgentTransport` in a closure producer and also stores it on `self.agent_transport` so callers that need synchronous access (like `a2a_messaging._get_agent_transport`) don't have to go through the factory.
- **Dependency pins (`pyproject.toml`)** -- `a2a-sdk>=1.0,<2.0`, and a new `protobuf>=5.29.5,<6` constraint. `protobuf 6.x`'s `json_format.MessageToDict` is incompatible with the Struct/Value shapes the SDK produces; pinning to `5.29.x` keeps the conversion path working until the ecosystem catches up.

### Architectural Notes

- **Protobuf glue lives in exactly one place.** `_sdk_helpers.py` is the canonical translation layer between MUXI's dict-shaped internal messages and the SDK's protobuf messages. Any new A2A code (registries, servers, clients, transports) must build messages through these helpers rather than touching protobuf construction directly. This contains the blast radius of any future SDK schema change to a single file.
- **Capability metadata rides on `AgentCard.skills[]`.** SDK 1.0 made `AgentCapabilities` a fixed-field protobuf message (`streaming`, `push_notifications`, `extensions`, `extended_agent_card`); it no longer carries per-capability descriptions or arbitrary metadata. The adapter now serializes each MUXI `A2ACapability` as an `AgentSkill` (one skill per capability) with tag-encoded metadata (`muxi:meta=<json>`) and adds a `_muxi_metadata` sentinel skill for extensions that don't map onto `AgentSkill` directly. Round-trip preserves `name` / `description` / `enabled` / `metadata`.
- **The `sdk_clients` dict is intentionally empty.** `RegistryClient` previously kept one `A2AClient` per registry; in 1.0 there is no persistent client shape — `create_client(url)` builds a fresh `Client` per call, which internally reuses the httpx connection pool for HTTP-transport registries. The `sdk_clients` attribute is preserved as `Dict[str, Any]` for API compatibility; callers iterating it get zero items, which is the correct no-op.
- **Transport producers let the same AgentTransport back every `agent://` client.** `ClientFactory.register` takes a callable now instead of an instance. Rather than instantiating a new AgentTransport per create_client call, the producer closure captures the overlord's singleton and returns it verbatim — semantically equivalent to the old "register an instance" API, and the overlord keeps a direct reference for callers that don't want to go through ClientFactory at all.
- **Health checks decoupled from the SDK.** The pre-migration health check used the A2A message protocol and inspected error strings for 405 to decide whether a registry was "healthy but not accepting messages". With the SDK-shaped health check removed, registries can evolve their health probe independently — a plain `GET /health` with the shared httpx client is faster, less brittle, and treats any <500 response as alive (so registries without a `/health` handler still count as reachable).
- **No behavioural changes outside the SDK boundary.** All 10 production files were rewritten to preserve their existing public contracts. MUXI callers of `overlord.send_a2a_message` / `overlord.register_with_external_registry` / `A2AService.send_message` see the same inputs, outputs, and error semantics. The xfail markers in the Phase-1 test harness (documenting pre-existing silent-failure modes against 0.3) all flipped to XPASS against 1.0 and were removed — the rewrite fixes those bugs as a side effect rather than reproducing them.

### Tests

**New unit tests** (40 assertions across 3 files):

- `tests/unit/test_a2a_messaging.py` (8 tests) -- validates `convert_from_internal_message` produces the `parts` shape MUXI expects, and that `convert_from_external_response` correctly unwraps text / data responses and wraps empty responses as errors.
- `tests/unit/test_a2a_models_adapter.py` (8 tests, 3 xfail markers cleared) -- round-trips messages (text + data), round-trips AgentCards (scalar fields + capabilities), round-trips authentication, and asserts capability metadata is preserved through the skills[] encoding. The three xfail markers that previously documented the `isinstance(part, TextPart)` / `AgentCapabilities.items()` / per-capability metadata drop bugs are all cleared as XPASS.
- `tests/unit/test_a2a_auth_outbound.py` (18 tests, 1 xfail marker cleared) -- validates `AuthCredentials` accepts / rejects expected shapes, validates `apply_authentication` injects the right header per auth type (API key custom header + default `X-API-Key`, bearer `Authorization`, basic-auth `base64(user:pass)`), validates `apply_sdk_authentication` is a noop when no scheme is registered, and validates `create_scheme` constructs `APIKeySecurityScheme` with 1.0's `name=`/`location=` fields.

**New integration tests** (6 assertions, new `tests/integration/` package):

- `tests/integration/test_a2a_server_roundtrip.py` -- boots an in-process `A2AServer` with a registered echo agent and exercises the HTTP surface: `/health`, `/agents`, legacy `POST /agents/{id}/message`, unknown-agent error path, and the 1.0-shape SDK request path with and without extracted text. The 1.0 SDK path's xfail marker (previously documenting the `sdk_to_muxi_message` silent-empty bug) is cleared as XPASS.

**New e2e smokes** (2 tests, `e2e/tests/7_orchestration/`):

- `test_7b1_a2a_internal_messaging.py` -- SDK-binding smoke against the 1.0 API. Asserts `a2a-sdk` reports version `1.0.0`, that string / dict / parts-dict all convert to `SDK Message` correctly, and that SDK -> MUXI round-trip recovers all parts. Finishes in <10s.
- `test_7b2_a2a_external_messaging.py` -- boots `A2AServer` + echo agent in-process and walks the HTTP surface (`/health`, `/agents`, legacy POST, unknown-agent error). Finishes in <1s.

**Formation swap** (1 e2e test unblocked):

- `e2e/tests/7_orchestration/formations/formation-multi-agent-segregated/agents/project-manager.yaml` -- swapped Linear MCP (`https://mcp.linear.app/sse`) for the filesystem MCP (same pattern as the neighbouring `it-support` agent) so `test_7b1_internal_a2a.py` can run in environments without Linear credentials. The A2A delegation path (`it-support` -> `project-manager`) is preserved; only the downstream side-effect (Linear issue -> filesystem file) changed.

### Validation

- **Phase 1 unit + integration suite (`tests/unit/test_a2a_*.py` + `tests/integration/test_a2a_server_roundtrip.py`): 44/44 pass against `a2a-sdk==1.0.0`.** All 5 xfail markers (3 in models_adapter, 1 in auth_outbound, 1 in server_roundtrip) flipped to XPASS and were removed.
- **Broader unit suite: 605 passed, 3 skipped, 1 pre-existing unrelated failure** (`tests/unit/rce/test_rce_client.py` asserts `client_version == '0.1.0'` but the runtime reports `0.20260308.2`; pre-dates this migration).
- **A2A e2e sweep (5 tests): 5/5 pass** -- `test_7b1_a2a_internal_messaging.py` (6.6s), `test_7b1_internal_a2a.py` (25.3s, unblocked by Linear->filesystem swap), `test_7b2_a2a_external_messaging.py` (0.8s), `test_7b3_a2a_discovery.py` (22.4s), `test_19r1_a2a.py` (19.8s).
- **Random e2e sample (20 tests across 11 areas): 20/20 pass** -- 1_foundation, 2_memory (3), 3_multimodal (5), 4_mcp (2), 7_orchestration (2, including the new a2a internal messaging smoke), 9_async, 11_formatting, 12_scheduling (2), 13_triggers, 18_observability, 21_skills.
- **`scripts/validate_events.py`: 1206/1206 observe() calls validate (100%).**
- **Lint: `black --check` clean across all 12 touched files.**

### Breaking changes

- **`a2a-sdk<1.0` is no longer supported.** Anyone pinning `a2a-sdk==0.3.x` alongside this runtime will get an `ImportError` at startup (`a2a.client.A2AClient` no longer exists). The new pin is `a2a-sdk>=1.0,<2.0`.
- **`protobuf>=6.0` is incompatible with this runtime.** `google.protobuf.json_format.MessageToDict` in 6.x rejects the Struct shapes the SDK produces. The new pin is `protobuf>=5.29.5,<6`.
- **`AgentCapabilities.items()` is no longer callable.** Any downstream code that treated MUXI's SDK AgentCard as having a dict-shaped `capabilities` field must now walk `AgentCard.skills[]` (preferred) or call `ModelsAdapter.sdk_to_muxi_agent_card(card).capabilities` to get the MUXI-shape dict back.
- **`RegistryClient.sdk_clients` is always empty.** Code iterating it now gets zero items. External callers that want to speak A2A to a registry should build their own `create_client(url)` instance per call.

### Known issues deferred to next release

- **Per-request client construction overhead.** `create_client(url)` builds a fresh `Client` per `send_message` call, which internally reuses the shared httpx connection pool but re-resolves the agent card on every call. For hot-path external A2A traffic this may add 10-50ms per request depending on DNS + TLS cache state. If profiling shows this is a bottleneck, a future release can cache resolved `AgentCard` objects and reuse them across calls.
- **`APIKeySecurityScheme.location` is always "header".** SDK 1.0 supports `location="query"` and `location="cookie"` but MUXI's `create_scheme` hardcodes header. If anyone needs query-string or cookie-based API keys, extend `create_scheme` accordingly.
- **StreamResponse `status_update` and `artifact_update` payloads are dropped.** `a2a_messaging._send_external_message` and `a2a_coordinator` iterate the StreamResponse but only surface `message` and `task` payloads back to MUXI. Incremental status and artifact updates are ignored. Fine for request/response-style agents; future streaming agents will need richer handling.

## v0.20260420.1

### Silent-Failure Fixes on Free-Text MCP Payloads (Google Calendar + Gmail)

The v0.20260420.0 release hardened placeholder resolution for MS Graph's structured JSON shapes (MS365 MCP). Production traffic on the Google Calendar / Gmail MCPs surfaced three remaining silent-failure modes because those servers return **free-text blobs**, not structured lists. All three traced back to the placeholder pipeline assuming structured payloads.

- **Text-block predicate fallback (Google Calendar: filtered placeholder dropped)** -- `{{EVENT_SEARCH[summary='Spark Test 2'].id}}` silently dropped because the google-mcp `get_events` tool returns a bulleted text blob (e.g. `- "Spark Test 2" (Starts: ...)\n  ID: rnnbrh...`), not a JSON list of dicts. v0.20260420.0's `_filter_records_by_predicate` walked structured records only, found zero matches, degraded to the legacy path, dropped the literal token, and the downstream `manage_event` call failed silently. Fix: when the structured walk returns zero matches the filter now falls back to a text-block parser.
    - New `_parse_text_blocks_into_records` splits the payload into bullet-prefixed chunks (`- ` / `* ` lines), parses each into a synthetic dict, and hands the list to the existing predicate matcher.
    - New `_split_text_into_bulleted_blocks` groups contiguous bullet-prefixed lines into block strings, preserving follow-on indented metadata (`Description: ...`, `ID: ...`) inside the same block.
    - New `_text_block_to_record` extracts the quoted title into every title alias (`summary`/`title`/`name`/`subject` via `_TEXT_BLOCK_TITLE_ALIASES`) plus every inline `Key: value` pair, yielding a dict the existing `_record_matches_predicate` can test.
    - New regex `_TEXT_BLOCK_BULLET_PREFIX` (`^\s*[-*]\s+`) and tuple `_TEXT_BLOCK_TITLE_ALIASES` centralize the detection rules; both are class attributes on `Agent` so they're discoverable alongside `PLACEHOLDER_INDEX_KEY`.
    - The fallback is conservative: it runs only when the structured predicate walk returned no matches, so predicate-on-structured payloads keeps the exact same precedence it had in v0.20260420.0.
- **Embedded placeholder substitution (Gmail: literal `{{DRAFT.body}}` sent to MCP)** -- The planner legitimately authored `body="{{DRAFT_CONTENT.body}}\n\nHappy Birthday!"` — a placeholder token spliced into a larger string alongside a literal suffix. v0.20260420.0's substitution only triggered when the ENTIRE value matched `_is_placeholder_like_value`; mixed strings (token + literal) fell through untouched, reaching MCP as literal `{{...}}` text and creating a duplicate malformed draft instead of updating the existing one. Fix: a new embedded-scan pass runs when the whole-string matcher declines.
    - New regex `_EMBEDDED_PLACEHOLDER_SCAN` captures every `{{...}}` token inside a larger string (parses the exact same placeholder shape the explicit-form matcher accepts, but without anchoring).
    - New `_contains_embedded_placeholder` staticmethod returns True for strings containing at least one token but which are not themselves a bare-placeholder string.
    - New `_substitute_embedded_placeholders` instance method splices each resolved token back into the surrounding text. Only **scalar** resolved values are spliced (strings, numbers, bools); structured payloads (dict / list) are left as literals so the leftover-strip pass can drop them with a loud warning — we never want to stringify-dump a JSON blob into an email body.
    - Wired into both the top-level param path (`_substitute_step_parameter_placeholders`) and the recursive nested path (`_substitute_nested_placeholders` string-leaf branch). Both paths invoke the embedded-scan only after the whole-string matcher declines, so v0.20260420.0's explicit-predicate / kind-aware / cross-placeholder precedence is preserved exactly.
    - `_find_unresolved_placeholder_leaves` now iterates `_EMBEDDED_PLACEHOLDER_SCAN` matches inside string leaves so the leftover-strip pass sees and logs partially-unresolved embedded tokens (path + literal token) the same way it handles whole-placeholder leaves.
- **`--- FIELDNAME ---` section separator in field extraction (Gmail: `.body` unextractable)** -- The Gmail MCP emits `--- BODY ---\n<body text>\n` to separate the message body from the `Subject: / From: / To: /` metadata header. v0.20260420.0's `_extract_field_values_from_text` recognized `Body: ...` label lines and `"body": "..."` JSON pairs but not the section-separator form, so `{{DRAFT_CONTENT.body}}` found no match, fell through to the scalar-payload fallback, and returned nothing. Fix: a new Pattern 4 runs **first** (before the looser label and JSON patterns) and short-circuits the rest when it matches.
    - Pattern 4 matches `(?:^|\n)\s*-{3,}\s*<field>\s*-{3,}\s*\n(<capture>)(?=\n\s*-{3,}\s*<next-field>-{3,}|\Z)` — strict about the dash-framed opening (prevents false positives on markdown horizontal rules) and lazy on the capture with a next-section / end-of-text lookahead so the body stops at the next `--- ATTACHMENTS ---` etc.
    - Section contents bypass the aggressive character normalization `_accept` applies to label captures — bodies are free-form text with punctuation, newlines, CR-LF, and mixed whitespace, and must be preserved verbatim for downstream mutation calls (draft update, calendar event description, etc.).
    - **Pattern precedence change**: Pattern 4 now runs FIRST and `continue`s the loop when it matches. Before, Pattern 1 (label-style with `\s`-separator) would match `Body paragraph one.` as `label=Body, value=paragraph` from inside the section body and pollute the result set. Running Pattern 4 first with short-circuit makes the section separator authoritative when it fires. Non-section payloads (label-only, JSON-only) keep the exact same behavior — Pattern 4 declines silently and the loop continues to Patterns 1-3.

### Architectural Notes

- The v0.20260420.0 predicate pipeline assumed "structured JSON → records → match". Google MCPs return "free text → bulleted blocks → extract". This release bridges the two shapes **at the record-iterator layer** so the rest of the pipeline (predicate matching, field extraction, cross-placeholder fallback, leftover-strip, repair-plan) works unchanged against text payloads. The Fix 1 / Fix 3 helpers are the canonical "free-text adapter" for anything downstream of `_iter_result_records`.
- Embedded-placeholder substitution promotes the contract from "value is a placeholder" to "value MAY contain placeholders". This is the shape the planner already produces for composed outputs (append-a-signature, prefix-a-subject, splice-a-field). The resolution rule stays conservative: scalars are spliced, structured values stay literal, unresolved tokens get logged and dropped.
- `_EMBEDDED_PLACEHOLDER_SCAN` is deliberately a **non-anchored** variant of the whole-value placeholder regex. It is registered as a class attribute on `Agent` so the unresolved-leaf detector and the embedded substituter share the same source of truth for "what counts as a token".
- Pattern 4 is order-sensitive. Any new field-extraction pattern added later must decide whether it is more specific than Pattern 4 (unlikely) or less specific (most cases) and inserted accordingly. The in-code comment documents this invariant.
- All three fixes are purely runtime-side. Zero LLM / MCP / prompt changes. `agent_planning.md` does not need updating — the planner already emits the shapes that now resolve correctly.

### Tests

**New unit tests** (`tests/unit/test_agent_planning_helpers.py`, 135 total in the file; 14 new under the `v0.20260420.0 regression tests` header):
- `test_parse_text_blocks_into_records_recovers_bulleted_google_calendar_events` -- google-mcp text payload parses into 3 dicts with title aliases (`summary`/`title`/`name`/`subject`) and inline `ID:`/`Description:`/`Location:` fields.
- `test_parse_text_blocks_into_records_returns_empty_for_non_bulleted_text` -- narrative prose without bullet prefixes yields no records.
- `test_filter_records_by_predicate_falls_back_to_text_blocks` -- predicate against a bulleted text payload matches the right block even though the structured walk finds nothing.
- `test_substitute_step_parameter_placeholders_resolves_predicate_on_text_payload` -- end-to-end: `{{EVENT_SEARCH[summary='Spark Test 2'].id}}` against the exact google-mcp payload resolves to the real event_id.
- `test_contains_embedded_placeholder_detects_mixed_strings` -- detects `{{X}}\n\nLiteral`, declines for bare `{{X}}` (the whole-string matcher handles those) and literal-only strings.
- `test_substitute_embedded_placeholders_splices_resolved_values` -- `"{{DRAFT.body}}\n\nHappy Birthday!"` + scalar resolution splices correctly and preserves the suffix.
- `test_substitute_embedded_placeholders_leaves_unresolved_tokens_intact` -- tokens with no matching payload stay literal (the strip-pass will then drop them).
- `test_substitute_embedded_placeholders_does_not_splice_structured_payload` -- dict/list payloads are NOT stringified into strings; token stays literal for downstream drop.
- `test_substitute_step_parameter_placeholders_resolves_embedded_body` -- full pipeline: Gmail draft payload with `--- BODY ---` section + embedded `{{DRAFT_CONTENT.body}}\n\nHappy Birthday!` resolves to real body + appended suffix.
- `test_find_unresolved_placeholder_leaves_detects_embedded_tokens` -- a single embedded unresolved token inside a larger string is reported with correct path.
- `test_find_unresolved_placeholder_leaves_detects_multiple_embedded_tokens` -- multi-token strings produce one leaf per token.
- `test_extract_field_values_from_text_recognizes_section_separator` -- `--- BODY ---\n<body>\n` extracts the full body, preserves whitespace/CR-LF/punctuation.
- `test_extract_field_values_from_text_section_separator_stops_at_next_section` -- body capture stops at the next `--- ATTACHMENTS ---` marker, doesn't bleed into subsequent sections.
- `test_extract_field_values_from_text_section_separator_not_confused_with_prose` -- bare `---` horizontal rules without a field name between them don't trigger a section match.

**New e2e test** (`e2e/tests/7_orchestration/test_7a7_text_payload_predicate_and_embedded_placeholder.py`):
- Five scenarios using the exact payload fixtures captured from the v0.20260420.0 production log:
    1. `calendar_predicate_on_text_payload` -- `{{EVENT_SEARCH[summary='Spark Test 2'].id}}` resolves to the correct event_id against the google-mcp `get_events` bulleted text blob.
    2. `calendar_predicate_routes_to_right_event` -- predicate `[summary='Ruby Daily Sync']` selects the second event (not the first), proving the text-block filter actually filters.
    3. `calendar_unmatched_predicate_drops_and_warns` -- an unmatched predicate drops the non-required param AND emits the `placeholder.unresolved` warning event.
    4. `gmail_embedded_body_substitution` -- Gmail draft with `--- BODY ---` section + embedded `{{DRAFT_CONTENT.body}}\n\nHappy Birthday!` resolves end-to-end, preserving the appended literal.
    5. `gmail_unresolved_embedded_flagged` -- a payload with no recoverable `body` field leaves the embedded token literal AND the unresolved-leaf detector reports it.
- 5/5 pass.

### Validation

- Full unit suite: **567 passed, 3 skipped, 1 pre-existing failure** (`test_rce_client.py` hardcoded version assertion — unrelated to placeholder work; confirmed via `git stash`).
- Targeted placeholder helper suite: 135/135 pass (121 baseline + 14 new).
- New e2e test (`test_7a7_text_payload_predicate_and_embedded_placeholder`): 5/5 scenarios pass.
- Neighbouring e2e tests to guard against regressions: `test_7a5_placeholder_predicate_resolution` 7/7, `test_7a6_nested_and_index_placeholder_resolution` 6/6.
- Random e2e sample (10 tests across 8 areas): 9/10 pass. The single failure (`9_async/test_9a3b_with_approval`) reproduces identically on pristine `develop` HEAD and is caused by the planner LLM short-circuiting the approval message `"Yes, please proceed with this plan"` to an empty plan — upstream of all placeholder-resolution code.
- `scripts/validate_events.py`: 1209/1209 observe() calls validate (100%).

### Known issues deferred to next release

- **Multi-word label-line capture truncation** -- `Subject: Meeting tomorrow` still extracts only `"Meeting"` because Pattern 1's value capture excludes whitespace. Orthogonal to the three bugs fixed here (body resolution is via Pattern 4; subject already half-worked pre-fix). Candidate for a dedicated "header-line" pattern in the next release.
- **Short follow-up clarification loss on context-free recall** -- the "pull it up" / "try again" loss-of-context issue noted in the v0.20260420.0 field report is NOT addressed here; root cause is in the buffer-memory injection into `=== CONVERSATION CONTEXT ===`, a separate surface from placeholder resolution.
- **Gmail `update-draft` tool semantics mismatch** -- the Gmail MCP's `update_draft` actually creates a new draft, requiring explicit `draft_id` plumbing. Tool-contract issue on the MCP side, not a runtime bug.

## v0.20260420.0

### Silent-Failure Fixes on v0.20260418.0 Placeholder Pipeline

- **`[N]` positional index now supported in placeholder predicates (Dev #1 v0.20260418.0 Excel B2)** -- The LLM emitted `{{WORKSHEET_LIST[0].id}}` to mean "first worksheet's id"; v0.20260418.0's parser accepted only `[key=value]` predicates and rejected bare integers, so the placeholder degraded to the legacy first-match path. The kind-aware cross-placeholder fallback then bound `workbookWorksheetId` to the Book.xlsx `driveItemId`, MS Graph returned 404 on `get-excel-worksheet`, and the failure surfaced as a confusing "could not obtain access token" message. New runtime helpers:
    - `Agent.PLACEHOLDER_INDEX_KEY` (`"__index__"`) reserves an internal marker key for positional selectors; parser-generated so callers cannot use it as a real field name.
    - `_parse_placeholder_predicate` now accepts `[N]` and `[-N]` → returns `{__index__: N}`. Non-integer numerics (`[1.5]`) and bare identifiers (`[abc]`) without `=` still fail as before.
    - `_iter_indexable_records` resolves the "most relevant" list of records for positional selection. Prefers (1) payload as top-level list of dicts, (2) common wrapper keys (`value`/`items`/`data`/`results`/`records`/`matches`/`files`/`messages`/`events`) whose value is a list, (3) depth-first walk for the first list of dicts. Empty list on out-of-range or no-list payloads so callers treat both as "no match".
    - `_filter_records_by_predicate` dispatches on `__index__` before value matching; index path is exclusive (rejects mixed with `key=value` at the parser level, defensive bail-out here). Returns `None` / `[]` on out-of-range indexes.
    - `_record_matches_predicate` defensively strips `__index__` so direct callers with a mixed predicate don't crash.
- **Recursive nested placeholder substitution (Dev #1 v0.20260418.0 OneDrive move)** -- The LLM correctly authored `parentReference: {id: "{{SPARK_FOLDER_SEARCH[name='Spark Test'].id}}"}`, the predicate syntax was already supported in v0.20260418.0, yet the runtime sent a literal `"{{SPARK_FOLDER_SEARCH[name='Spark Test'].id}}"` string to MS Graph because `_substitute_step_parameter_placeholders` iterated only top-level param values. MS Graph returned 200 and silently ignored the bogus parentReference; the file never moved. Fix: the substitution pipeline now runs a two-pass design.
    - Top-level pass (unchanged) applies the full schema-aware machinery (auto-inferred predicates, kind-based fallback, cross-placeholder resolution) to each top-level param whose value is itself a placeholder string.
    - New nested pass `_substitute_nested_placeholders` walks every string leaf inside dict/list top-level params and substitutes placeholders using explicit predicate / field-hint resolution. Schema-driven inference is intentionally skipped for nested leaves because per-leaf schema is unavailable; the LLM authored the placeholder explicitly and we honor it literally.
    - Depth cap `_NESTED_SUBSTITUTION_MAX_DEPTH = 8` guards pathological payloads. MS Graph shapes rarely exceed 4 levels; 8 leaves comfortable headroom.
    - Bare `{{FOO}}` nested references only substitute when the referenced payload is a scalar; structured payloads are left as literals so the leftover-strip pass can drop them with a loud warning.
- **Recursive leftover stripping + loud `placeholder.unresolved` warnings (Dev suggestion, defense-in-depth)** -- `_strip_leftover_placeholder_parameters` now walks dicts/lists recursively. A non-required top-level param containing ANY unresolved placeholder leaf at ANY depth is dropped before the MCP call. Required params with nested unresolved leaves are left intact (the repair-plan flow reacts to them) but a warning event is still emitted.
    - `_find_unresolved_placeholder_leaves` enumerates every placeholder-like string leaf with dotted/indexed path tracking (`parameters.parentReference.id`, `attendees[0].emailAddress.address`).
    - A single `AGENT_PLANNING` WARNING event with `phase: "placeholder.unresolved"` reports every unresolved leaf (path + literal placeholder) alongside the list of dropped top-level params. Devs now see silent failures in the log stream the instant they happen, instead of puzzling over a 200-but-noop response.
- **Repair-plan flow fires for nested required params (Dev #1 v0.20260418.0 OneDrive move, root-cause)** -- `_has_resolved_required_parameter_value` now recursively inspects dict/list required params for unresolved placeholder leaves via `_find_unresolved_placeholder_leaves`. Without this, `_get_unresolved_required_parameters` could not see the nested literal inside `parentReference.id`, the repair-plan attempt never fired, and the failed move silently shipped. The added check is O(leaves) with a tiny constant; no measurable overhead on hot paths.
- **`agent_planning.md` PLACEHOLDER RULES block extended** -- The strict contract now documents:
    - `[N]` / `[-N]` positional index syntax with the exact Excel scenario (`{{WORKSHEET_LIST[0].id}}` → first worksheet), and a caution that positional indexes are list-order-dependent and usually less safe than a name predicate.
    - Nested placeholder support: placeholders MAY appear inside dict/list parameter values (e.g. MS Graph's `parentReference: {id: "{{...}}"}`), every string leaf is substituted at any depth, and unresolved nested leaves emit a `placeholder.unresolved` warning and either drop the non-required parent or trigger repair-plan when required.

### Architectural Notes

- The three-tier resolution hierarchy from v0.20260418.0 now extends cleanly to nested values:
    1. **Explicit predicate / index** — `{{FILE_LIST[name='Book.xlsx'].id}}`, `{{WORKSHEET_LIST[0].id}}`, deterministic.
    2. **Auto-inferred predicate** — still only top-level; schema-driven inference needs per-param metadata unavailable for nested leaves.
    3. **Legacy first-match** — preserved at top level; nested pass leaves literals untouched and defers to the leftover-strip + repair-plan pipeline for diagnosis.
- The leftover-strip pass is now the canonical "last line of defense" against silent failures. Any literal `{{...}}` reaching MCP is a bug — the warning event + repair-plan flow ensures devs and the runtime both notice.
- `Agent.PLACEHOLDER_INDEX_KEY` is a class attribute (not a module constant) because predicate parsing is a staticmethod on the class; this keeps the reserved key discoverable in a single place. The marker is deliberately long and namespaced (`__index__`) so it cannot collide with real MS Graph field names.
- This closes all three silent-failure modes in the Dev #1 v0.20260418.0 report: `[N]` syntax, nested-dict substitution, and the loud warning devs requested for literal-placeholder pass-through.

### Tests

**New unit tests** (`tests/unit/test_agent_planning_helpers.py`, 121 total in the file; 13 new):
- `test_parse_placeholder_predicate_accepts_integer_index` -- `[0]`, `[3]`, `[-1]` parse to `{__index__: N}`; non-integer numerics / bare identifiers without `=` return None.
- `test_parse_placeholder_reference_supports_integer_index` -- `{{WORKSHEET_LIST[0].id}}` splits into (base, field='id', `{__index__: 0}`).
- `test_iter_indexable_records_prefers_top_level_value_wrapper` -- MS Graph `{value: [...]}` shape is used directly.
- `test_iter_indexable_records_handles_top_level_list` -- top-level list-of-dicts passes through.
- `test_iter_indexable_records_walks_nested_when_no_wrapper_match` -- depth-first fallback walk.
- `test_filter_records_by_predicate_dispatches_index_path` -- positive/negative/out-of-range indexes, collect_all parity.
- `test_extract_field_with_index_predicate_picks_positional_record` -- end-to-end extraction via index predicate.
- `test_substitute_step_parameter_placeholders_resolves_index_predicate` -- Excel B2 scenario; `{{WORKSHEET_LIST[0].id}}` resolves to the first worksheet's GUID, not driveItemId.
- `test_substitute_step_parameter_placeholders_resolves_nested_dict_placeholder` -- OneDrive scenario; `parentReference: {id: "{{...}}"}` substitutes correctly.
- `test_substitute_step_parameter_placeholders_resolves_nested_list_placeholder` -- attendees array with per-record predicate resolution.
- `test_substitute_step_parameter_placeholders_caps_recursion_depth` -- 20-deep pathological payload doesn't trigger RecursionError.
- `test_find_unresolved_placeholder_leaves_walks_nested_structures` -- leaf finder reports dotted/indexed paths for nested literals.
- `test_strip_leftover_placeholder_parameters_drops_top_level_with_nested_unresolved` -- non-required parent dict with nested literal gets dropped.
- `test_strip_leftover_placeholder_parameters_keeps_required_with_nested_unresolved` -- required parent kept so repair-plan can react.
- `test_has_resolved_required_parameter_value_rejects_nested_unresolved` -- dict/list required params with any nested literal report as unresolved.

**New e2e test** (`e2e/tests/7_orchestration/test_7a6_nested_and_index_placeholder_resolution.py`):
- Six scenarios covering `[0]` + `[-1]` integer indexing, nested-dict predicate substitution, recursive leftover-strip with warning, required-nested repair-plan trigger, and the combined `[0]` inside nested dict. Exercises the full placeholder pipeline end-to-end against MS Graph-shaped `list-excel-worksheets` and `search-onedrive-files` payloads. 6/6 pass.

### Validation

- Full unit suite: **553 passed, 3 skipped, 1 pre-existing failure** (`test_rce_client.py` hardcoded version assertion — unrelated to placeholder work).
- Targeted placeholder helper suite: 121/121 pass (108 baseline + 13 new).
- New e2e test (`test_7a6_nested_and_index_placeholder_resolution`): 6/6 scenarios pass.
- Random e2e sample: 3/3 pass (scheduling, MCP credentials, artifacts).
- ruff, black, mypy: clean on touched files.

### Known issues deferred to next release

- **MS365 tool selection collapse on A2A delegation (Dev #1 Excel Failure Mode 2, prior report)** -- still deferred; not a placeholder-resolution issue.
- **Repair-tool suggests `list-outlook-contacts` for drive-root-item recovery** -- pre-existing heuristic misrouting in `_build_auto_discovery_repair_plan`; orthogonal to this release.

## v0.20260418.0

### New Placeholder Contract — Collection Disambiguation

- **New predicate syntax in placeholder references (Dev #1 Excel Failure Mode 1)** -- The dotted placeholder contract is extended from `{{NAME}}` / `{{NAME.field}}` to also accept `{{NAME[key=value]}}` and `{{NAME[key=value].field}}`. This gives the planner a deterministic way to say "the record named X" when a prior step returned a collection. Without this, `{{FILE_LIST.id}}` silently resolved to whichever record `_iter_result_records` encountered first — in the reported Excel case that was the alphabetically-first `Attachments` folder, not the user's `Book.xlsx`, and passing a folder id to `list-excel-worksheets` produced the misleading "WAC 403 / could not obtain access token" error. New runtime helpers:
    - `_parse_placeholder_reference` now returns a 3-tuple `(base_key, field_hint, predicate)`.
    - `_parse_placeholder_predicate` parses the `[key=value]` body with typed values: single- or double-quoted strings, booleans, integers, floats, `null`/`none`, and bare identifiers.
    - `_record_matches_predicate` applies the predicate with normalized field names (so `[name=X]` matches `Name`, `display_name`, or `DisplayName`) and case-insensitive string comparison.
    - `_filter_records_by_predicate` walks `_iter_result_records` and returns matching records.
    - `_extract_field_from_result_payload` accepts an optional `predicate=` kwarg that filters records before field extraction. Text-chunk fallback is disabled under predicate mode because free-text payloads cannot be reliably filtered by structural field value.
    - Malformed predicate syntax (`[==]`, `[]`, etc.) degrades gracefully — the helper returns the untouched placeholder string so downstream resolution / repair-plan flows react normally.
- **Auto-inferred name predicate from `action_description` (Dev #1 Excel Failure Mode 1, defense-in-depth)** -- Layered on top of the new syntax as a backward-compatibility bridge. When the planner emits the legacy `{{FOO.field}}` form (no predicate) and the step's `action_description` explicitly names a resource, the runtime synthesizes a `{name|displayName|title|subject: X}` predicate automatically and applies it. This closes the "LLM hasn't learned the new syntax yet" gap without waiting for prompt compliance.
    - `_extract_named_resource_from_action` pulls a resource name from the description via three conservative matchers: double-quoted strings (`"Quarterly Report"`), single-quoted strings (`'Team Standup'`), backticked markdown code spans (`` `Book.xlsx` ``), and unquoted filenames with a recognized extension (`Book.xlsx`, `quarterly-report.pdf`). Bare capitalized words are deliberately excluded — they produce too many false positives in prose.
    - `_infer_auto_name_predicate` synthesizes the predicate only when three guards all hold: (1) the description names a resource, (2) the payload contains ≥ 2 records carrying the same name-field variant (genuine ambiguity), (3) at least one record actually matches the extracted name (prevents silent rewrites against resources the prior step never returned).
    - Synthesized predicates use the actual field variant present on matching records (`name`, `displayName`, `title`, or `subject`) so downstream matching — which is strict about key normalization — succeeds.
    - Precedence is unambiguous: an explicit `[key=value]` from the LLM always wins over the auto-inferred predicate. The auto-path only runs when the LLM emitted no predicate at all.
    - An `AGENT_PLANNING` INFO observability event is emitted every time auto-inference fires, carrying the inferred predicate, the original placeholder key, the field hint, and a truncated action description — so devs can see exactly when the runtime auto-corrected a plan.
- **`agent_planning.md` PLACEHOLDER RULES block extended** -- The strict contract now documents the predicate syntax with correct/wrong examples using the exact Book.xlsx scenario, the value-type cheat sheet (quoted strings, bools, numbers, bare identifiers), and the single-pair-only v1 limitation. The LLM learns the structure from the prompt; the runtime catches residual non-compliance via the auto-inference fallback.

### Architectural Notes

- This closes the "collection disambiguation" gap identified during the Dev #1 Excel debug session: our previous plan-execute model assumed shape-deterministic data flow (each step produces a single definite scalar / record). The predicate extension makes the contract expressive enough for list-returning tools, and the auto-inference fallback bridges legacy plans that don't yet use the new syntax. The runtime now has three tiers of resolution for multi-record payloads, in precedence order:
    1. **Explicit predicate** — `{{FILE_LIST[name='Book.xlsx'].id}}`, deterministic.
    2. **Auto-inferred predicate** — `{{FILE_LIST.id}}` with action "... to find Book.xlsx", heuristic but guarded.
    3. **Legacy first-match** — original behavior preserved when no named resource is available.
- `_parse_placeholder_reference` is now a 3-tuple API. Callers and test assertions updated accordingly (one production call site, one unit test). Safe to extend further (comma-separated AND predicates, not-equals operators) without breaking today's shape.
- The "collection disambiguation" work is purely runtime-side: zero LLM / MCP changes. The companion MS365 MCP tool-selection bug (Dev #1 Excel Failure Mode 2) — A2A-received agents getting 10 task-only tools instead of the 217 configured — is tracked separately and NOT addressed here.

### Tests

**New unit tests** (`tests/unit/test_agent_planning_helpers.py`, 515 total; 106 passed in the file):
- `test_parse_placeholder_reference_supports_quoted_string_predicate` -- `{{FILE_LIST[name='Book.xlsx'].id}}` splits into (`{{FILE_LIST}}`, `id`, `{name: 'Book.xlsx'}`); double- and single-quote forms both parse.
- `test_parse_placeholder_predicate_accepts_all_scalar_value_types` -- quoted strings, booleans, integers, floats, null, bare identifiers; malformed cases return None.
- `test_parse_placeholder_reference_rejects_malformed_predicate` -- `[==]` degrades gracefully to the untouched string.
- `test_record_matches_predicate_normalizes_field_names_and_string_case` -- `[name=X]` matches `Name`, `display_name`, `DisplayName`; string comparisons are case-insensitive; None matches missing/null.
- `test_extract_field_with_predicate_picks_correct_record_from_list` -- Dev #1 Excel scenario; predicate resolves to Book.xlsx id, not Attachments.
- `test_extract_field_with_predicate_skips_text_fallback` -- text payloads are not scanned when a predicate is active.
- `test_filter_records_by_predicate_collects_all_matches` -- `collect_all=True` path returns every matching record in order.
- `test_substitute_step_parameter_placeholders_uses_predicate` -- end-to-end substitution honors the predicate.
- `test_extract_named_resource_from_action_prefers_quoted_strings` -- quoted/backticked wins over incidental filenames.
- `test_extract_named_resource_from_action_detects_unquoted_filenames` -- filenames with recognized extensions qualify.
- `test_extract_named_resource_from_action_ignores_prose_without_markers` -- bare capitalized words do NOT qualify.
- `test_infer_auto_name_predicate_fires_for_ambiguous_multi_record_payload` -- Excel scenario; synthesizes `{name: 'Book.xlsx'}`.
- `test_infer_auto_name_predicate_returns_none_without_ambiguity` -- single-record payloads skip inference.
- `test_infer_auto_name_predicate_returns_none_when_named_resource_not_in_payload` -- guard prevents silent rewrite against absent resources.
- `test_infer_auto_name_predicate_adapts_to_displayname_field` -- synthesized predicate uses the actual field variant present on records.
- `test_substitute_placeholders_auto_applies_predicate_from_action` -- end-to-end Excel scenario without explicit predicate.
- `test_substitute_placeholders_respects_explicit_predicate_over_auto` -- explicit `[name=X]` wins over auto-inference.
- `test_substitute_placeholders_falls_back_to_legacy_without_named_resource` -- legacy first-match preserved for plans without named context.

**New e2e test** (`e2e/tests/7_orchestration/test_7a5_placeholder_predicate_resolution.py`):
- Seven scenarios exercising the full substitution pipeline against realistic MS365 Graph API response shapes (`list-folder-files`, `list-sharepoint-sites`) — explicit predicate path, auto-inference path, `displayName` variant adaptation, legacy fallback, explicit-beats-auto precedence, array-typed predicate filtering, and the guard that declines auto-inference when the named resource is not in the payload. Verifies both the resolved values and the emitted `AGENT_PLANNING` observability event.

### Validation

- Full unit suite: **515 passed, 27 skipped** (zero failures).
- Targeted placeholder helper suite: 106/106 pass (89 baseline + 7 predicate syntax + 10 auto-inference).
- New e2e test (`test_7a5_placeholder_predicate_resolution`): 7/7 scenarios pass.
- Random e2e sample: 5/5 pass (multimodal, artifacts, knowledge, clarification x2).
- ruff, black, mypy: clean on touched files.

### Known issues deferred to next release

- **MS365 tool selection collapse on A2A delegation (Dev #1 Excel Failure Mode 2)** -- when `ms365-assistant` is reached via A2A from another agent, semantic tool selection returns only 10 task/planner tools (out of 217 configured), excluding all drive and Excel tools. This is a runtime bug in the MCP tool-selection path, not a placeholder-resolution issue, and requires separate investigation. Tracked with the observability diagnostic proposal (log ranked-tools-before-cutoff for A2A-received planning).
- **Cross-placeholder explicit-predicate miss semantics** -- when the LLM writes `{{FOO[name='Nonexistent'].id}}` and no record matches, the existing kind-aware `_resolve_parameter_from_result_payload` fallback can still return a value of the matching schema kind. This is pre-existing behavior (not a regression from today's changes); tightening it to respect explicit-predicate intent is deferred as a targeted follow-up.

## v0.20260417.2

### Prompt Hardening

- **Planning prompt now pins the placeholder contract** -- Added a new `PLACEHOLDER RULES (strict)` block to `src/muxi/runtime/formation/prompts/agent_planning.md` that codifies the four failure modes surfaced by v0.20260416.x / v0.20260417.x field reports. The runtime-side guards shipped in v0.20260417.1 stay in place; this change reduces how often they're triggered by telling the planner upfront what valid plans look like.
    - **Syntax pinning**: only `{{UPPERCASE_NAME}}` or `{{UPPERCASE_NAME.field}}` is valid. No `<<NAME>>`, `${{NAME}}`, `{NAME}`.
    - **Reference consistency**: a later step may reference a prior output ONLY by the exact name assigned in its `output_placeholder`. Invented names now have an explicit "silently fails" warning with a correct/wrong example (drawn from the Calendar BUG-1 shape).
    - **Dotted field syntax documented**: `{{NAME.field}}` is now called out as the supported way to extract a single field from a prior step's output, and explicitly noted that array parameters are auto-collected by the runtime (don't emit a list literal).
    - **Sentinel values banned**: explicit list (`auto-injected`, `auto_fill`, `from_server`, `from_context`, `server_default`, `<to-be-provided>`, `to_be_injected`) with instruction to OMIT the key instead.
    - **Array extrapolation banned**: explicit prohibition against fabricating additional items (incrementing IDs, pattern-completed emails, guessed hashes) — drawn verbatim from the Gmail BUG-3 failure signature.

### Rationale

- Four of the last five placeholder-related regressions came from the LLM writing syntactically valid but semantically inconsistent plans. The runtime fixes in v0.20260417.1 catch these at multiple layers, but every catch adds latency and log noise. Pinning the contract up-front should drop the incidence rate materially on capable models (GPT-4o-mini, Claude Sonnet-4) while leaving the runtime guards as the safety net.
- Token cost: ~180 tokens added per planning call (~12% overhead on the planning prompt). Acceptable given the expected reduction in repair-plan / inference-fallback round-trips.

### Validation

- Full unit suite: **497 passed, 27 skipped** (no prompt-snapshot regressions).
- Random e2e: 5/5 pass.
- No code changes; isolated to `agent_planning.md`.

### Expected impact (by category)

| Category | Estimated reduction |
| --- | --- |
| Sentinel values (`auto-injected` etc.) | ~90% |
| Placeholder-name mismatch across steps | ~70% |
| Array extrapolation / fabrication | ~30-50% |
| Syntax variation (`<<NAME>>` etc.) | ~95% |

Runtime guards (v0.20260417.1) remain the source of truth and catch the residual.

## v0.20260417.1

### Bug Fixes

- **Placeholder substitution now extracts from free-text MCP results (CRITICAL, Gmail BUG-3)** -- When the LLM referenced `{{APRIL_10_MESSAGES.message_ids}}` and the Gmail search tool returned its results as a free-text blob (`"1. **Message ID:** aaa111\n2. **Message ID:** bbb222\n..."`), `_extract_field_from_result_payload` only walked structured records and returned `None`. The unresolved flag triggered parameter inference, which saw one real ID in context and hallucinated the other nine by incrementing the hex digits. Fix: added `_collect_text_chunks_from_payload` and `_extract_field_values_from_text` so the extractor also scans every text chunk for label-style (`Field: value`, `**Field:** value`) and JSON-style (`"field": "value"`) patterns, with case-insensitive matching across snake_case / camelCase / spaced / Title / ALL-CAPS variants. For array parameters (`message_ids`), extraction now collects every match, and singular / plural forms are probed automatically so `message_ids` still finds `Message ID: ...` labels.
- **Cross-placeholder fallback for LLM-invented placeholder names (CRITICAL, Calendar BUG-1)** -- The planner occasionally emits a placeholder name in step 2 that it never assigned in step 1 (e.g. `{{EVENT_ID_FROM_SEARCH}}` after only producing `{{EVENT_DETAILS}}`). `_substitute_step_parameter_placeholders` used to bail out on a missed key lookup and left the literal `{{EVENT_ID_FROM_SEARCH}}` string in the parameter dict. Because `event_id` isn't in the tool's `required` list for `manage_event`, the unresolved-required gate never fired and the literal placeholder went straight to MCP (→ 404). Fix: added `_resolve_parameter_across_all_results` which tries to bind the parameter to a value from the union of all successful prior results (structured + text fallback, including unadorned `id:` labels for `*_id` params); only commits when exactly one candidate exists so it won't silently pick wrong values from ambiguous multi-record sets.
- **Leftover literal placeholders are now stripped before the MCP call (CRITICAL, Calendar BUG-1 defense)** -- Added `_strip_leftover_placeholder_parameters`, called right before `_validate_tool_parameters`, which drops any non-required parameter still shaped like a placeholder (`{{...}}`, `<<...>>`, etc.) after all substitution / context / inference attempts have run. Required-parameter placeholders are preserved so the existing repair-plan flow can handle them.
- **Array inference validation drops fabricated items (CRITICAL, Gmail BUG-3 defense-in-depth)** -- `_validate_inferred_parameters_against_results` now handles list-typed parameters. Every inferred item must literally appear in a prior successful result (as a record value or in any text chunk); items that don't are dropped. If the entire list is fabricated, the parameter is removed so the repair-plan flow runs instead of sending an invalid array to MCP. This kills the Gmail "incrementing hex" hallucination pattern at the inference gate even when text extraction already fills most of the array from the prior result.

### Tests

- `test_field_name_variants_covers_snake_camel_space_and_all_caps` -- verifies the variant generator produces every common surface form.
- `test_extract_field_values_from_text_handles_markdown_and_json_patterns` -- `Field: value`, `**Field:** value`, and `"field": "value"` all resolved.
- `test_extract_field_values_from_text_collects_all_matches_for_arrays` -- Gmail BUG-3 shape; returns all 3 message IDs from the text blob.
- `test_extract_field_from_result_payload_falls_back_to_text_patterns` -- Calendar `ID: abc` line is found when looking for `event_id`.
- `test_extract_field_from_result_payload_collects_all_in_array_mode` -- deduplicated, order-preserving array extraction from text.
- `test_substitute_step_parameter_placeholders_resolves_dotted_array_param` -- Gmail BUG-3 end-to-end; `{{APRIL_10_MESSAGES.message_ids}}` resolves to `["aaa111", "bbb222", "ccc333"]`.
- `test_substitute_step_parameter_placeholders_cross_placeholder_fallback` -- Calendar BUG-1 shape; `{{EVENT_ID_FROM_SEARCH}}` with only `{{EVENT_DETAILS}}` in `my_results` resolves correctly.
- `test_substitute_step_parameter_placeholders_cross_placeholder_declines_ambiguous` -- ambiguous multi-result case leaves the literal placeholder for the strip step / repair flow.
- `test_strip_leftover_placeholder_parameters_drops_unresolved_non_required` -- Calendar BUG-1 defense; literal `{{...}}` on non-required params is dropped before MCP.
- `test_strip_leftover_placeholder_parameters_preserves_required_literals` -- required placeholders survive for the repair flow.
- `test_validate_inferred_parameters_drops_fabricated_array_items` -- Gmail BUG-3 defense; fabricated IDs are removed and only the real ID survives.
- `test_validate_inferred_parameters_removes_array_when_all_fabricated` -- the parameter is dropped entirely when no item is verified.
- `test_validate_inferred_parameters_keeps_real_ids_from_text_payload` -- items verified against text chunks are preserved.
- `test_collect_text_chunks_from_payload_walks_nested_structures` -- nested `structuredContent` / `content[].text` serializations are fully visited.

### Validation

- Full unit suite: **497 passed, 27 skipped**.
- Targeted placeholder / inference tests: 88/88 pass.
- ruff, black, mypy: clean.

### Known issues deferred to next release

- **Gmail cross-request context loss (Bug 2)** -- when a user asks follow-up questions that reference an ID the agent mentioned in a prior turn (e.g. "pull content from the draft I sent"), the planner occasionally fabricates a new ID instead of reusing the real one from buffer memory. Needs a structured tool-output memory layer visible to the planner; not a substitution / inference bug and outside the scope of this release.
- **Calendar date drift in response synthesis (Bug 2)** -- planner sees the correct current date (`v0.20260416.1` fix confirmed via log), but occasional drift persists in the final user-facing response. Needs a separate trace against response synthesis; not reproduced in this pass.
- **Repair-tool domain mismatch** -- still fires for non-`auto-injected` sentinel cases. Tracked.
- **Scheduled-job response delivery** -- still requires webhooks; synchronous completion (`v0.20260416.3`) keeps DB state correct.

## v0.20260417.0

### Bug Fixes

- **Repair-tool selection now respects resource domain** -- The auto-discovery repair scorer in `_build_auto_discovery_repair_plan` previously had no notion of resource domain, so a `list-mail-folders` or `search-sharepoint-sites` call could be chosen to repair a failed `get-drive-root-item` even though both live on the same `ms365-mcp` server. Fix: added `_DOMAIN_TOKENS` (an unambiguous-token taxonomy for mail, calendar, drive, sharepoint, chat, contact, task, and note domains) and `_get_tool_domain_tags()`. When both the failed tool and a candidate carry unambiguous domain tags, the scorer now adds +4 for overlapping domains and -15 for disjoint domains, which is enough to drop cross-domain candidates below the `score <= 0` cutoff when the only positive signal is a verb match on the same server. Generic tokens (`file`, `folder`, `item`, `message`, `page`, `list`, etc.) are deliberately excluded so legitimately ambiguous tools stay untagged and neither incur nor cause a penalty.

### Tests

- `test_get_tool_domain_tags_classifies_unambiguous_tokens` -- unit coverage for the new tagger (drive, mail, sharepoint, calendar, task domains).
- `test_get_tool_domain_tags_returns_empty_for_ambiguous_names` -- ensures generic names stay untagged.
- `test_auto_discovery_rejects_cross_domain_same_server_candidate` -- exact shape from the v0.20260416.2 Dev #1 Excel report; `list-mail-folders` and `search-sharepoint-sites` must be rejected and `list-drives` must win when repairing `get-drive-root-item`.
- `test_auto_discovery_prefers_same_domain_same_server_candidate` -- calendar repair prefers `list-calendar-events` over `list-mail-folders`.

### Validation

- Full unit suite: **483 passed, 27 skipped**.
- Targeted repair-tool tests: 74/74 pass.
- Random e2e (5/5 pass): `14_user_synopsis/test_14a1_synopsis_enabled`, `19_api/test_19p1_scheduler_admin`, `4_mcp/test_4a2_system_info_mcp`, `4_mcp/test_4d3_clarification`, `5_artifacts/test_5_9`.
- ruff, black, mypy: clean.

## v0.20260416.3

### Bug Fixes

- **LLM-emitted sentinel values no longer block MCP server-default injection (CRITICAL, Dev #1 Excel, BUG-4 context)** -- When the planner encountered a required parameter that a same-server MCP default would provide (e.g. `driveId` on `get-drive-root-item`), it often emitted a literal sentinel string like `"driveId": "auto-injected"`. The v0.20260416.1 parameter-preservation fix treated that sentinel as a resolved value, so the real server default was never merged in. MCP then rejected the call with `driveId=auto-injected`. Fix: added `_is_sentinel_placeholder_value()` that matches LLM-invented sentinels (`auto-injected`, `from_server`, `from_context`, `server_default`, `<to-be-injected>`, etc.) and the parameter candidate / unresolved-parameter pipelines now treat these values as unresolved so server defaults, context, and inference can overwrite them.
- **Dotted placeholder references like `{{SPARK_EVENT.event_id}}` now resolve correctly (CRITICAL, BUG-3)** -- `_substitute_step_parameter_placeholders` used the full `{{FOO.field}}` string as a `my_results` lookup key, but the dict is keyed on the bare `{{FOO}}` placeholder. Lookup always missed and the literal `{{FOO.field}}` string was passed through to MCP. Fix: added `_parse_placeholder_reference()` that strips the `.field` suffix for lookup and records the suffix as a field hint; `_extract_field_from_result_payload()` then walks the referenced step's records (case-insensitive, ignoring underscores/dashes) to find the requested field.
- **Whole-payload fallback no longer returns the entire result dict for unknown params (CRITICAL, BUG-4 root cause)** -- The final branch of `_resolve_parameter_from_result_payload` previously returned the entire payload whenever a field-level match failed. For LLM-hallucinated parameters that weren't in the tool schema (e.g. `user_google_email` on `manage_event`), this sent the whole result dict to MCP and produced pydantic validation errors. Fix: the fallback now only applies when the parameter has a known schema **and** the payload is a scalar; it never returns a dict or a list for a hallucinated or schema-less parameter.
- **Scheduler now marks job success when no webhook is configured** -- `_execute_single_job` unconditionally called `overlord.chat(use_async=True, webhook_url=webhook_url)` and relied on `complete_job_from_webhook` to update counters. When the formation had no `async.webhook_url`, the webhook never fired: jobs ran successfully (LLM replied, memory updated) but `total_runs` stayed 0 and `last_run_status` stayed empty. Fix: when `webhook_url` is absent, the scheduler runs the chat synchronously and calls `mark_job_execution_success` (and `complete_onetime_job` for one-time jobs) directly after the await returns.

### Tests

- `test_is_sentinel_placeholder_value_matches_llm_invented_tokens` -- coverage for the new sentinel matcher (auto-injected, from_server, from_context, etc.).
- `test_merge_parameter_candidates_overrides_sentinel_placeholder_values` -- ensures real values beat sentinels during merge.
- `test_get_unresolved_required_parameters_flags_sentinel_placeholder_values` -- ensures sentinels count as unresolved so server-default injection runs.
- `test_substitute_step_parameter_placeholders_strips_dot_field_suffix` -- exact bug shape from BUG-3 (`{{SPARK_EVENT.event_id}}` must resolve to the event's id).
- `test_parse_placeholder_reference_splits_dotted_forms` -- unit coverage for the dotted reference parser.
- `test_resolve_parameter_from_result_payload_does_not_return_whole_payload` -- regression for BUG-4 (`user_google_email` on `manage_event` with empty schema must resolve to `None`, not the whole result dict).
- `test_resolve_parameter_from_result_payload_still_returns_scalar_for_scalar_schema` -- sanity check that legitimate scalar resolution still works.
- 3 source-level verification tests in `TestSchedulerMarksSuccessWhenNoWebhook` confirming the synchronous no-webhook completion path.

### Validation

- Full unit suite: **479 passed, 27 skipped**.
- Targeted fix tests: 85/85 pass.
- Random e2e (5/5 pass): `19_api/test_19w1_logs_stream`, `3_multimodal/test_3d3`, `3_multimodal/test_3f1`, `5_artifacts/test_5_13_rce_error_paths`, `9_async/test_9c1_webhook_failure`.
- ruff, black: clean.
- mypy: 4 pre-existing errors in `scheduler/service.py` (unrelated to this release).

### Known issues deferred to next release

- **Repair-tool domain mismatch** -- auto-discovery still picks `list-mail-folders` / `search-sharepoint-sites` when `get-drive-root-item` fails because there's no keyword-domain scoring pass; Fix 1 in this release removes the trigger for the most common case (`auto-injected` driveId) so the repair path is rarely reached now.
- **CLI-side timestamp parsing** -- scheduler list output crashes on microsecond timestamps (CLI issue, not runtime).
- **Scheduled-job response delivery** -- no mechanism exists to deliver scheduler output back to the user without a webhook; synchronous completion (Fix 4) just keeps DB state correct.

## v0.20260416.1

### Bug Fixes

- **Planning mode no longer strips tool parameters (CRITICAL)** -- `_finalize_execution_plan` was rebuilding `my_steps` from the unified `steps` list, but the planning prompt template only instructs the LLM to emit `parameters` in its separate `my_steps` block. The rebuild silently replaced every parameter set with `{}`, so `manage_event` was called with only `{"action": "create"}` and `get_events` with `{}` -- missing all required fields. Fix: `_finalize_execution_plan` now preserves parameters from the LLM's original `my_steps` by matching on `tool_name`, using a FIFO queue so repeated tool uses keep their own params.
- **Planner can now resolve relative date references like "today" and "tomorrow"** -- `_plan_before_execution` used `self.system_message` (the static formation-config attribute) and never saw the current-date injection that `process_message` applies to the live conversation system message. The planner therefore had no way to turn "tomorrow" into an RFC3339 date and emitted literal strings like `"time_min": "tomorrow at 00:00:00"`. Fix: the planning prompt now includes a `## Current date/time:` section with the current local date, time, and timezone, plus an explicit instruction to resolve relative references into concrete dates.

### Tests

- `test_finalize_execution_plan_preserves_parameters_from_llm_my_steps` -- exact shape from the bug report (`steps` without params, `my_steps` with full param set).
- `test_finalize_execution_plan_preserves_parameters_across_repeated_tool_use` -- two `manage_event` calls in the same plan, ensuring params are matched positionally per tool.
- `test_plan_before_execution_injects_current_date_into_planning_prompt` -- verifies the planning prompt carries a `## Current date/time:` block before the LLM call.

### Validation

- Full unit suite: **469 passed, 27 skipped**.
- ruff, black, mypy: clean.

## v0.20260416.0

### Bug Fixes

- **Parameter-free planned MCP steps no longer crash with UnboundLocalError** -- `server_default_param_names` was initialized inside the `if required_params:` branch but referenced unconditionally by validation and tool dispatch. Tools like `list-mail-messages`, `get_events`, and `search_gmail_messages` that require no user-supplied parameters crashed before reaching the MCP server. Fix: hoisted the variable initialization above the conditional gate.
- **Scheduler job execution no longer crashes with "Future attached to a different loop"** -- The scheduler worker thread created its own event loop, but `overlord.chat()` and its downstream I/O (asyncpg, httpx, MCP transports) are bound to the main uvicorn loop. Fix: `start()` now captures the main loop, and `_execute_due_jobs()` dispatches via `asyncio.run_coroutine_threadsafe()` so job execution runs where the formation's async resources live.
- **Repair-tool selection no longer picks tools from unrelated MCP servers** -- The auto-discovery fallback in `_build_auto_discovery_repair_plan` scored candidates purely on verb/keyword heuristics with no server affinity. A `todo-helper-mcp__get-default-list-id` could outscore same-server mail tools when repairing a failed `ms365-mcp__list-mail-messages`. Fix: added server affinity scoring (+4 same-server, -3 cross-server).
- **Fixed legacy table name in e2e test `test_2k1_enhanced_prompt_integration`** -- Memory verification query referenced bare `memories` table instead of `memories_1536`, causing the test to fail on all dimension-aware databases.

### Tests

- Regression test exercising `process_message()` with a planned MCP step using `parameters: {}` (the exact crash path).
- Regression test verifying cross-server tool (`todo-helper-mcp`) is rejected when a same-server candidate (`ms365-mcp`) is available during repair planning.
- 3 source-level verification tests confirming scheduler dispatches job execution to the main event loop.

### Validation

- Full affected unit suite: **72 passed**.
- Scheduler e2e test (`test_12a4_verify_execution`): passed.
- 5 random e2e regression tests: 4/5 passed (1 pre-existing DB schema issue unrelated to this release).

## v0.20260415.0

### Runtime Fixes

- **MCP default-backed required parameters no longer trigger fallback inference** -- Planning/execution now treats required params supplied by MCP server defaults as satisfiable, so runtime-injected values like `driveId` are not redundantly inferred and accidentally replaced with guessed values such as `"me"`.
- **Named-resource hint extraction is now more general without service-specific heuristics** -- Context hint extraction now recognizes user-supplied resource references like `#social`, `@name`, quoted names, and filenames, allowing semantic record disambiguation without introducing Slack- or app-specific runtime rules.
- **Delegated analysis prompts now carry prior tool results** -- When delegation is still necessary, the runtime appends compact summaries of successful prior tool results so downstream agents do not reason without the data already gathered and fabricate answers from missing context.
- **Planning guidance now discourages delegating pure reasoning over locally retrieved data** -- Agents are instructed to keep arithmetic, summarization, and analysis with the current agent when its own tools can already fetch the needed data, reducing unnecessary A2A handoffs like Excel aggregation falling into the generic assistant.

### Dependency Updates

- **Raised `onellm[cache]` minimum version to `>=0.20260415.0`** -- Pulls in the latest OneLLM fixes required by current runtime work without changing the dependency shape.
- **Kept `faissx` minimum version at `>=0.20260403.0`** -- Confirmed the current floor already matches the requested minimum, so no additional package change was needed.
- **Aligned direct dependency floors with recently merged Dependabot PRs** -- Raised the minimum versions for dependencies that already had merged update PRs and are declared directly in `pyproject.toml`: `fastmcp>=3.2.0`, `pypdf>=6.10.0`, `Pillow>=12.2.0`, `aiohttp>=3.13.4`, `requests>=2.33.0`, `cryptography>=46.0.7`, `pytest>=9.0.3`, and `black>=26.3.1`.

### Notes

- Only direct dependencies declared in `pyproject.toml` were raised. CI-only GitHub Actions bumps and transitive-only lockfile bumps were intentionally left out.
- Prepared as an unreleased entry so additional fixes from today can be appended before the next push/tag.

## 0.20260414.0 - Result Recency Bias, Snake_case Normalization & Preventive Hardening

### Bug Fixes

- **Alias extraction copied `driveItemId` into `workbookWorksheetId` instead of the worksheet GUID** -- When multiple prior steps' results all contain records with an `id` field, the alias extraction iterated results in chronological order and returned the first match. In the 4-step Excel chain, the `list-folder-files` result (step 2) appeared before `list-excel-worksheets` (step 3), so the file's `driveItemId` was extracted instead of the worksheet GUID. Fix: reversed result iteration order so the most recent step's records are searched first, and relaxed the alias resolution guard to return the first (most-recent) match when multiple alias values exist.
- **Snake_case parameter names (`channel_id`, `drive_id`) were not matched by the alias suffix list** -- The Slack MCP uses `channel_id` (snake_case), but the suffix list only matched `channelid` (camelCase lowered). The underscore prevented suffix matching, so `channel_id` was never bound from `slack_list_channels` results. Fix: normalize parameter names by stripping underscores before suffix matching (both in alias extraction, kind inference, and driveId fallback).

### Preventive Hardening

- **Exact-key matching in `_resolve_parameter_from_records` now normalizes underscores** -- When a record has `channel_id` as a literal key and the required param is `channelId` (or vice versa), the exact-match phase now strips underscores before comparing. Previously only the alias path was normalized, so the exact-match short-circuit was missed for cross-casing keys.
- **`_extract_explicit_parameter_values_from_text` now matches both camelCase and snake_case forms** -- When context text contains `channel_id = C08SZKB16UF` but the schema param is `channelId`, the regex now tries both forms. Previously only the literal param name was searched, so cross-casing context lines were invisible.
- **`_record_matches_context_hints` now checks snake_case field variants** -- Added `display_name`, `file_name`, `web_url`, `channel_name`, and `topic` to the candidate fields list. MCP servers using snake_case conventions (Slack, Jira, etc.) could have records that matched context hints but were missed because only camelCase fields were checked.
- **`_compact_planning_record` preferred_keys expanded for snake_case MCPs** -- Added snake_case variants (`display_name`, `drive_id`, `drive_item_id`, `parent_reference`, `web_url`, `site_id`, `channel_id`, `channel_name`, `created_at`, `updated_at`) plus commonly useful fields (`position`, `visibility`, `type`, `status`, `description`, `topic`). Records from snake_case MCPs were being stripped to empty dicts during compaction, losing data needed by downstream steps.

### Tests

- **Most-recent-step preference** -- Test confirming that when both a file record (step 2) and a worksheet record (step 3) have `id` fields, the worksheet GUID from the more recent step is extracted for `workbookWorksheetId`.
- **Snake_case alias matching** -- Test confirming `channel_id` (snake_case) extracts the channel ID from a Slack channel record.
- **Exact-key normalization** -- 3 tests: `channel_id` record key matches `channelId` param, `channelId` record key matches `channel_id` param, `drive_item_id` record key matches `driveItemId` param.
- **Explicit text cross-casing** -- 2 tests: `channel_id = X` in text resolves `channelId` param, and `channelId = X` in text resolves `channel_id` param.
- **Context hints snake_case fields** -- 2 tests: records with `display_name` and `channel_name` fields are matched by context hints.
- **Compact record preservation** -- Test confirming snake_case keys (`display_name`, `channel_id`, `channel_name`, `position`, `visibility`, `type`, `status`, `description`) are retained while unknown keys are dropped.
- **Full snake_case MCP resolution** -- Integration test feeding a Slack `channels` result with snake_case keys and verifying `channel_id` is correctly bound.

### Validation

- Full unit suite: **456 passed**, 27 skipped.
- mypy/Black clean.
- 5 random e2e regression tests passed (API streaming, foundation loading, artifacts, knowledge isolation, orchestration SOP).

## 0.20260413.1 - Worksheet & Entity ID Binding from Prior Tool Results

### Bug Fixes

- **`workbookWorksheetId` and other entity GUIDs could not be extracted from prior tool results** -- The alias extraction helper that maps a record's `id` field to downstream parameters only recognized 9 entity suffixes (`itemid`, `fileid`, `folderid`, etc). Parameters ending in `worksheetid`, `channelid`, `planid`, `teamid`, and other common MS365 Graph entity patterns were not covered. This caused the 4-step Excel read chain (get-drive-root-item, list-folder-files, list-excel-worksheets, get-excel-range) to succeed through step 3 but fail at step 4 because `workbookWorksheetId` was never bound. Fix: added `worksheetid`, `sheetid`, `notebookid`, `sectionid`, `pageid`, `channelid`, `teamid`, `planid`, `listid`, `eventid`, and `contactid` to the alias suffix list.
- **Real GUIDs in braces were rejected as unresolved placeholders** -- The placeholder detection pattern `^\{[A-Z0-9...]*\}$` matched real worksheet GUIDs like `{4C35B2DD-58DF-4BDB-B806-E0421A3D5456}` because they are uppercase hex in braces. The value was discarded by `_is_nonempty_parameter_candidate`, preventing it from being used as a resolved parameter even after correct extraction. Fix: added an early exemption for GUID-format strings (`{8-4-4-4-12}` hex pattern) before the placeholder patterns are checked.
- **JSON string values in the `result` field were not parsed for record extraction** -- When a tool result arrived as `{"result": "{\"value\": [...]}", "status": "success"}`, the extraction function returned the raw JSON string without parsing. `_iter_result_records` cannot iterate strings, so zero records were found and no identifiers were extracted for downstream steps. This is the same class of bug fixed in v0.20260410.0 for the `content` field (modern MCP protocol), now also fixed for the `result` field path. Fix: added `_parse_json_like_text()` call for string-typed `result` values.

### Tests

- **Entity ID alias extraction coverage** -- Added tests for `workbookWorksheetId`, `planId`, and `channelId` alias extraction from records, plus a full `_resolve_parameters_from_context` integration test that feeds a `list-excel-worksheets` JSON string result and verifies `workbookWorksheetId` is bound correctly.
- **GUID placeholder exemption coverage** -- Added tests verifying real GUIDs in braces are not treated as placeholders, planning placeholder patterns are still detected, and `_is_nonempty_parameter_candidate` accepts GUIDs but rejects placeholders.
- **Result-field string parsing coverage** -- Added tests for `_extract_structured_planning_result_payload` handling JSON object strings, JSON array strings, and plain text strings in the `result` field.
- **Validation sweep** -- Full unit suite passed (`445 passed, 27 skipped`). 10 random e2e regression tests passed across triggers, multi-identity, API, skills, memory, multimodal, orchestration, and clarification.

## 0.20260413.0 - Planning JSON Robustness & Truncation Fix

### Bug Fixes

- **Planning JSON parser failed when the LLM returned prose before the JSON block** -- Some models (notably `claude-sonnet-4-20250514`) emit a natural-language preamble before the JSON execution plan, sometimes wrapped in a markdown code fence that does not start at character 0. The parser only handled the case where the response began with `` ``` ``, so the full prose+JSON string was passed to `json.loads()`, which failed at char 0. The entire planning phase was abandoned and the request fell through to A2A delegation, where an agent without the right tools fabricated responses from training data. Fix: planning JSON extraction now uses a three-stage approach -- direct parse, regex extraction of code-fenced JSON anywhere in the response, then brace-matched search for the outermost `{...}` containing `"steps"`.
- **Multi-step plans were silently truncated on formations with many tools** -- The planning LLM call did not set `max_tokens`, inheriting the Anthropic API default (4096). Formations with 100+ MCP tools produce planning prompts where a 4-step plan (e.g., get-drive-root-item, list-folder-files, list-excel-worksheets, get-excel-range) exceeds that cap. The model stopped generating mid-JSON, producing an unterminated string error at ~3000 characters. The agent fell back to delegation, which could not fulfill the request. Fix: the planning call now sets `max_tokens=16384` explicitly, which is the maximum output supported by current Anthropic models and 4-5x larger than any realistic multi-step plan.

### Tests

- **Planning JSON extraction coverage** -- Added 3 tests to `tests/unit/test_agent_planning_helpers.py` covering: prose preamble with code-fenced JSON, bare JSON preceded by prose text, and verification that `max_tokens=16384` is passed to the planning LLM call.
- **Validation sweep** -- Full unit suite passed (`435 passed, 27 skipped`) along with Black and mypy checks on touched files.

## 0.20260410.0 - MCP Default Parameters, Deterministic Planned-Step Binding & Result Extraction

### New Features

- **MCP server `parameters` field for infrastructure constants** -- MCP server declarations (formation-level and agent-level) now support a `parameters` field: a flat dictionary of default tool arguments that the runtime auto-injects into every tool call for that server. This removes the need for the LLM planner to discover or infer fixed org-level values like `driveId`, `siteId`, or `tenantId`. Parameters support `${{ user.credentials.X }}` placeholder resolution at call time and are validated as flat dicts with scalar values. Tool-call-supplied arguments take precedence over defaults.

### Bug Fixes

- **Planned tool execution could bind required parameters from polluted enhanced prompts instead of the current request** -- Planning already used the extracted current request plus explicit `[Context: ...]` lines, but execution-time parameter resolution still scanned the broader enhanced prompt and could pick up stale values from memory/profile/conversation sections. Fix: planned-step execution now resolves parameters from the clean current request/context, successful prior results, and active runtime skill context instead of the full enhanced prompt blob.
- **Placeholder values could still leak into local planned tool calls** -- Local `my_steps` did not have a deterministic placeholder substitution pass, and strings like `{{ROOT_FOLDER_ID}}` or `<<ID>>` could still be treated as resolved required values. Fix: placeholder-shaped values are now considered unresolved, local planned steps substitute placeholder params from prior successful results before execution, and unresolved placeholders block tool calls safely.
- **Failed prior steps could contaminate downstream parameter reuse and inference** -- Parameter extraction and compact inference context considered all prior results, including handled error payloads. Fix: only successful prior tool/skill results are now eligible for placeholder substitution, structured record extraction, and inference context construction.
- **LLM could fabricate ID-typed parameters not found in any prior result** -- When inferring parameters for multi-step tool chains, the LLM could hallucinate plausible-looking IDs (e.g., a driveItemId) that did not appear in any successful prior result. These fabricated IDs would reach the MCP server and produce confusing errors. Fix: added `_validate_inferred_parameters_against_results()` which checks LLM-inferred ID-typed params against successful result records using `_record_matches_expected_kind()` and rejects values not found in discovered records.
- **Structured MCP result extraction failed for modern protocol string content** -- `ModernProtocolFeatures.process_structured_output()` flattens content blocks into a single JSON string, but `_extract_structured_planning_result_payload()` only handled `list`-typed content. String content was wrapped in a dict with no useful records, preventing downstream steps from extracting identifiers like `driveItemId` from prior successful tool calls. Fix: when content is a string, attempt `json.loads()` before returning so JSON payloads from modern MCP protocol are properly parsed for record extraction.
- **Agent-level MCP registration did not pass `parameters` to service** -- The overlord's `_register_agent_mcp_servers()` path did not forward the `parameters` kwarg, so MCP servers declared at agent level (common in formations like Spark) had empty defaults despite being configured. Fix: added parameters pass-through in both the formation-level and agent-level registration paths.
- **Activated skills could guide planning but not contribute machine-usable runtime context** -- Skill activation only appended prompt instructions, so formations had no generic way to register runtime-only structured facts for later tool execution. Fix: skills now support `execution_context` in frontmatter, the runtime resolves secret-backed values without injecting them into the prompt body, and active skill execution context is stored per `(agent_id, session_id)` for deterministic parameter binding.
- **`run_skill` results were not first-class structured inputs for later planned steps** -- Skill execution returned stdout text only, forcing downstream chaining to rely on prompt reconstruction. Fix: when skill stdout is valid JSON, `run_skill` now exposes it as `structuredContent`, and planning/execution result extraction consumes that structured payload like any other successful tool result.

### Tests

- **MCP default parameters unit coverage** -- Added `tests/unit/test_mcp_default_parameters.py` with 10 tests covering: parameter injection during tool invocation, tool-call args taking precedence over defaults, `${{ user.credentials.X }}` placeholder resolution, validation of flat/scalar-only dicts, and formation/agent-level registration pass-through.
- **Post-inference validation coverage** -- Extended `tests/unit/test_agent_planning_helpers.py` with tests for ID-typed parameter validation against successful result records, rejection of fabricated IDs, and pass-through of IDs that match discovered records.
- **Expanded planned-step and skills regression coverage** -- Extended `tests/unit/test_agent_planning_helpers.py`, `tests/unit/skills/test_skills.py`, and `tests/unit/skills/test_skill_secrets.py`, and added `tests/unit/skills/test_skill_dispatch.py` to cover clean execution binding, placeholder rejection/substitution, failed-result exclusion, runtime skill execution context, and structured `run_skill` stdout chaining.
- **Validation sweep** -- Full unit suite passed (`432 passed, 27 skipped`) along with focused mypy, Ruff, and Black checks on all touched files.
- **Live formation validation** -- End-to-end tested against Spark Enterprise formation (MS365 + Sonnet 4.5 and Opus 4) confirming: `driveId` injected from MCP defaults, `driveItemId` extracted from prior step results, full 3-step tool chain executes deterministically, honest failure when target file not found. Both models produce identical behavior.

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
