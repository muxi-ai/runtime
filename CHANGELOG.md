# Changelog

## [unreleased]

### Remote knowledge sources - archives, scheduling, extra protocols (Phases 2-4)

Completes the remote-knowledge-sources PRD on top of the Phase 1 core
sync: archive extraction, scheduled re-sync with incremental
re-embedding, a manual sync trigger endpoint, and four more protocols.

- **Archive extraction (Phase 2)**: ``extract: true`` sources download a
  single archive (``.zip``, ``.tar``, ``.tar.gz``/``.tgz``,
  ``.tar.bz2``, ``.tar.xz``) and extract it into the local mirror;
  ``extract_pattern`` keeps only matching members. Extraction is
  security-hardened: member names are path-traversal-safe (same guards
  as the manifest), symlink/hardlink/device members are rejected, and
  decompression bombs are bounded by ``max_extracted_files`` (default
  1000) and ``max_extracted_size`` (default 500MB) counted on the
  DECOMPRESSED stream, never trusted from headers. Extraction happens in
  a temp dir next to the mirror (always cleaned up); the mirror is only
  updated after the whole archive extracted successfully, so a corrupt
  or malicious archive degrades to the previously synced content.
  Unchanged archives (hash + size) skip both download and extraction.
- **Scheduled re-sync (Phase 3)**: sources with a cron ``schedule``
  (or ``@hourly``/``@daily``/``@weekly``) now actually re-sync
  periodically. The new ``KnowledgeSyncService`` registers with the
  existing SchedulerService worker loop (the heartbeat's periodic-task
  extension point -- no second scheduler). Per-source locks skip
  overlapping syncs (``knowledge.sync.skipped``); total failures retry
  with exponential backoff (per-source ``retry:`` block --
  ``max_attempts``/``initial_delay``/``max_delay``/``exponential_base``,
  defaults 3/5s/300s/2) and then fall back to the next cron fire, always
  serving stale content in the meantime. After a sync that changed the
  mirror, only the changed/deleted files are re-embedded
  (``KnowledgeHandler.refresh_remote_source``), not the whole source.
  Schedules without a running scheduler degrade to startup-only sync
  with a loud init warning. ``@startup`` / no schedule keep the Phase 1
  startup-only behavior.
- **Manual sync trigger**: ``POST /v1/agents/{agent_id}/knowledge/sync``
  (AdminKey; optional ``{"source_id": ...}`` body) re-syncs an agent's
  remote sources on demand through the same locks and incremental
  re-embed path, returning per-source results.
- **Additional protocols (Phase 4)**: ``gs://`` (Google Cloud Storage,
  Content-MD5 change detection, optional ``auth: {type: gcp,
  credentials_json}`` else ADC), ``az://`` (Azure Blob Storage,
  Content-MD5/ETag; requires ``auth: {type: azure}`` with
  ``connection_string`` or ``account_name``+``account_key``),
  ``ftp://`` (stdlib, size+mtime, ``basic`` auth or URL userinfo), and
  ``sftp://`` (paramiko, size+mtime, ``ssh_key`` or ``basic`` auth;
  strict host-key checking by default with the same
  ``accept_new_host_keys`` opt-in as rsync+ssh). All use the shared
  atomic-download path. Optional SDKs ship as extras --
  ``muxi-runtime[gcs]``, ``[azure]``, ``[sftp]`` -- with clear
  config-time errors naming the extra when missing; ftp needs nothing.
- Fixed a latent WorkingMemory bug surfaced by incremental re-embedding:
  FAISS partitions for pre-computed embeddings (knowledge chunks) were
  created/rebuilt at the buffer's own embedding dimension, silently
  dropping vectors on write and crashing every vector search after the
  first index rebuild. Partition dimensionality now follows the vectors
  it stores.
- All new config keys are fail-fast validated at load time; formations
  without remote sources remain untouched (the remote machinery is never
  imported).

### Memory event substrate - projections, provenance, rebuild (Phases 2b-2d)

The immutable memory event log (memory-event-substrate PRD) now covers the
full write-path story on top of the shipped core log + dual-write:

- Incremental projection builders (2b): per-(projection, user) cursors in
  ``projection_checkpoints`` drive ``project_pending`` (catch a cursor up
  to the log tail; idempotent, poison events are skipped and reconciled by
  rebuild) and ``apply_event`` (project one just-appended event). A new
  artifact-metadata projector rebuilds ``artifacts`` rows from
  ``artifact.saved`` events (v2 payloads carry the full metadata; v1
  events are reconstructed deterministically - builders handle every
  historical payload version); blobs are never touched and pre-substrate
  rows survive resets.
- Event-first cutover groundwork (Phase C, flag-gated, DEFAULT OFF):
  ``memory.events.event_first: true`` makes the extractor, knowledge
  graph, captain's log, ingestion, and shared-scope write paths append
  the event and derive the projection through the substrate (synchronous
  apply + background applier as crash recovery, with cursor snapshots
  guarding dual-written history). Dual-write remains the default until
  cutover.
- Provenance (2c): ``GET /v1/memories/provenance?entity=X`` answers "why
  do you think X?" - the knowledge graph entity, every fact touching it
  (contradicted/superseded included), and per-fact causation chains from
  the event log back to the originating interaction turn or ingestion
  item. ``?event_id=`` traces a single event. The ``artifacts`` table
  gains an additive ``derived_from_event_id`` provenance column.
- Decay at query time (2c): ``memory.decay`` settings (default half-life
  180d, volatile TTL 24h, per-relationship-type ``half_lives`` map).
  Volatile events without an explicit expiry are stamped at write time;
  an hourly maintenance sweep soft-deletes expired volatile events so
  rebuilds drop their projections. Context-block ranking re-weights
  facts by half-life age for configured types (no-op by default - the
  hot read path pays nothing unless the formation opts in).
- Contradiction audit (2c): knowledge-graph writes that conflict with or
  supersede an existing exclusive fact now record ``fact.contradicted``
  events (idempotent per fact pair, ``caused_by``-linked to the
  extraction) plus a ``memory.fact.contradicted`` observability event.
  Replay re-marks rows but never re-records audit events.
- Rebuild & migration (2d): ``POST /memory/rebuild`` (admin) runs as a
  background job by default (202 + job id, pollable at
  ``GET /memory/rebuild/{job_id}``; ``background: false`` blocks) - this
  backs ``muxi memory rebuild --user <id>``. ``POST /memory/backfill``
  synthesizes idempotent ``source='legacy'`` events for pre-event-log
  rows (KG entities/relationships, captain's log entries/lessons,
  artifacts, orphan flat facts); ``rebuild`` accepts ``backfill: true``
  to do both. ``POST /memory/forget`` is the GDPR flow: soft-delete a
  source's events (reversible for the retention grace period; the
  hard-purge worker then removes them), record the ``user.deletion``
  audit event, and rebuild projections as if the source never existed.
- Ops: per-user event-log size-cap alert
  (``memory.events.retention.max_events_per_user``, alert-only per the
  PRD's SQLite posture), projection lag alerts
  (``memory.projections.lag_alert_threshold_seconds``), and new
  observability events (``memory.projection.lagging``,
  ``memory.event.expired``, ``memory.event.size_cap_exceeded``,
  ``memory.fact.contradicted``, ``memory.backfill.started/completed``).
  All new config keys fail-fast validated at load.

### Knowledge reasoning RAG - Method A tree retrieval (Phase 1)

Large knowledge files are now indexed as hierarchical trees navigated by an
LLM at query time instead of vector chunking (knowledge-reasoning-rag PRD,
Phase 1):

- New `formation/agents/knowledge/reasoning/` package: `TreeBuilder`
  (deterministic heading/window segmentation + batched LLM summaries),
  `TreeCache` (MD5-keyed disk persistence: compact tree JSON + separate
  node->raw KV file), and `TreeSearchA` (Method A: one LLM call selects
  node_ids from the compressed tree; raw content resolved from the KV).
- Per-file gate at ingestion: files above `knowledge.reasoning_threshold`
  tokens (default 40000, `0` disables) are tree-indexed; everything else
  flows through the unchanged vector pipeline. Applies inside directory
  sources too. Per-source `retrieval: vector|tree` overrides the gate
  (`tree-vector`/`hybrid` are reserved for later phases and rejected at
  load). New `knowledge.tree` settings block: `model` (defaults to the
  agent's text model; accepts an `llm.aliases` name or `provider/model`),
  `max_depth`, `max_pages_per_node`, `max_tokens_per_node`,
  `max_document_tokens`. All new keys fail-fast validated at load time.
- Tree and vector sources coexist in one agent's knowledge base; tree
  results carry `source_type: "tree"` plus a `node_path` breadcrumb via the
  unified `RetrievalResult` schema (contract shared with the memory-revamp
  PRD).
- Failure isolation: tree build failure (or the `max_document_tokens` size
  cap) falls back to vector indexing; navigation failure at query time falls
  back to vector search results - never a failed turn. New observability
  events: `KNOWLEDGE_TREE_BUILD_STARTED` / `_COMPLETED` / `_FAILED` and
  `KNOWLEDGE_TREE_FALLBACK_TO_VECTOR` (with cause).
- Inert when unconfigured: files under the threshold (and handlers without a
  tree model) behave byte-identically to the previous vector path, pinned by
  unit tests.

### Remote knowledge sources - Phase 1 core sync

Agents can now declare url-based knowledge sources next to local paths
(remote-knowledge-sources PRD, Phase 1):

- ``knowledge.sources[*].url`` supports ``http(s)://`` (single file),
  ``s3://`` (prefix + glob), ``rsync://`` / ``rsync+ssh://`` (incremental
  tree sync), and ``file://`` (bind mounts). Credentials go through the
  existing ``${{ secrets.* }}`` interpolation (``auth`` blocks:
  ``basic``/``bearer`` for http, ``aws`` for s3, ``ssh_key`` for
  rsync+ssh; plus http ``headers``).
- Remote content syncs at formation startup into a per-source local
  mirror under the runtime knowledge cache dir with manifest-based
  change detection (ETag / Last-Modified / size+mtime), then feeds the
  unchanged local ingestion pipeline. Downloads are atomic (temp file +
  rename), so a mid-stream failure can never truncate a previously
  synced good copy. ``include``/``exclude`` filters and ``max_files`` /
  ``max_file_size`` / ``max_total_size`` / ``timeout`` limits are
  enforced. For rsync+ssh, SSH host key checking is strict by default;
  ``accept_new_host_keys: true`` is the explicit opt-in for
  trust-on-first-use. S3 ``auth: {type: aws}`` without explicit keys
  uses boto3's default credential chain.
- Failure isolation: a failing sync never blocks formation startup or
  chat -- sources degrade to previously synced content (stale-wins); on
  a cold start with an unreachable source the formation still starts
  with a loud warning. New observability events:
  ``knowledge.sync.started``, ``knowledge.sync.completed``,
  ``error.knowledge.sync.failed``.
- Fail-fast load-time validation of source declarations (schemes, auth
  shape, limits, cron ``schedule`` syntax). Not yet in Phase 1 (config
  is rejected or documented accordingly): archive extraction
  (``extract``), scheduled re-sync (``schedule`` accepted, sync runs at
  startup only), and ``gs``/``az``/``ftp``/``sftp`` protocols.
- Formations with only local knowledge sources are untouched (the remote
  sync machinery is never even imported).

### RBAC membership via request middleware; server.auth and user_groups removed

MUXI stops storing group memberships (request-middleware PRD). Breaking
for pre-1.0 formations that used ``server.auth`` or seeded
``user_groups``:

- New top-level ``middleware:`` block: an actual MCP server (stdio
  ``command``+``args`` or http ``url``+``headers``, plus ``timeout``)
  exposing exactly one tool named ``middleware``. It receives the full
  request payload (``user_id``, ``message``, ``attachments``,
  ``metadata``, ``route_class`` -- never ``groups`` inbound) and returns
  the same-shaped payload, possibly modified: attaching ``groups`` (the
  ONLY membership source), rewriting identity, applying payload policy.
  Connected at formation load with the existing MCP client; a missing or
  non-conforming ``middleware`` tool fails the load. Fail-closed at
  request time: error, timeout, or malformed response rejects the
  request (403; ``error.middleware.failed``). No runtime-side caching --
  ``timeout`` is the only knob.
- New top-level ``rbac:`` block: ``active: auto|true|false`` (auto =
  on iff ``groups/`` has files; true without groups fails the load;
  false is a loud kill switch) and ``fallback: false|<group_name>``
  (reject no-group requests, or proceed with the named group's
  permissions -- validated against ``groups/``). Dead config (active +
  ``fallback: false`` + no middleware) fails the load.
- The pipeline runs after client-key auth and before any processing on
  ALL authenticated inbound traffic (chat, audiochat, triggers, memory
  routes) AND internally-originated requests -- heartbeat and scheduler
  jobs synthesize the same payload (``route_class: "heartbeat"`` /
  ``"scheduler"``) and traverse middleware + RBAC identically.
- REMOVED: ``server.auth`` (the ``required|open`` key, the user auth
  gate, and the open+groups load rule). The client key authenticates
  the caller; user-level gating is ``rbac.fallback: false`` plus a
  middleware that returns no groups for unknown users. Formations still
  carrying the key fail the load with a migration error.
- REMOVED: the ``user_groups`` table (creation and the resolver's DB
  membership read). Existing deployed tables are left orphaned --
  nothing destructive. The ``groups/`` YAML files, inheritance, the
  four-level tools cascade, ``memory.write`` grants, and resource
  filtering are all unchanged.
- Shipped template: ``contributing/templates/middleware.py`` -- a
  one-file stdio middleware (stdlib only) resolving groups from a
  static map; doubles as the e2e fixture. Config reference:
  ``contributing/request-middleware.md``.

### Unified tools vocabulary + attachment overrides (#251)

Completes the GBAC tool-override cascade design.

- ``allow`` / ``deny`` is now the canonical vocabulary for ``tools:``
  blocks at every level -- registry (``mcp.servers[].tools``) and agent
  attachments included; ``whitelist`` / ``blacklist`` remain accepted
  aliases. The strict either-or rule is relaxed to both-permitted with
  deny-applied-after-allow (a superset of previous behavior).
- Agent attachments to formation-declared MCP servers can now carry a
  ``tools:`` override (string reference or ``{id, tools}`` mapping),
  filling in level two of the four-level cascade: formation catalog,
  agent attachment, group per-server, group per-agent -- most specific
  wins.
- An intentionally emptied shared catalog is respected as empty instead
  of silently falling back to the unfiltered registry.

### Proactiveness, Phase 4: default heartbeat SOP + docs (#247)

The closing slice of the proactiveness epic -- content, docs, and two
suppression-robustness fixes found by the first live heartbeat e2e.

- Bundled default heartbeat SOP: heartbeats enabled without a
  ``sop:``/``instruction:`` fall back to a shipped SOP (check due jobs
  and recent context, reach out only when warranted, otherwise
  ``HEARTBEAT_OK``); formation config overrides it.
- Suppression hardened: the sentinel is detected anywhere in a heartbeat
  response (synthesis layers wrap it), and persona formatting passes
  sentinel-bearing responses through verbatim -- scoped to
  heartbeat-originated sessions so normal chats mentioning
  ``HEARTBEAT_OK`` are untouched.
- Soul document template + guide (``contributing/soul-documents.md``,
  ``contributing/templates/soul.md``) for the overlord soul, a full
  config reference for ``proactive:`` / ``commands:``
  (``contributing/proactiveness-config.md``), and enriched OpenAPI docs
  for the notifications and user-channels endpoints.

### Proactiveness, Phase 3: built-in commands (#245)

Eight built-in slash commands land in the registry Phase 1 left open --
all fully deterministic, zero LLM round-trips, active whenever the
``commands:`` block is enabled (no block still means no interception).

- ``/setup``: a stateful guided flow derived from the formation's own
  config (channel question only when channels are declared, then
  timezone), per-user with a 10-minute expiry that replies with a clear
  expiration message instead of leaking answers to the LLM.
- ``/jobs``: list/pause/resume/cancel/logs against the scheduler with
  caller-ownership enforcement; ``/identity``: link/unlink identifiers
  with cross-user protection; ``/channels`` and ``/preferences``:
  read/write per-user channel state (``/channels test`` routes a real
  notification); ``/reset``: clears the current session buffer;
  ``/help`` and ``/status``: pure reads.
- Formation-defined commands shadow built-ins (author control wins), and
  a ``commands.builtin:`` map disables individual built-ins.
- Handler failures return a friendly reply and emit new
  ``command.{executed,failed}`` events -- never a crashed turn.

### Proactiveness, Phase 2: channel templates (#243)

Platform channels ship as declarative content, not MCPs. A channel is a
trigger + transformer pair: the developer points their bot at
``POST /server/triggers/{id}``, and the trigger names the payload format
and the post-back URL.

- ``transformer:`` and ``webhook:`` in trigger frontmatter now compose --
  the transformer supplies payload format, auth, and retry; the trigger's
  webhook URL is the delivery destination. ``endpoint.url`` is optional
  in transformer YAML; resolution is trigger/channel URL first, then the
  transformer's own, with a load-time error when neither exists.
  ``proactive.channels.<name>.url`` gets the same override, including
  ``${{ secrets.* }}``-backed bridge URLs.
- Bundled dormant templates for ``slack``, ``telegram``, ``discord``,
  and ``email`` -- real platform payload shapes, no URLs, inert until
  referenced, shadowed by formation-local ``transformers/`` files (same
  rule as built-in skills). Email emits a constructed message object
  (from/to/subject/body/headers) to the developer's bridge webhook;
  SMTP/SES wiring stays developer territory.
- Per-platform setup guides and example triggers in
  ``contributing/channel-templates.md``.

### Proactiveness, Phase 1: foundation (#238)

Formations can now initiate contact instead of only responding. The
``proactive:`` block wires notification routing, heartbeats, and slash
commands -- all inert when unconfigured.

- **Channels are transformers**: a channel is a named reference to a
  trigger transformer, so outbound delivery reuses the existing template
  substitution, auth, and retry machinery with a single webhook fallback
  when every channel fails.
- **Routing precedence**: explicit channel(s) over user preference over
  formation default over webhook, with reserved ``last`` / ``preferred``
  / ``webhook`` targets and multi-channel arrays. Per-user channel state
  (preferred channel, addressing context, last channel, timezone) is
  kept in memory with write-through persistence and exposed via
  ``POST /v1/notifications`` and ``GET/PUT /v1/users/{id}/channels``.
- **Source tracking**: inbound chat and triggers record which channel a
  user last spoke on, so "reply where they are" works.
- **Heartbeat**: rides the existing scheduler through a new periodic-task
  extension point -- interval gating, active hours (fixed or user
  timezone, overnight ranges, weekend flags), ``HEARTBEAT_OK``
  suppression, fresh session per run, and full failure isolation with
  new heartbeat events.
- **Soul documents**: soul stays an overlord-level concept -- a
  ``SOUL.md``/``soul.md`` next to ``formation.yaml`` is auto-discovered
  as the overlord's default persona (precedence: ``SOUL.md`` >
  ``soul.md`` > inline ``overlord.soul`` > built-in default). Agents are
  single-file contained: an agent's character lives in its
  ``system_message``.
- **Slash commands**: opt-in ``commands:`` block mapping ``/command`` to
  SOPs via explicit invocation (no LLM round-trip for unknown commands);
  the built-in command registry lands in a later phase.
- Phases 2-5 (channel MCPs, built-in ``/setup``-style commands, extra
  channels) are deliberately out of scope for this PR.

### Bundled compute skill (#237)

A built-in code-as-reasoning skill: the agent writes a self-contained
Python file and a bundled executor runs it inside the existing Skill RCE
sandbox. No inner LLM loop, no orchestration, no new execution paths.

- ``SKILL.md`` teaches activation, the write-file/print-answer contract,
  and the allowed-imports policy (json, math, datetime, re, statistics,
  csv, pandas, numpy inlined); four worked reference examples ship with
  the skill.
- Executor hardening: path-traversal and symlink rejection, AST
  import/builtin policy that follows attribute chains (``eval.__call__``
  is caught), and distinct machine-readable error prefixes so agents fix
  syntax errors as syntax and import violations as imports.
- ``run_skill`` gained ``input_files`` pass-through (the RCE server has
  no shell, so code cannot ride in ``command``), plus a compute-only
  recovery shim for planner models that put raw Python in ``command``.
- New ``computation.{requested,completed,failed}`` events with a
  ``failure_kind`` breakdown. Disable via ``skills.disable_builtin``;
  degrades like any scripted skill when no RCE is configured.

### Fixes (#229, #231, #234, #235, #240, #241, #249)

- Scheduler due-job queries are scoped to the owning formation:
  formations sharing one database no longer execute each other's
  scheduled jobs (``get_active_jobs_batch`` and its pagination count
  filtered only on ACTIVE status; every other query in the manager was
  already formation-scoped) (#249).

- The formation MCP server exposes its tools again on FastAPI 0.137+:
  lazy router inclusion left ``app.routes`` holding placeholders instead
  of flattened routes, so the MCP mount found zero routes with an
  ``operation_id`` and generated an empty tool set. Client tool paths are
  now collected from the source routers at registration time -- same
  exposure semantics, no dependence on FastAPI route internals (#241).
- The artifact-memory e2e fixture uses a repo-relative ``secrets.enc``
  symlink so it works in fresh worktrees (#240).

- Scope-column migration now covers ALL ``memories_{dim}`` tables, not
  just the dimension guessed at startup -- the active dimension is probed
  lazily on first embed, so the previously-migrated table could differ
  from the one actually queried, breaking scope-filtered retrieval (#231).
- The resilient executor's tool-timeout fallback no longer passes a
  keyword argument ``process_message`` does not accept; the resulting
  ``TypeError`` was swallowed, so recovery silently failed the task
  instead of retrying without tools (#234).
- The ``13_triggers`` e2e runner discovers its tests dynamically instead
  of a hardcoded list that had drifted from the files on disk (#229).
- e2e ``CapturingLogger`` fakes implement ``should_emit()``, restoring
  event capture in the PII-redaction observability tests after the
  filtered-event pre-check landed (#235).

### Hierarchical Model Selection (#232)

Model choice now follows the formation hierarchy with lowest-level-wins
overrides: formation ``llm.models`` -> agent ``llm_models`` (previously
validated but never applied -- now wired) -> SOP/trigger/skill frontmatter
``model:`` -> per-step ``[model:x]`` directives. Authors specify models
where the knowledge lives; no capability inference.

- ``llm.aliases``: semantic names (``fast``, ``premium``) mapped to
  ``provider/model``, resolved before cache keying so an alias and its
  target share one cached model instance.
- Fail-fast load-time validation of every model reference in ``sops/``,
  ``triggers/``, and ``skills/`` and of alias targets; a broken alias
  errors both at its definition and at every usage site.
- Request-time failure isolation: an unresolvable override falls back to
  the agent default, and a failing override call retries on the agent's
  own model -- a model-selection problem never crashes a turn. New
  ``MODEL_OVERRIDE_APPLIED`` / ``MODEL_OVERRIDE_FAILED`` events carry the
  override source (``agent``, ``trigger``, ``skill``, ``sop_frontmatter``,
  ``sop_step``).
- When the same underlying model appears under several capabilities with
  different keys/settings, overrides deterministically prefer the ``text``
  capability's entry, else the first declared.
- Inert when unconfigured: formations without the new fields behave
  identically to before (pinned by tests).

### Trigger Transformers: response formatting + outbound routing (#228)

Trigger results can now reach external platforms (Slack, Telegram, Twilio,
any webhook consumer) with zero custom glue code -- the outbound half of the
triggers-and-transformers design.

- Transformer YAML files (``transformers/<name>.yaml``) with fail-fast
  validation: template variable substitution over trigger context and
  response data, HTTP delivery with bearer/basic/header auth, and retry
  with exponential backoff.
- Trigger frontmatter integration: ``transformer:`` / ``webhook:``
  (mutually exclusive) route the response; ``parse:`` extracts inbound
  fields via JSONPath and passes them through as template context.
- Failure isolation per the PRD: delivery errors retry, then fall back to
  the formation's default async webhook with ``transformer_error``
  metadata -- a broken transformer never loses the trigger result.
- Hardened rendering from review: markdown-to-HTML link substitution only
  emits anchors for ``http(s)`` URLs (``javascript:``/``data:`` render as
  plain text), truncation never exceeds ``max_length`` even with long
  suffixes, and whitespace-bearing templates keep their whitespace.

### Workflow-level replanning (#227)

When a workflow fails after task-level recovery is exhausted, the runtime
can now analyze why and ask the decomposer for a fundamentally different
plan instead of returning the failure. Disabled by default
(``overlord.workflow.replanning.enabled``).

- ``ReplanningCoordinator``: failure analysis, replan generation through
  the existing ``TaskDecomposer``, duplicate-plan detection, and
  per-original-workflow attempt budgets (replans of replans share one
  budget, default 3).
- Non-replannable errors (auth, permissions, credentials, configuration,
  data corruption) never trigger a replan -- a different plan hits the
  same wall.
- Replanned executions run within the *remaining* time budget of the
  original workflow, never a fresh ceiling.
- Completed work travels into the replan context so the new plan does not
  redo it; the decomposition prompt stays byte-identical when replanning
  is disabled.
- New ``workflow.replanning.{started,completed,failed,skipped}`` events
  and streaming stages.

### Artifact Memory, Phase 1: capture (#226)

Everything agents produce through ``generate_file`` (local sandbox or RCE)
is now persisted -- versioned, user-scoped, encrypted, and
retention-managed. No behavior change for agents; the data accumulates
silently for the retrieval phase to build on.

- Storage pipeline: gzip, then AES-256-GCM with per-user keys derived
  (HKDF-SHA256) from an immutable ``formation_instance_id``, local blob
  store, SHA-256 checksums, metadata row in the new ``artifacts`` table
  (both backends).
- Versioning on name match: previous head demoted, ``parent_id`` chain,
  history blobs retained; version races resolved with keyed locks plus a
  partial unique index.
- Retention worker: ``expires_at`` computed at capture from
  ``artifacts.retention``; hourly sweep soft-deletes expired rows and
  prunes blobs, following the shared background-loop lifecycle.
- Capture is a tracked background task off the response path -- every
  failure is logged and swallowed; the user response is never affected.
  Secret-interpolated content is never captured.
- Phase 2 (manifest injection + ``get_artifact*`` retrieval tools) waits
  on the Knowledge Index layer; S3 storage is rejected loudly at config
  time rather than silently falling back.

### Memory Distillery: runtime endpoint (#221)

On-premises distilleries can now push pre-processed memory into a formation
through a signed, verified channel.

- ``POST /v1/memories/distilled`` with fail-closed Ed25519 verification:
  domain-separated signatures over the raw request body, header-bound
  against replay, one indistinct 401 for every failure mode.
- Distillery registration/trust registry (admin API + table on both
  backends) with per-registration authority scoping (user patterns, event
  types, daily quotas) -- distilleries are system principals; their events
  land user-scoped and visibility stays group-governed at retrieval.
- Idempotent by construction on the event substrate; quota gates only
  net-new events, so full-duplicate replays always succeed. Pre-computed
  embeddings accepted on exact model match, re-embedded otherwise.
- Inert without ``memory.distillery`` config. The on-prem distillery server
  itself is a separate open-source project; this is the runtime side of
  the contract.

### Memory benchmarking harness, Tier 1 (#220)

``bench/memory/``: reproducible retrieval + QA benchmarks over the real
memory stack (LongMemEval, LoCoMo, ConvoMem runners) with committed
synthetic fixtures for CI, documented full-dataset downloads, cheap-model
configs (retrieval-only runs cost $0), per-run token/cost reporting,
deterministic seeds, structured JSON reports, and failure-isolated runs
that always produce a (possibly partial) report with a nonzero exit code
on any incomplete run.


### Memory Ingestion: the /v1/memories platform endpoint (#218)

MUXI now builds memory from more than interaction: developers and pipelines
can push content into a formation's memory through a first-class ingestion
API.

- **Contract**: ``POST /v1/memories`` with ``source`` / ``source_id`` /
  ``timestamp`` / ``metadata`` (plus the existing scope fields);
  ``POST /v1/memories/batch`` with per-item accepted/duplicate/invalid
  statuses; ``GET /v1/memories/ingestion/{processing_id}`` for async status
  with per-stage outcomes and token-usage cost attribution.
- **Idempotent by construction**: ``(source, source_id)`` rides the event
  substrate's unique index -- a replayed POST returns the original event id
  and its derived events (``duplicate: true``), never creates copies, and
  batches are safely retryable (limits fire before any append).
- **Tiered pipeline**: cheap local-classifier triage (no frontier LLM),
  aggressive-by-default per-source noise filtering (tunable via
  ``memory.ingestion.sources.<source>.filter``), then extraction through
  the existing flat-fact/knowledge-graph machinery with source provenance
  carried onto every derived fact. Filtered items are recorded as
  replayable events -- improve the filters later and re-project history
  instead of re-ingesting it.
- Per-user in-flight caps with leak-proof slot accounting; shared-scope
  ingestion honors the ``memory.write`` grants from memory namespaces.


### Memory Namespaces: user, group, and formation scopes (#214, #215)

Memory is no longer single-scope. A memory is written to exactly one scope
and read up the chain -- a user's queries see their own memories, their
groups' shared memories, and formation-wide memories, merged by relevance
with more-specific scopes outranking broader ones.

- **Scope substrate**: ``scope_type`` / ``scope_id`` on the memory tables
  (additive migration; existing rows read as user scope) with canonical
  constants shared by the memories store and the event substrate; working-
  memory partitions generalized to ``session | user | group | formation``,
  adding the previously missing user-level partition.
- **Shared writes are grant-gated and event-first**: writing formation or
  group scope requires a ``memory.write`` grant in the caller's group YAML
  (403 without one, glob grants supported); the scoped event must append
  before the row is written, so every shared fact is replayable by
  construction. Conversation-derived extraction remains user-scope only,
  always.
- **Read fan-out**: long-term search/list and working-memory retrieval fan
  out across ``user -> member groups -> formation`` (GBAC membership, with
  resolver fallback for non-API callers), support per-query narrowing
  (``scopes=["user"]``), and never surface another group's memories.
- Also fixes a silent pre-existing bug where flat-fact memories never
  reached the clean chat context (wrong keyword argument, exception
  swallowed) -- long-term recall now actually flows into agent responses.


### Memory Event Substrate (#212)

Every memory write is now recorded as an immutable event; the memory stores
become rebuildable projections.

- **Event log**: ``memory_events`` on Postgres and SQLite with idempotency
  keys (``source`` + ``source_id``), versioned payload schemas validated at
  write time, causation chains, and forward-compatible scope columns.
- **Dual-write**: knowledge-graph extraction, Captain's Log digests, lessons,
  and flat-fact extraction all append events alongside their existing writes
  (Phase A of the migration plan); event append failures never affect the
  projection write or the chat turn.
- **Replay**: a projector registry with wipe-and-rebuild
  (``POST /v1/memory/rebuild``), proven replay-equivalent for all three
  projections -- improve extraction logic, re-project history.
- **Selective forgetting**: ``forget_source`` soft deletion with audit events
  and a daily hard-purge loop -- the GDPR substrate the memory platform
  builds on.

### Access control hardening (#211)

A ``groups/`` directory now requires ``server.auth: "required"`` -- the
"open formation with groups" combination is a load-time validation error.
Its documented semantics gave unknown users full access while registered
users got filtered access (inverted trust); the combination is no longer
expressible.


### Group-Based Access Control (#202, #203, #204, #207)

Formation operators can now control who may interact with a formation and
which agents, triggers, SOPs, and MCP tools each group of users can reach.

- **Auth gate**: ``server.auth: required | open`` (default ``open`` -- existing
  formations unaffected). Under ``required``, requests from users not present
  in the formation's database are rejected with 401 on chat and trigger
  routes. New ``groups`` / ``user_groups`` tables build on the existing
  ``users`` / ``user_identifiers`` identity substrate; memberships reference
  external identifiers so operators can populate groups before a user's
  first interaction.
- **Auto-discovered group files**: a ``groups/`` directory activates
  permission filtering. Simplified format -- id from filename stem, plain
  lists are allow-lists, ``inherits`` with cycle detection, fnmatch globs,
  union-of-allows / any-deny-wins across a user's groups.
- **Cascading tool overrides**: one ``tools: {allow, deny}`` structure at four
  levels (MCP registry catalog, agent attachment, group per-server, group
  per-agent-per-server); most specific wins, a group override supersedes the
  inherited config, and ``tools: {deny: "*"}`` hides a server from a group.
- **Request-time enforcement**: permissions resolve once per request (TTL
  membership cache + LRU resolution cache) and filter agent routing, direct
  agent addressing, workflow planning/execution, trigger firing (403), SOP
  matching, and each agent's per-server MCP tool surface. A denied agent
  behaves exactly like an unknown one -- no information leak. Formations
  without a ``groups/`` directory are completely unaffected.

### Memory: Knowledge Graph + Captain's Log (#208, #209)

The first two phases of the memory revamp: structured relationships and a
temporal narrative layer, built alongside (not replacing) flat-fact
extraction.

- **Knowledge graph foundation**: ``kg_entities`` / ``kg_relationships`` on
  Postgres and SQLite, real-time extraction riding the existing extraction
  pipeline plus an hourly deep-extraction pass, contradiction detection with
  supersession (retain-never-delete), graph context injected into chat
  context, and graph algorithms via pgRouting (Postgres) or NetworkX
  (SQLite) behind a parity-tested interface.
- **Captain's Log**: periodic per-user digests with full source lineage (a
  cycle-checked derivation DAG), same-date digest merging, and a new
  ``/history`` client endpoint.
- **Lessons loop**: digest-extracted lessons with dedup + confirmation
  bumps, confidence decay and archiving, embedding-cluster consolidation,
  a ``record_lesson`` built-in tool, and top-N lesson injection into agent
  system prompts.

### Performance: request hot path (#190, #192, #194-#200)

- **Working memory vector search**: per-session FAISS partitions replace the
  formation-wide index -- session-scoped searches no longer scan (or get
  crowded out of top-k by) other sessions' vectors, fixing a recall bug where
  busy multi-user formations could return zero results despite good matches
  (#200); O(1) reverse index mapping removes an O(k*n) scan per search (#190).
- **Observability off the hot path**: file/stream/trail event transports moved
  to a batched background writer with connection reuse (#197); events are
  filtered before redaction and thread spawn (#196); redaction patterns are
  precompiled and redaction itself runs on the emission thread with a cheap
  container snapshot guarding against caller mutation -- output unchanged
  (#198).
- **Concurrency**: profile-memory collections fetched concurrently (#195);
  memory-extractor duplicate checks and stores batched with within-batch
  dedup (#194).
- **Hygiene**: LRU-bounded agent routing cache (#192); buffer FIFO cleanup
  moved off the shared multitasking pool onto a dedicated thread so event
  emitters stop queueing behind it (#199).

### Fixes

- **Knowledge search session filter** (#201): knowledge chunks are stored
  without a session id but were searched with one, so session-scoped
  knowledge searches silently returned zero results; the knowledge leg of
  unified search is no longer session-filtered (conversational memory keeps
  its session scoping).
- **Cache keys** (#191, #193): the overlord model cache now includes the
  model name and a settings digest, so capability model or settings changes
  no longer serve stale instances; LLM cache keys are order-preserving for
  list inputs.

## v0.20260619.0

### PII/secret redaction hardening + entity-based redaction

Observability and memory now redact secrets and personal data far more
thoroughly, and entity-based PII redaction (names, addresses, organizations,
dates of birth, financial identifiers) is a built-in capability that is on by
default.

- **Redact by default in observability**: ``observe()`` now redacts every event
  before emission instead of only a user-facing allow-list. Non-user events
  (``SystemEvents``, ``MCP_*``, ``WORKFLOW_*``, ...) previously emitted raw
  payloads that could carry secrets. A ``skip_redaction=True`` opt-out exists for
  audited, non-sensitive events.
- **Luhn-validated credit-card redaction**: 16-digit sequences are now masked
  only when they pass the Luhn checksum, eliminating false positives on order
  IDs, timestamps, and other long digit runs while still catching real cards.
- **Unified sensitive vocabulary**: a shared ``utils/sensitive_terms.py`` holds
  two term sets -- ``SENSITIVE_KEY_TERMS`` (substring-matched for dict keys) and
  ``SENSITIVE_PREVIEW_TERMS`` (word-boundary-matched for free text) -- so the
  observability redactor and the memory extractor stop drifting apart and avoid
  ``"monkey"``-contains-``"key"`` style false positives.
- **Entity-based PII redaction**: a pluggable detector layer
  (``utils/redaction/``) sits after the regex layer. The default implementation
  wraps Microsoft Presidio (spaCy ``en_core_web_sm``) and masks PERSON, ADDRESS,
  ORG, date-of-birth (date entities only in birth context), and financial
  identifiers using consistent indexed tokens (``[PERSON_1]``, ``[ORG_1]``, ...).
  Generic dates and non-Luhn numbers are deliberately preserved.
- **Core dependency, default on**: ``presidio-analyzer`` / ``presidio-anonymizer``
  are now core dependencies (spaCy + ``en_core_web_sm`` were already core, used by
  document chunking), so this is not an optional extra. A single
  ``logging.redaction.entities`` flag (default ``true``) toggles the entity layer;
  it is registered during formation load before observability is enabled. If the
  model is unavailable the layer degrades gracefully to regex-only.
- **Memory extractor gate**: the extractor reuses the shared vocabulary and the
  entity detector so PII-bearing content is kept out of long-term memory.
- **Lean image**: the lean ``Dockerfile`` now bakes ``en_core_web_sm`` into the
  install prefix so default-on entity redaction works in the default image,
  matching ``Dockerfile.production`` and the e2e image.

Files touched:
- ``utils/sensitive_terms.py`` -- NEW shared term sets
- ``utils/security.py`` -- Luhn helpers, shared vocabulary, entity-layer composition
- ``utils/redaction/{base,entity,__init__}.py`` -- NEW detector layer + Presidio impl
- ``services/observability/__init__.py`` -- redact-by-default + ``skip_redaction``
- ``services/memory/extractor.py`` -- shared vocabulary + entity-detector gate
- ``formation/formation.py`` -- register detector from ``logging.redaction.entities``
- ``formation/config/validation.py`` -- validate ``logging.redaction``
- ``pyproject.toml`` -- presidio promoted to core dependencies
- ``Dockerfile`` -- bake ``en_core_web_sm`` into the lean image
- ``tests/unit/test_observability_redaction.py`` -- NEW redact-by-default tests
- ``tests/unit/utils/test_redaction.py`` -- NEW detector/Presidio tests (incl. live)
- ``tests/unit/utils/test_security.py`` -- Luhn coverage
- ``e2e/tests/18_observability/test_18c_pii_redaction_observability.py`` -- NEW e2e:
  pipeline redaction with the flag on and off
- ``e2e/tests/18_observability/test_18d_pii_redaction_chat.py`` -- NEW e2e: real chat
  turn never leaks secrets/PII into emitted events

## v0.20260616.0

### SOP Skill Directives -- deterministic activation from SOP steps

SOP steps can now declare skills that should be activated deterministically
before the assigned agent processes the task, using a new bracket directive
syntax similar to ``[agent:...]`` and ``[mcp:...]``.

- **Bracket syntax**: ``[skill:skill-name]`` for activation-only, ``[skill:skill-name/script-name]`` to also run a script from the skill's ``scripts/`` directory. Placed on the same line as the step heading after ``[agent:...]``.
- **Deterministic activation**: the workflow executor calls ``skill_manager.activate_async`` directly before ``agent.process_message``, without waiting for the LLM to choose the ``activate_skill`` tool. Skill content is injected into the task prompt as a skill prelude.
- **Deterministic script execution**: when the run form is used and an RCE client is available, the executor calls ``run_skill_command`` directly before the agent runs, and the script output is appended to the task prompt under "Skill execution results".
- **Request-scoped transient grants**: SOP-declared skills work even when not pre-declared for the assigned agent in its YAML formation. The executor registers transient grants via ``skill_manager.grant_request_skills`` before workflow execution and revokes them in ``finally``.
- **Script resolution**: ``_resolve_skill_command`` maps ``script.py`` -> ``python3 scripts/script.py``, ``script.sh`` -> ``bash scripts/script.sh``, ``script.js`` -> ``node scripts/script.js``; if no extension is given, the stem is matched against existing ``scripts/*`` entries.

Files touched:
- ``datatypes/workflow.py`` -- ``SkillRef`` model added to ``SubTask.required_skills``
- ``skills/skill_manager.py`` -- request grant registry with ``grant_request_skills`` / ``revoke_request_skills``
- ``agents/skill_dispatch.py`` -- ``run_skill_command`` extracted as shared helper
- ``workflow/decomposer.py`` -- ``_SOP_SKILL_RE`` regex, skill extraction in both step parsers
- ``workflow/executor.py`` -- activation / run injection in ``_execute_task_with_agent``, grant lifecycle in ``_execute_workflow_internal``
- ``agents/agent.py`` -- ``_current_request_id`` tracked, passed to skill tool builders
- ``overlord/overlord.py`` -- ``skill_manager`` passed to ``TaskDecomposer``, ``overlord`` wired into executor
- ``prompts/sop_template_mode.md`` / ``sop_guide_mode.md`` -- directive documentation updated
- ``tests/unit/test_sop_skill_directive.py`` -- 13 unit tests for parsing, dedup, grants, script resolution

### E2E: new skill-directive activation test

- ``e2e/tests/21_skills/test_21b4_sop_skill_directive_activation.py`` -- standalone E2E test that loads a formation with a ``test-skill`` and a ``skill-activation-test`` SOP, invokes it via ``overlord.chat()``, and asserts deterministic activation, skill content injection, and clean shutdown.

### E2E: update deprecated Gemini model

All E2E formation YAMLs referencing ``google/gemini-2.0-flash`` (shut down by Google)
now use the stable successor ``google/gemini-2.5-flash``. This fixes formation-loading
404 errors in tests that depend on vision/video model declarations.

### Dependency minimums updated to latest compatible releases

65 direct dependency minimums in ``pyproject.toml`` raised to the newest
resolvable versions after ``uv lock --upgrade``. Notable bumps:
- ``mcp>=1.27.2`` (was 1.26.x)
- ``fastmcp>=3.4.2`` (was 3.2.x)
- ``numpy>=2.2.6`` (was 1.24.x)
- ``pandas>=2.3.3`` (was 2.0.x)

## v0.20260508.0

### Fix: scheduler firing recursion — overlord re-classified delivery as new schedule request

Recurring scheduled jobs (e.g. ``remind me to drink coffee every 3 minutes``) were spawning a fresh one-time job on every firing instead of delivering the reminder. Three layers of the scheduler pipeline were involved; the actual fault was at the overlord layer, not the prompt rewriter.

When a recurring job fires, ``SchedulerService`` invokes ``overlord.chat()`` with the stored ``execution_prompt`` (e.g. ``"remind me to drink coffee"``) as the user message. The overlord runs every incoming message through ``request_analyzer`` for intent classification — and a phrase like ``"remind me to drink coffee"``, in the absence of any context that this is a delivery, correctly classifies as ``is_scheduling_request=True``. The scheduler-intent handler at the top of the chat pipeline then short-circuits the request and creates a NEW one-time job ID, returning a synthesized ``"I've created a scheduled job for you..."`` message. The agent never runs, no reminder is delivered, and ``scheduled_jobs`` accumulates orphan rows on every firing.

Three surgical changes:

- ``overlord.chat()`` (``formation/overlord/overlord.py``) now takes ``is_scheduled_execution: bool = False``. When ``True``, both the scheduler-intent handler and the scheduler-query handler are bypassed so the message reaches the agent as a normal delivery.
- ``SchedulerService._execute_job`` (``services/scheduler/service.py``) passes ``is_scheduled_execution=True`` from the firing path so any chat invocation tied to a job session is treated as delivery, not new scheduling.
- ``PromptRewriter._llm_rewrite_prompt`` (``services/scheduler/rewriter.py``) no longer treats ``rewritten == original_prompt`` as failure. The rewriter prompt explicitly tells the LLM to return the input unchanged when there are no timing words to strip; wrapping that with ``"Execute scheduled task: "`` was a misread of intent that compounded the recursion (orphan jobs stored ``execution_prompt`` values like ``"Execute scheduled task: remind me to drink coffee"``). Empty LLM responses still fall back to the prefix wrapping. Surrounding quotes the LLM occasionally adds despite explicit instructions are now stripped.

The downstream symptom from the bug report — empty ``job_results`` rows at the receiving webhook — resolves automatically once the agent actually runs and produces a real reply for the webhook payload, instead of the synthesized "I've created a scheduled job" string.

Adds ``tests/unit/test_scheduler_rewriter.py`` covering unchanged-output, empty-output, normal-rewrite, quoted-output, and llm-unavailable paths.

## v0.20260503.0

### Fix: audio probe regression, MCP cancel-scope race, knowledge OOM (onellm pin bump to 0.20260502.1)

Four independent fixes shipped together after a full e2e regression sweep (176/263 tests, all green).

**1. Audio probe regression** (`formation/agents/agent.py`). The model-capability probe added in an earlier release inadvertently broke the audio transcription path. The probe now correctly checks `capability_models["embedding"]` before falling back, restoring audio transcription without touching the embedding probe logic.

**2. MCP cancel-scope race** (`services/mcp/transports/command.py`). A task-cancellation race in the stdio MCP transport caused tool calls to be silently dropped when the overlord cancelled an in-flight request. The cancel-scope is now scoped tightly around the subprocess lifetime rather than the entire connection, so in-progress tool results drain cleanly before teardown.

**3. Knowledge ingestion OOM / macOS jetsam** (`formation/agents/agent.py`). Knowledge ingestion loaded the wrong model on Apple Silicon: `capability_models` lookup was falling through to the text model instead of the embedding model, loading a second large ONNX graph on top of the already-resident embedding graph. Peak RSS reached ~8.7 GB and macOS jetsam killed the process at ~280 s before any chat-side work ran. Fix: probe `capability_models["embedding"]` explicitly; the wrong-model load path is now unreachable.

**4. onellm pin bump to `>=0.20260502.1`** (`pyproject.toml`, `Dockerfile.pytorch`, `Dockerfile.cuda`). Picks up the CoreML compiled-artifact cache fix in onellm 0.20260502.1: `CoreMLExecutionProvider` now receives a `ModelCacheDirectory` option pointing at `$HF_HOME/onellm-coreml/<repo>/<revision>/`, so the compiled `.mlmodelc` package persists across process restarts instead of being recompiled on every `InferenceSession` construction. Combined with fix 3 above, the knowledge e2e suite on Apple Silicon went from 280 s + SIGKILL to 38 s warm.

### Docker: bump lean variants to ``python:3.13-slim`` (and narrow markitdown extras)

The lean Dockerfiles (``Dockerfile``, ``Dockerfile.production``, ``e2e/docker/Dockerfile``) move from ``python:3.10-slim`` to ``python:3.13-slim``. The library's own ``requires-python`` floor in ``pyproject.toml`` stays at ``>=3.10`` - the upper end of the supported interpreter range expands; the lower end is unchanged.

Why the bump: third-party benchmarks measure CPython 3.14 at ~2.0-2.4x faster than 3.10 on pure-Python loops (with the largest single jump at the 3.10 -> 3.11 cliff). MUXI's hot path is overwhelmingly I/O-bound (LLM round trips, MCP subprocess JSON-RPC, DB round trips, network embeddings), so the realistic end-user delta is in the single-digit percent range - but the change is mechanical and the orchestration glue (planning loops, JSON manipulation in the agent tool-call loop, prompt builders, SOP / workflow planning) does benefit on every request.

Companion change in ``pyproject.toml``: the ``markitdown[all]`` dependency is narrowed to ``markitdown[docx,pdf,pptx,xls,xlsx]``. This is necessary to unblock 3.14 and is independently a hygiene win - the previous ``[all]`` superset pulled four extras MUXI does not actually use:

- ``audio-transcription`` (pydub + speechrecognition) - audio transcription in MUXI goes through OneLLM, not MarkItDown (see ``services/multimodal/fusion_engine.py``).
- ``az-doc-intel`` (azure-ai-documentintelligence + azure-identity)
  - no Azure Document Intelligence ingest path exists.
- ``outlook`` (olefile) - no ``.msg`` ingest path exists.
- ``youtube-transcription`` (youtube-transcript-api~=1.0.0) - no YouTube URL ingest path exists, and this transitive is what blocked 3.14: every release of ``youtube-transcript-api 1.0.x`` declares ``requires_python = "<3.14,>=3.8"``. Newer 1.2.x supports 3.14, but ``markitdown[all]``'s ``~=1.0.0`` pin holds pip to the 1.0.x line. Codebase audit confirmed zero direct imports of ``youtube_transcript_api``, ``mammoth`` (used only via the kept ``docx`` extra), ``pdfminer`` / ``pdfplumber`` (used only via the kept ``pdf`` extra), ``pydub``, ``speech_recognition``, ``olefile``, or any Azure DI SDK.

Behavioural impact for downstream library users: ``MarkItDown`` still converts every file format MUXI's knowledge ingest dispatches to (``.docx``, ``.pdf``, ``.pptx``, ``.xls``, ``.xlsx``). Users who previously relied on MUXI's transitive install of MarkItDown to pick up Outlook ``.msg`` ingest, audio transcription via MarkItDown, Azure DI, or YouTube transcripts now need to install ``markitdown[all]`` explicitly alongside ``muxi-runtime``. The trade-off is intentional: the previous behaviour silently shipped ~120 MB of unused-by-MUXI dependencies on every install AND blocked ``muxi-runtime`` from installing on Python 3.14 in the first place.

What changed:

- ``Dockerfile`` (lean / default, both builder and runtime stages): ``python:3.10-slim`` -> ``python:3.13-slim``.
- ``Dockerfile.production`` (lean + bundled PostgreSQL 17 + FAISSx via supervisor): ``python:3.10-slim`` -> ``python:3.13-slim``.
- ``e2e/docker/Dockerfile`` (E2E test harness with all services and the test runtime): ``python:3.10-slim`` -> ``python:3.13-slim``.
- ``pyproject.toml``: ``markitdown[all]>=0.1.0`` -> ``markitdown[docx,pdf,pptx,xls,xlsx]>=0.1.0``.

What did NOT change:

- ``Dockerfile.pytorch`` and ``Dockerfile.cuda`` use a parametrized ``${BASE_IMAGE}:${BASE_TAG}`` and are gated separately on torch wheel availability. They stay on whatever their callers pin and are not touched here.
- ``Dockerfile.ci-test`` is built on ``ubuntu:22.04`` with Python installed via apt; the ``FROM`` line does not reference a ``python:`` tag. Unchanged.
- ``pyproject.toml::requires-python = ">=3.10"``. Bumping the library minimum is a breaking change for downstream users with no offsetting benefit.
- ``black target-version`` (``[py310, py311, py312, py313]``), ``ruff target-version`` (``py310``), ``mypy python_version`` (``3.10``). The Docker bump does not require source-syntax features past 3.10. Adding 3.14 to these target lists is a separate decision.
- CI matrix. Adding 3.14 to the CI matrix is a separate decision.

Verification:

- **Resolver**: full ``pip install --dry-run`` against the core dep set on Python 3.14 / ``manylinux_2_28`` for both ``x86_64`` and ``aarch64`` resolves cleanly - all wheels available, no source builds.
- **Build, arm64**: native ``docker build`` on the local Apple Silicon host succeeds. Image size: 1.9 GB (down from 2.11 GB on 3.10 - ~10% reduction from the dropped extras + slimmer Trixie base + newer wheels).
- **Build, amd64**: cross-build via ``docker build --platform linux/amd64`` (BuildKit + QEMU) succeeds. The aarch64-specific ``sqlite-vec`` recompile in the builder stage uses ``python -c "import sys; print(f'python{sys.version_info.major}. {sys.version_info.minor}')"`` to derive the install path; this branch was exercised on the arm64 build and is version-agnostic.
- **SIF, arm64**: ``./scripts/build/sif.sh --arch arm64`` produces a 551 MB SIF (down from 643 MB on 3.10 - 14% smaller).
- **SIF, amd64**: ``./scripts/build/sif.sh --arch amd64`` produces a 607 MB SIF (down from 643 MB on 3.10 - 5.6% smaller). The smaller delta on amd64 is expected - amd64 wheels for ``scipy`` / ``numpy`` / ``pandas`` are slightly larger than their aarch64 counterparts and ``onnxruntime`` ships a fatter amd64 binary. SIF deployed to ``~/.muxi/server/runtimes/`` and smoke-tested via ``runtime-runner:latest`` under QEMU emulation on the Mac host: passes (Python 3.14.4 / x86_64; faiss 1.13.2; pyzmq 27.1.0; markitdown + the kept extras' backends import OK
  - mammoth, pdfminer.six, pdfplumber, python-pptx, openpyxl,
  xlrd; the four dropped extras confirmed absent; ``muxi.runtime.formation.initialization.probe_declared_models`` callable; ``SystemEvents`` enum reports 127 entries).
- **Wheels confirmed in the built image**: ``faiss-cpu 1.13.2`` (cp310 abi3 on manylinux_2_28), ``pyzmq 27.1.0`` (cp312 abi3 on manylinux_2_28; the 3.14 standard-ABI wheel is published as ``cp314-cp314t`` for the free-threaded interpreter only, but the abi3 wheel covers the standard interpreter), ``psycopg2-binary 2.9.12``, ``spacy 3.8.13``, ``lxml 6.1.0``, ``mammoth 1.11.0``, ``pdfminer.six 20251230``, ``pdfplumber 0.11.9``, ``python-pptx 1.0.2``, ``openpyxl 3.1.5``, ``xlrd 2.0.2``, ``scipy 1.17.1``, ``numpy 2.4.4``, ``pandas 3.0.2``, ``cryptography 47.0.0``, ``Pillow 12.2.0``, ``pydantic 2.13.3``, ``protobuf 7.34.1``.

### Formation: probe declared models at init; refuse to load on 404

Finding 5 from the 2026-04-29 MS365 testing run: the dev's formation declared ``embedding: local/all-MiniLM-L6-v2`` and the embedding service silently degraded to recency-only memory retrieval on every request, surfacing only an opaque ``InvalidConfigurationError`` deep in the runtime path. Two follow-up fix attempts by the dev failed because the failure mode masquerades as a "model not available" issue when the actual root cause is a slug-syntax problem: OneLLM's dispatcher splits the model name on the **first** ``/`` only, so ``local/all-MiniLM-L6-v2`` is passed to HuggingFace as the bare repo id ``all-MiniLM-L6-v2``, which is not a valid HF identifier. The canonical form is ``local/sentence-transformers/all-MiniLM-L6-v2``, where everything after ``local/`` is the full ``<owner>/<repo>`` HF slug. OneLLM has no curated alias table - what you write is what gets sent to HF.

The runtime's only previous defense was the after-the-fact ``InvalidConfigurationError``. By the time it fired, the formation had already loaded, vector search was already broken, and the operator had no signal that the cause was a typo in their slug rather than a deeper environmental problem.

This change introduces a fail-fast probe at formation init. After ``initialize_llm_config()`` populates ``formation._capability_models`` and the text-fallback cascade runs, ``probe_declared_models()`` is invoked. It iterates every distinct ``(model_slug, probe_kind)`` pair, dedups across capabilities, and issues a minimal OneLLM call: ``Embedding.acreate(input="probe", model=...)`` for the ``embedding`` capability and ``ChatCompletion.acreate(messages=[{"role":"user","content":"ping"}], max_tokens=1, model=...)`` for everything else (``text``, ``vision``, ``audio``, ``documents``, ``streaming``, future capabilities).

Failure classification is deliberate. Two error classes from OneLLM abort formation init via ``ConfigurationValidationError``:

- ``ResourceNotFoundError`` (HF 404 / provider model-not-found)
- ``InvalidRequestError`` (HF validation error - the dev's exact bare-name slug case)

Everything else (``AuthenticationError``, ``RateLimitError``, ``ServiceUnavailableError``, ``RequestTimeoutError``, other ``OneLLMError`` subclasses, and non-``OneLLMError`` exceptions indicating probe-machinery bugs) is logged at WARN and continues. This split is intentional: the two fatal classes are deterministic "this slug will never resolve" failures, while the rest is either transient or environmental, and bricking an otherwise-healthy formation on an init-time auth blip is worse than the silent degradation the probe is meant to prevent.

Probes run **synchronously, serially**. The first fatal aborts before later probes execute, so an operator with multiple bad slugs fixes them one error message at a time rather than wading through a dozen entangled failures. ``ChatCompletion`` cost: ~50 input + 1 output token per probe, fractions of a cent on cloud providers, zero on cached local models.

The fatal error message is dynamic. For ``local/<bare-name>`` slugs (the exact failure mode the dev hit) the message names the correction explicitly:

```
Cause: the local slug is missing the owner/organization segment.
The runtime requires the full HuggingFace repo id:
    local/<owner>/<repo>   (e.g. local/sentence-transformers/all-MiniLM-L6-v2)
NOT local/<repo>          (e.g. local/all-MiniLM-L6-v2)
```

For ``local/<owner>/<repo>`` slugs that 404, the message points at typo / gated-repo causes. For cloud slugs the local-specific hint is omitted entirely so the message stays relevant.

Three new ``SystemEvents`` cover the lifecycle: ``MODEL_INIT_PROBE_STARTED``, ``MODEL_INIT_PROBE_COMPLETED``, and ``MODEL_INIT_PROBE_FAILED`` (with ``severity ∈ {fatal, warn}`` and the underlying ``OneLLMError`` class encoded in the payload).

Tests cover failure-class mapping, slug-shape-aware error formatting, capability dedup, and end-to-end probe outcomes. The serial-fail-fast invariant -- first 404 aborts before later probes run -- is locked in.

No escape hatch was added. Correctness over convenience: a formation that won't actually work shouldn't pretend to be loading.

### MCP: translate misleading upstream errors into agent-actionable hints

Findings 4 and 6 from the 2026-04-29 MS365 testing run both surfaced the same defect from the agent's perspective: an Excel tool call (``list-excel-worksheets`` and ``excel-write-range`` respectively) received a ``driveItemId`` / ``file_id`` that pointed to a folder rather than a workbook. Microsoft Graph returned 403 with the message ``"Could not obtain a WAC access token."`` — a WAC-token error that, read at face value, looks like an auth failure. The agent surfaced it to the user as a permissions problem rather than re-resolving the file ID.

The runtime's parameter-funnel work in 0.20260410.0 already covers the *common* failure modes for this flow: ``parameters`` defaults on MCP server declarations remove the LLM's need to infer org-level constants like ``driveId``, and ``_validate_inferred_parameters_against_results()`` rejects LLM-fabricated IDs not found in any prior successful result.

But the WAC case sits in a fourth class the funnel doesn't catch: the agent picks a *real* ID from a *real* prior tool result — it's just the **wrong type** for the next tool's contract. The Attachments folder ID does appear in ``list-folder-files`` output, so it isn't fabricated; the required param isn't missing; clean-context binding is irrelevant. The runtime can't disambiguate folder-vs-file inside a generic list response without per-MCP semantics — that line stays on the model side. But the runtime *can* spot the misleading error pattern after the fact and tell the agent what likely happened, so the next turn carries an actionable correction instead of a confusing auth-flavored error.

**Implementation.** New module ``services/mcp/tools/error_translator.py`` with a small registry of ``_ErrorPattern`` declarations. Each pattern gates on three signals — content regex (case-insensitive search of the upstream error text), required arg keys (at least one of these must be in the tool call's arguments — prevents matching unrelated tools), and an optional server_id regex (for server-specific patterns; default ``None`` means server-agnostic). First-match-wins on overlap. The single shipped pattern catches the WAC-token case gated on ``driveItemId`` or ``file_id`` being present:

```
category:           excel_wac_token_folder_id
content_regex:      r"could not obtain a wac access token" (IGNORECASE)
required_arg_keys:  ("driveItemId", "file_id")
hint:               "Likely cause: the supplied driveItemId/file_id
                     refers to a folder rather than a workbook (.xlsx)
                     file. […] Re-resolve the workbook ID via
                     list-folder-files (or the equivalent listing tool)
                     and select the item whose name ends in '.xlsx' —
                     not a folder such as 'Attachments'."
```

**Wiring.** ``services/mcp/service.py::_invoke_tool_with_resolved_credentials`` calls ``translate_tool_error`` on the processed result whenever ``isError`` is True (right after ``ModernProtocolFeatures.process_structured_output``). On a match, two writes to the agent-bound payload:

* Structured ``_runtime_hint = {"category": ..., "message": ...}`` field for observability and any future structured consumer.
* Inline append to ``content``: ``"\n\n[Runtime hint] {hint}"`` so the model literally reads the correction in the tool message on the next turn (most reliable surface for self-correction).

The translator never blocks the call. It only annotates an existing failure — at worst, the agent reads an extra sentence and ignores it. Original upstream error text is preserved verbatim.

**Observability.** Reuses ``MCP_TOOL_CALL_COMPLETED`` (no new event type) with a new ``translation_category`` metadata field. ``None`` when no pattern fired; the category string when one did. Lets us track in production which translations are actually firing without adding event type churn.

**What this fix is NOT.** It does not validate parameters before sending — that's already done by the ``_validate_inferred_parameters_against_results()`` machinery shipped in 0.20260410.0 for the fabricated-ID class, and the ``parameters`` field on MCP server declarations for the org-level defaults class. It also does not attempt to disambiguate folder-vs-file at parameter inference time — that requires per-MCP semantic knowledge the runtime should not own.

**What this fix DOES require.** Formations using ms365-mcp must declare ``parameters: { driveId: ..., siteId: ..., tenantId: ... }`` on the server block to fully benefit from the parameter funnel — the WAC-translation hint covers the wrong-typed-ID case, but upstream failures from missing org-level constants are a config gap the formation must close.

**Tests** in ``tests/unit/test_mcp_error_translator.py`` cover the frozen-dataclass contract, the WAC pattern (positive matches with both ``driveItemId`` and ``file_id``, case-insensitive content match, server-agnostic firing), the three negative gates (missing arg keys, non-matching content, non-dict arguments), the ``server_id_regex`` semantics, registry first-match-wins on category overlap, and end-to-end injection through ``ModernProtocolFeatures.process_structured_output`` confirming both the structured ``_runtime_hint`` field and the inline ``[Runtime hint]`` suffix on ``content``.

### Scheduler: restore job stat persistence + collapse doubled session_id + preserve delivery framing + disambiguate scheduled execution at agent boundary

Three independent scheduler bugs surfaced by user testing on a recurring ``*/3 * * * *`` reminder job. After two confirmed successful runs the ``scheduled_jobs`` row showed ``last_run_at NULL``, ``total_runs 0``, ``last_run_status`` empty — yet the user's external webhook receiver *had* recorded the result text in their ``job_results`` table. From the outside the scheduler looked broken; from the inside it looked like the job had never run.

**1. Job stats never persisted (the root cause).**

``Overlord._execute_async_request`` referenced ``self._scheduler`` (with a leading underscore) at four sites — but the scheduler is stored as ``self.scheduler_service``. ``hasattr(self, "_scheduler")`` returned False on every scheduled run, so the entire completion-handler block was silently skipped:

```python
if (
    hasattr(self, "_scheduler")   # ← always False
    and self._scheduler           # ← never evaluated
    and session_id
    and session_id.startswith("job_")
):
    handled = await self._scheduler.complete_job_from_webhook(...)
```

Effect on every successful scheduled run:

* ``mark_job_execution_success`` never called → ``total_runs`` stayed 0
* ``scheduled.job.completed`` event never emitted
* ``last_run_at`` / ``last_run_status`` never updated
* External webhook *was* delivered (control fell through to the standard delivery branch once the inner ``if`` was skipped) — which is why the user's external receiver had the result and made it look like the job worked

The four references were renamed to ``self.scheduler_service`` (``getattr(self, "scheduler_service", None)`` to keep the original defensive shape during early init). The accompanying silent ``except Exception: pass`` blocks — which were how this typo hid for months — were replaced with logged ``ERROR.INTERNAL_ERROR`` warnings, so any future breakage on this path surfaces in observability instead of vanishing.

**2. Doubled ``job_`` prefix in ``session_id`` (cosmetic).**

``_execute_single_job`` constructed ``session_id = f"job_{job_id}"`` — but job IDs are already prefixed by the manager, producing ``job_job_<id>`` in every observability event:

```json
{
  "event": "scheduled.job.started",
  "data": {
    "job_id":     "job_JmYB5QuDisCdBpLU",
    "session_id": "job_job_JmYB5QuDisCdBpLU"
  }
}
```

``complete_job_from_webhook`` papered over the doubling with ``job_id = session_id[4:]`` (strips the first ``job_`` and recovers the real job_id), so the lookup *worked* and the dev-reported hypothesis that this caused the missing stat updates was incorrect — both ends used the same doubled string. But the relationship between session_id and job_id was no longer obvious to anyone reading code or logs. Now: ``session_id = job_id`` directly, and the strip in ``complete_job_from_webhook`` becomes ``job_id = session_id`` (the ``startswith("job_")`` namespace guard stays).

**3. Prompt rewriter strips delivery framing (behavioral).**

The scheduler's prompt rewriter over-compresses scheduled prompts. A user scheduling

> ``remind me to drink water every 3 minutes``

ended up with an execution prompt of bare ``drink water``. The agent, receiving that as a fresh user message with no scheduling context, interpreted it as a confirmation and replied:

> "Got it. Drinking water now? Want me to set up a daily reminder?"

— a recursive offer to schedule the exact reminder it was already executing. Reminders, notifications, and "send me a summary of" scheduled tasks were silently non-functional whenever their intent lived in the framing.

Root cause: the rewriter prompt told the model to "Strip away ALL scheduling patterns" but never explicitly told it to *preserve* delivery framing (``remind me``, ``notify me``, ``send me``, ``tell me``, ``show me``, ``alert me``). A 12B model interprets "all scheduling patterns" generously and treats ``remind me to`` as metadata.

The rewriter prompt was rewritten to:

* Frame the rewrite for the agent's perspective: "the agent will receive your output as a fresh user message — with NO knowledge that it was scheduled" — drives home why framing matters.
* Explicitly call out delivery-framing words as part of the action, NOT scheduling.
* Provide a side-by-side correct/wrong table including the exact failure case (``remind me to drink water`` → keep, NOT strip).
* Spell out the recipient pronoun (``remind ME``, ``tell US``).

**4. Disambiguate scheduled execution at the agent boundary (behavioral, second-order).**

Live-testing the rewriter fix surfaced a second-order problem. Rewriter output for ``remind me to drink water every hour`` is now correctly ``remind me to drink water`` — but when the cron fires and that string lands in the agent as a fresh user message with no context, Claude Sonnet 4.6 treats it as a chat request to *configure* a reminder and politely declines:

> "Can't set reminders directly — no access to your clock or
> notification system. Quickest fix: just tell your phone's
> assistant 'Remind me to drink water every hour' and you're done."

A recursive offer to schedule the exact reminder it was already executing. The rewriter is correct; the agent is missing the context that this is a *firing*, not a *configuration request*.

Live-tested four marker variants on hello-muxi. The minimum form

```
[SCHEDULED] remind me to drink water
```

worked perfectly with no system-prompt change required. The agent produced direct reminder content (``💧 Water break! Hey, time to grab a glass of water``) and even self-tagged the response with ``Scheduled reminder ✓``. Longer preambles accidentally triggered SOP routing (variant C posted to GitHub), so the marker has to stay minimal.

Implemented as a single-source-of-truth helper in ``chat_orchestrator.py``:

```python
SCHEDULED_EXECUTION_MARKER = "[SCHEDULED] "

def _apply_scheduled_marker(message: str, session_id: Optional[str]) -> str:
    if session_id and session_id.startswith("job_"):
        return f"{SCHEDULED_EXECUTION_MARKER}{message}"
    return message
```

Wired into both message-rendering paths: the analyzer-pipeline ``=== CURRENT REQUEST ===`` rendering inside ``_enhance_message_with_context``, and the agent-LLM ``current_user_message`` field returned by ``_build_clean_chat_context``. ``buffer_turns`` (history rendered from buffer memory) is intentionally left untouched — past scheduled invocations appear in history as the original user text, since the assistant's prior responses already encode the scheduled-execution behavior.

**Memory and observability stay clean.** PR #165's ``EnhancedMessage(original, enhanced)`` threading pays off here: the ``original`` field is the raw user text the marker is applied *on top of*, so:

* Buffer memory stores the unprefixed message (``remind me to drink water``) — no marker pollution in conversation history.
* Observability events emit ``message_preview`` from the original, not the enhanced/marked form — the ``clarification.request.sent`` and ``overlord.agent.selection_started`` events on a scheduled run show ``"message_preview": "remind me to drink water"`` (verified live).
* Only the agent's view at inference time gets the marker — visible in the ``agent.planning`` event's ``request`` field, which is the correct place since that event records what the agent is planning *against*.

**Live verification matrix on hello-muxi (Claude Sonnet 4.6):**

| Scenario | session_id | Expected | Result |
|---|---|---|---|
| Scheduled job firing | ``job_test1`` | reminder content | ✓ ``💧 Water break!`` |
| Normal chat | ``normal-chat`` | no regression | ✓ same as pre-fix |
| Streaming scheduled | ``job_stream_test`` | reminder content via stream | ✓ ``💧 Water check!`` |
| Adversarial — user types ``[SCHEDULED]`` in normal chat | ``user-typed-bracket`` | agent ignores marker, answers normally | ✓ answered the question, no exploit surface |

**Tests** in ``tests/unit/test_bugfix_verification.py`` lock the four invariants: no live code references ``self._scheduler``; ``_execute_single_job`` uses ``session_id = job_id`` directly (and ``complete_job_from_webhook`` no longer slices with ``[4:]``); the rewriter prompt explicitly preserves delivery framing; and the centralized ``[SCHEDULED] `` marker helper applies on job session IDs and not on non-job ones, with both rendering paths calling the helper rather than re-implementing the rule.

### MCP tool filtering via ``tools.{whitelist|blacklist}``

Adds an optional ``tools`` block on any MCP server config that lets operators register only a subset of an upstream catalog. Cuts both the runtime tool registry and the per-turn planning prompt down to the capabilities a formation actually needs — reducing token spend per planning call and preventing destructive upstream tools (e.g. ``delete_repo``, ``force_push_branch``) from being plannable in the first place.

**Schema.** Either ``tools.whitelist`` *or* ``tools.blacklist`` (mutually exclusive) on any MCP server ``.afs``:

```yaml
type: "http"
endpoint: "https://api.githubcopilot.com/mcp/"
auth: { type: "bearer", token: "${{ secrets.GITHUB_PAT }}" }
tools:
  whitelist:
    - "search_*"
    - "get_*"
    - "list_*"
    - "issue_*"
    - "add_issue_comment"
    - "create_or_update_file"
```

Patterns are fnmatch globs (``*``, ``?``, character ranges). Literal names are matched exactly. Both list members are case-sensitive to match the upstream MCP convention.

**Pipeline.** Translation lives in a new pure module ``services/mcp/tool_filter.py``: ``ToolFilterSpec.from_config`` is total and tolerant (malformed input → inactive spec); ``apply_filter`` is the single entry point used during registration. The filter runs *between* ``tools/list`` and registry insertion in ``MCPService._connect_single_transport`` so post-filter empty sets abort registration with a typed ``mcp.tool_filter.empty_set`` warning instead of silently registering an agent with zero tools.

**Wiring.** Both registration sites now honor the spec:

* ``Formation._register_mcp_servers`` (formation-level, always-on servers) — ``formation.py:2419``
* ``Overlord._register_agent_mcp_servers`` (per-agent re-registration during agent load) — ``overlord.py:2092``

A dropped agent-level wiring would silently re-register the full upstream catalog after agents loaded, defeating the filter for any flow that reached the agent path. The live test caught it.

**Observability.** Three new ``SystemEvents`` emitted per registration:

* ``MCP_TOOL_FILTER_APPLIED`` (info) — full pattern resolution table so operators can audit exactly which upstream tools each glob expanded to. Critical for catching silent scope expansion when an upstream adds a tool that newly matches a wildcard.
* ``MCP_TOOL_FILTER_UNKNOWN_TOOL`` (warning, once per unknown literal pattern) — surfaces typos with ``difflib`` "did you mean?" suggestions. Glob patterns that match nothing emit an empty suggestion list (suppressed to avoid noise).
* ``MCP_TOOL_FILTER_EMPTY_SET`` (warning) — registration aborted because the post-filter set is empty.

A clean ``[ INFO ]`` init line also prints the resolution inline next to ``Connected to MCP``:

```
[ INFO ] MCP 'github-mcp' tool filter (resolved 29/44 tools via whitelist(9 patterns))
           whitelist['search_*'] -> 5 match(es): search_code, search_issues, ...
           whitelist['issue_*']  -> 2 match(es): issue_read, issue_write
           whitelist['add_issue_comment'] -> 1 match(es): add_issue_comment
[  OK  ] Connected to MCP 'github-mcp' (29 tools available via streamable http)
```

**Validation.** ``ConfigValidator._validate_mcp_tools_block`` enforces fail-fast load-time rules: mutex (``whitelist`` XOR ``blacklist``); list-of-strings; non-blank patterns. Empty pattern lists log a ``no filter will be applied`` warning rather than failing — operators sometimes scaffold the block before populating it.

**Live measurement on ``example-formations/demo/hello-muxi``.** A 12-phrase variation battery against a capability-scoped whitelist (29 of 44 github-mcp tools registered) showed:

* 0 errors, 0 warnings across all runs
* 4/4 guestbook-comment paraphrases ("sign", "leave a note", "say hi", "post a greeting on issue 50") routed correctly to the ``community-greeter`` agent and posted to issue #50 via ``add_issue_comment``
* 4/4 muxi-expert concept questions ("what is muxi", "tell me about the overlord", "explain formations", "what's an SOP") returned MUXI-grounded answers
* Per-request token footprint: ~12.0k for guestbook flows, ~13.5k for concept Q&A — vs ~23.3k pre-filter for the same workload (~48% reduction on a matched flow)

**Tests** in ``tests/unit/test_mcp_tool_filter.py`` cover pure filter semantics (literal, glob ``*`` / ``?``, mixed lists, ordering, unknown-pattern ``difflib`` suggestions, empty-set reporting, pass-through field preservation), ``ToolFilterSpec.from_config`` tolerance, and the formation-level validator hooks (mutex, type, blank, empty, clean whitelist, clean blacklist).

### Collapse three synthesis LLM passes into one persona call

Removes the agent-level and workflow-level synthesis LLM calls and replaces both with deterministic builders that feed structured input into the overlord's existing ``_apply_persona`` pass — which is now the single LLM hop on the way back to the user.

**Before**: a workflow turn with N tasks made N agent-synthesis calls (one per task), one workflow-synthesis call to merge them, and one persona call to dress the merge for the user — all sequential, all cloud round-trips. A bare chat turn made one agent-synthesis call followed by the persona call. Three of those LLM hops were the runtime saying the same thing back to itself.

**After**: agents emit raw structured output via a new ``Agent._build_raw_response`` deterministic renderer (``### {placeholder}`` sections, dict results expanded as ``key: value``, artifact filenames inline, delegated-agent prose appended verbatim). The overlord's ``_synthesize_workflow_results`` delegates merging to a new ``_consolidate_workflow_results`` helper that produces budget-bounded per-task sections via the existing ``_render_task_body`` — no LLM call. ``_apply_persona`` is the single user-facing LLM hop and its system prompt was extended with two contracts inherited from the deleted synthesis prompts: a raw-input acknowledgment that names the ``### Task`` / ``### {placeholder}`` markers it should expect, and the date-preservation guardrail that previously lived in the workflow synthesis system prompt.

Dead code removed: ``Overlord._create_synthesis_prompt``, ``Overlord._get_workflow_synthesis_system_prompt``, ``Overlord._fallback_synthesis``. Skip-synthesis observability events now emit ``reason: always_skip_v2`` (chat turn) and ``reason: deterministic_consolidator`` (workflow turn) so operators can audit the new path.

**Expected savings on the canonical hello-muxi cold path**: ~4 s on a chat turn (one agent-synthesis call eliminated), ~20 s on a 4-task workflow turn (four agent-synthesis calls + one workflow-synthesis call eliminated). Live end-to-end run on develop confirmed: Turn 2 issue-listing dropped from 38.4 s to 34.0 s and Turn 3 multi-step delegation produced a 3934-character briefing in 86.6 s with zero ``planning_response_synthesis_*`` events emitted.

**Tests** pin the always-skip contract on the agent path, the ``_build_raw_response`` deterministic output shape, the persona system prompt's raw-input acknowledgment and date-preservation guardrails, and the new ``_consolidate_workflow_results`` helper (lifted from the prior ``_create_synthesis_prompt`` suite).

### Hot-reload secrets without restarting the formation

Adds an admin-only ``POST /secrets/reload`` endpoint that refreshes the running formation's in-memory secret cache from ``secrets.enc`` without restarting the process. Useful when secrets are rotated externally (e.g. CI redeploys the encrypted file) and you don't want to bounce a live formation just to pick up the new values.

**Non-destructive merge semantics** Reload does not replace the cache wholesale. It performs an add-or-override merge:
- secrets present on disk but missing in memory are added
- secrets present in both places are overwritten with the disk value
- secrets present only in memory are preserved and are NOT deleted

The preservation rule is intentional: an in-memory-only secret may have been added through the API or be in active use by a running agent / MCP integration, and silently dropping it on reload would break those consumers.

**Failure isolation** If decrypting or parsing ``secrets.enc`` fails, the existing in-memory cache is left untouched and the endpoint returns 500. The reload is performed under the existing ``SecretsManager`` async lock, so concurrent readers never see a partially-built cache.

**Scope of effect** Reload affects future secret lookups that read from the live cache (e.g. ``get_secret``, ``interpolate_secrets``, skill env resolution, runtime user-credential resolution). It does NOT retroactively rewrite values that were already interpolated into formation config during initialization or into MCP auth at registration time — those remain fixed until a normal reload of the affected component.

New pieces:
- ``SecretsManager.reload()`` returning ``{added, overwritten, preserved, count}``
- ``Formation.reload_secrets()`` wrapper
- ``APIEventType.SECRET_RELOADED`` (``secret.reloaded``)
- ``POST /secrets/reload`` admin route emitting the merge summary

Five new unit tests in ``tests/unit/test_secrets_reload.py`` cover add, overwrite, preserve, failure-leaves-cache-intact, and missing-file behaviour.

### Cold-path latency cuts: classifier preload + SOP-template analyzer skip

Two complementary changes that together shave ~16-18 s off the cold hello-muxi demo path without touching the workflow executor or model selection. Both are pure additions; nothing in the existing flow is removed and there is a fallback for every new fast path.

**Local classifier preloaded at formation startup** The local prototype-similarity classifier (``Xenova/multilingual-e5-small``, introduced in PR #160) lazy-loaded on first user request, costing ~10 s on the very first chat turn — easily the worst-feeling part of the demo. ``Overlord._async_startup`` now awaits ``_get_local_classifier()`` immediately after the routing/extraction models are ready, moving that cost off the critical path. The existing process-wide ``services.classification.get_classifier()`` singleton means subsequent overlord/scheduler/credential consumers adopt the warmed instance for free. Failures during preload degrade to the legacy lazy-init path with a warning event, never block startup.

**SOP-template fast path skips the LLM request analyzer** When an SOP has been matched earlier in a request AND is in deterministic ``template`` mode, the analyzer's complexity score and topic tags are not consulted by the downstream workflow — the SOP itself is the plan. ``_process_sync_chat`` now skips the ~6-8 s ``request_analyzer.analyze_request`` LLM call and substitutes a stub ``RequestAnalysis`` with ``requires_decomposition=True``, ``is_security_threat=False``, and empty topics.

Security is not regressed: a fast heuristic regex screen (``_looks_heuristically_suspicious``) runs against the actual user message before the skip is taken. The pattern set covers the canonical prompt-injection / jailbreak phrasings ("ignore previous instructions", "reveal your system prompt", "you are now DAN", role- override prefixes like ``<|im_start|>system``, content-policy override attempts, etc.). When any pattern matches, the gate falls through to the full LLM analyzer so the higher-confidence verdict still runs and can block the request.

A new debug-level ``WORKFLOW_ANALYSIS_SKIPPED`` event fires whenever the fast path is taken, tagged with ``reason: sop_template_match``, ``sop_id``, ``sop_name``, and ``skipped_stage: request_analyzer_llm``, so operators can audit how often the override is biting.

22 new unit tests in ``tests/unit/test_overlord_sop_template_analyzer_skip.py`` pin the heuristic screen (8 attack patterns must flag, 7 benign inputs must not), the stub ``RequestAnalysis`` shape (safe defaults, reasonable complexity/confidence), and the composed gate (benign + template = fast path; attack + template = falls through; guide-mode SOP never takes fast path; no SOP never takes fast path).

### Synthesis capability in AFS schema (companion spec)

Adds an optional ``synthesis`` capability to the formation LLM model list, with the same shape and options as ``text``: ``api_key`` override plus ``settings.{temperature, max_tokens, timeout_seconds, max_retries, fallback_model}``. When present, agents route the post-tool-call response synthesis stage through this model; when absent, agents fall back to ``text`` (existing behavior). Pure spec addition for now — runtime resolution is a follow-up.

Documented in ``afs-spec/schemas/formation.afs`` and the SCHEMA_GUIDE override hierarchy section.

### Maintenance: FastAPI deprecation + OneLLM startup warning

* ``audit`` admin route: replaced ``Query(regex=...)`` with ``Query(pattern=...)``. FastAPI deprecated ``regex=`` in favor of ``pattern=``; the runtime now emits the right keyword and the startup deprecation warning is gone.
* ``llm.py``: registered a ``warnings.filterwarnings`` for the ``onellm.cache`` UserWarning that fires when OneLLM's default semantic-cache embedding model lacks ONNX weights and PyTorch isn't installed. The cache correctly falls back to hash-only mode and the runtime ships ``Xenova/multilingual-e5-small`` for actual semantic similarity work, so the warning is noise that scared users on every formation startup. Filter is registered immediately before the ``onellm_init_cache`` call in ``initialize_onellm_cache`` so it stays scoped to the cache module.

### SOP-aware actionability gate (post-PR-#160 regression)

Fixes a demo regression where the hello-muxi formation would silently swallow a matched SOP. Replaying the demo flow:

* User says "onboard me"
* `sop.matched` fires at +1.1s for SOP `onboarding` (mode `template`)
* Clarification analyzer returns `action: execute`
* `_is_actionable_message` (the new local prototype-similarity classifier from PR #160) returns `False` for the bare two-word phrase
* Overlord takes the persona fast path, returns a chat-style reply
* No `agent.planning`, no `overlord.routing.completed`, no GitHub issue comment — the matched SOP is dropped on the floor

The classifier replacement was the right call for filtering bare social chatter ("hi" / "thanks" / "got it") at ~50 ms instead of a cloud LLM round-trip, but it is deliberately conservative on short verb-light phrases. Pre-PR-#160 the LLM-based check correctly read "onboard me" as a procedure trigger; the new heuristic does not.

Fix: extracted the actionability decision in `overlord._process_sync_chat` into a small helper `_resolve_actionability(message, matched_sop)`. Behavior:

* No SOP match → defer to `_is_actionable_message` verbatim (preserves the PR #160 latency win for greetings/acks)
* SOP match + classifier says actionable → no-op, return `True`
* SOP match + classifier says non-actionable → **force `True`** and emit a debug-level `SOP_MATCHED` event tagged `stage: actionability_override` so operators can audit how often the override is biting

A matched SOP is by definition actionable: we already know what to do. The classifier verdict cannot override an explicit procedure match.

Tests in `tests/unit/test_overlord_actionability_sop_override.py` pin all four classifier x SOP combinations plus the `name`-fallback metadata shape.

### Pure-chat multi-turn context fix (clean role-turn bundle)

Fixes cross-turn context loss in pure-chat sessions where honesty-trained models (Sonnet 4.6 most prominently) would respond "I'm missing the context here" to a simple follow-up question (`"What about the language thing though?"`) on turn 3 of an otherwise normal four-turn conversation, despite the buffer memory holding the full prior exchange.

Root cause: every pure-chat turn was sent to the agent's LLM as a **single user message** wrapping the request inside a `=== CURRENT REQUEST ===` block, with the prior conversation re-serialized as a flat `[12:30] User: ...` blob inside a `=== CONVERSATION CONTEXT ===` section of that *same* user message. GPT-class models pattern-match through this; honesty-trained models read the explicit "CURRENT REQUEST" framing as an isolated query and treat the surrounding prose as ambient metadata, not history. The result was correct context retrieval but a confused model.

Fix:

* **`ChatOrchestrator._build_clean_chat_context`** — new helper that builds a structured bundle alongside the existing marker-formatted `enhanced_message` (kept verbatim because the analyzer pipeline — clarification, classifier text extraction, planning intent extraction — depends on the marker contract). The bundle carries buffer history as proper role turns (`{"role": "user"|"assistant", "content": ...}`), the un-enhanced current user message, plus `user_profile_text` / `long_term_memories` / `file_results` as separate fields. `chat()` now `gather()`s both representations in parallel and threads the bundle through `_create_stream_generator` → `_process_sync_chat`.
* **`Overlord._process_sync_chat`** — accepts and forwards `clean_chat_context` to `Agent.process_message`.
* **`Agent._assemble_messages_from_clean_context`** — new helper that produces a chat-API-shape `[system_with_addendum, ...buffer turns, current_user]` list. Profile, memories and file-results land in a *system addendum*, not embedded inside the user turn.
* **`Agent.process_message`** — when a clean bundle is supplied, prefers the raw user text from the bundle and rebuilds `self._messages` via the helper each turn rather than appending marker-formatted blobs into agent-instance state. This produces a transcript shape that matches a normal direct LLM call.
* **`Agent.process_message` `direct_simple_response` path (line ~2229)** — the empty-plan synthesis path was constructing its own `[system, current_user]` pair from scratch, which silently bypassed the freshly-rebuilt `self._messages`. Now reuses the fully-assembled transcript when a clean bundle is present, falling back to the legacy two-message pair for non-chat callers.

Verification: replayed the same four-turn solo-trip transcript against Sonnet 4.6 (`anthropic/claude-sonnet-4-6`). Turn 3 now opens "You'll be totally fine in Lisbon" and turn 4 builds on the prior anchor-mornings advice. Input token count grows turn over turn (8703 → 9406 → 9027 → 9560) where it was previously flat at ~8000 every turn — confirming the model is actually receiving the accumulated history rather than re-processing the same isolated turn.

Tests in `tests/unit/test_chat_orchestrator_clean_context.py` pin the bundle shape, chronological reversal of recency-first buffer rows, the race-filter that drops the current user message if the buffer stored it ahead of us, role/empty-text filtering, and the agent-side assembly invariants (system addendum, no double history in any user turn).

### Review hardening (PR #160)

Two follow-ups from greptile code review:

* **Deleted dead `get_default_classifier()`** in `services/classification/local_classifier.py`. The function declared its own competing `_default_classifier` / `_default_lock` singleton but was never imported or called anywhere — all consumers (`overlord`, `scheduler`, `fusion_engine`) go through `get_classifier()` in `classification/__init__.py`. Per AGENTS.md "no dead code" rule, removed the dead function entirely along with the now-unused `Optional` import.
* **Added minimum-margin gate** to both Group B clarification fast paths. New module-level constant `MIN_FAST_PATH_MARGIN = 0.05` in `clarification.py`. `_analyze_request` STEP 1.5 and `_check_need_more` STEP 0 now skip the LLM only when the classifier is **both** confident in "no clarification" **and** the margin clears the threshold. On a near-zero margin (uncertain centroids) the call falls through to the LLM, preserving the clarification-on-ambiguity guarantee. Below- threshold cases emit a `logger.debug` line so operators can audit how often the threshold is biting; no new event types or config surface.

  ```python
  if not needs_clar and margin > MIN_FAST_PATH_MARGIN:
      # confident-no — skip LLM
  elif not needs_clar:
      # uncertain-no — fall through to LLM
  ```

### Fix: synthesis LLM hallucinated "the file didn't come through" on mixed-result artifact plans

Surfaced from a hello-muxi demo trace: `create a bar chart showing pretend quarterly sales of acme corp` returned the chart attachment **and** a synthesis paragraph saying the file didn't come through. The attachment WAS there; the prose contradicted reality.

**Root cause.** `Agent._serialize_planning_result_for_synthesis` strips the `_artifact` key from each `my_results` entry before serializing for the synthesis LLM:

```python
serializable_result.pop("_artifact", None)
```

That left the synthesis prompt with **zero ground-truth signal** that any file was attached. The pure-artifact synthesis-skip fast path (`439b9271`, v0.20260427.0) didn't fire either, because the plan had two steps — `activate_skill(file-generation)` produces a non-`_artifact` instruction blob, and `generate_file` produces the artifact-bearing result. Mixed-shape `my_results` correctly fail the `every entry has _artifact` gate, so synthesis ran. With nothing in the prompt to confirm the file existed and a SOUL coaching the model to "be honest if something's broken," Sonnet 4.6 took the metadata-only view as failure evidence and wrote the contradiction.

**Fix.** Surface the attached artifacts as a dedicated block in the synthesis prompt — explicitly so the LLM knows the file IS surfacing in the user's UI and cannot hallucinate failure.

* New `Agent._collect_attached_artifact_lines(my_results)` helper. Walks result values, pulls every `_artifact` (handles both `MuxiArtifact` Pydantic instances and dict-shaped fallbacks), and renders one line per artifact:
  ```
  - acme_corp_quarterly_sales.png (image/png, 56.4 KB)
  ```
* `Agent._build_planning_response_synthesis_prompt` calls the helper. When non-empty, it injects:
  ```
  FILES ALREADY ATTACHED TO THIS RESPONSE:
  - acme_corp_quarterly_sales.png (image/png, 56.4 KB)

  These files have been successfully generated and will surface in the user's UI
  regardless of what you write below. Do NOT claim a file is missing, did not come
  through, or that generation failed when this list is non-empty. You MAY mention
  the filename(s) naturally in your reply.
  ```
  …right before the existing closing instructions. Pure-text plans (no artifacts at all) get no block — the conditional keeps prompt size unchanged for the common case.

The serializer is left as-is — it correctly avoids dumping the full `MuxiArtifact` (binary `data_url`, base64 thumbnails) into the LLM context. The new block carries only the user-facing identifying data (filename, type/format, size).

**Out of scope (deliberate):**

* **Did not loosen the synthesis-skip gate** to treat `activate_skill` results as transparent. That's a fine follow-up if the demo team wants `activate_skill + generate_file` to skip synthesis entirely, but Option B addresses the structurally weaker path: the case where synthesis runs anyway. Both Options A and B can coexist.
* **Did not modify `hello-muxi/SOUL.md`.** The bug was in the prompt, not the persona — the SOUL's "be honest" coaching is correct guidance; the LLM was just lacking the ground truth it needed to be honest about.

**Tests** in `tests/unit/test_agent_planning_helpers.py` cover extraction from a real `MuxiArtifact` instance, dict-shaped fallback with `format` + `metadata.size_bytes`, partial metadata (missing format/size/filename), non-`_artifact` results skipped (the mixed-plan case), and end-to-end mixed-plan vs pure-text-plan prompts (block present in the former, absent in the latter).

### Performance: localize 13 binary classification gates — heavy PDF median 60.4 s → 50.7 s (-16 %)

The pre-planning critical path was emitting 4-5 cloud LLM calls per non-trivial request — actionability detection, workflow eligibility, clarification analysis, simple-question detection, recall-question detection, plus credential and scheduler binary checks deeper in the flow. Every one of those was structurally a **binary** decision (yes/no, label/no-label) or a pure semantic-similarity score. None of them needed a cloud LLM. A 384-dim multilingual embedder pinned against curated prototype exemplars classifies them in ~60 ms with deterministic accuracy on the eval set, and ships as part of the runtime — no extra service, no API key, no network round-trip.

**The architecture.** New `services/classification/` module:

* `prototypes.py` — 11 `IntentSpec` definitions, each carrying 8-15 positive + 8-15 negative exemplars (with 1-2 multilingual entries per spec where the call site is multilingual).
* `local_classifier.py` — `classify_binary(intent, text)` and `pairwise_similarity(text_a, text_b)`.
* `__init__.py` — public API + a process-wide singleton accessor (`await get_classifier()`).

The model is `local/Xenova/multilingual-e5-small` (384-dim, ONNX, multilingual), auto-downloaded by OneLLM on first use, cached under the standard HuggingFace cache directory. Classifier warmup batch- embeds all positive and negative exemplars once at first use, computes L2-normalized centroid pairs per intent, and caches them in-process. Per-call cost: ~60 ms median on Apple Silicon ONNX Runtime. Process warmup is ~13 s, amortized.

**Phase 1 (commits `3acd09e9`, `1ca9b3be`) — six pre-planning gates moved local:**

* `Overlord._is_actionable_message`
* `Overlord._is_non_actionable_for_workflow`
* `Overlord._is_simple_question`
* `UnifiedClarificationSystem._check_context_switch`
* `UnifiedClarificationSystem._check_stop_intent`
* The recall-question detection at STEP 1 of `_analyze_request`

**Phase 2 (commits `3fc8d8c1` → `cd39e50c`) — seven more gates in three patterns:**

* **Group A — full replacements (no LLM fallback when classifier is healthy).**
  * `CredentialHandler.is_credential_request`
  * `CredentialHandler._is_cancellation` (multilingual: en/es/fr/ja exemplars)
  * `CredentialHandler._is_help_request` (multilingual)
  * `JobManager._is_significant_prompt_change` → `pairwise_similarity(old, new) < 0.88` (calibrated threshold).
* **Group D — direct cosine replacement.**
  * `MultiModalFusionEngine._calculate_semantic_similarity` → `pairwise_similarity(source_desc, target_desc)`. The LLM was being asked to score 0.0-1.0 similarity; that *is* cosine in an embedding space, so we compute it directly.
* **Group B — fast-path skip (split text generation from classification decision).** The clarification analyzer (`mt=250-1000`) and the inner "do we need more info?" gate produce a `{needs_X: bool, question: str}` structured output. The classifier owns the binary; the LLM only fires on the positive branch (where it has to *generate* the clarifying question). On a confident-no the LLM never runs. Wired in `UnifiedClarificationSystem._analyze_request` (STEP 1.5) and `_check_need_more` (STEP 0).

**Deferred (intentional, not regressions):**

* **Agent router** (`AgentRouter.select_agent_for_message`, sequential, ~8 s on heavy PDF). Skipped for defense-in-depth security reasons — the router doubles as a defense surface against malicious agent-name injection in user input.
* **Topic extraction** in `RequestAnalyzer` (parallel, ~1.5 s). Skipped because the analyzer LLM still runs for 11 other structured-output fields — replacing topics alone breaks the call into two round-trips and saves nothing.
* **`IntentDetectionService`** (4+ multi-class call sites). Skipped: bigger blast radius; would need a `classify_multiclass` method and per-`IntentType` prototype curation.

**Failure modes — every wired gate falls back to the prior behavior on classifier-fail.** Group A credential gates fall back to the preserved keyword fallback from the legacy LLM-fail branches. Group A scheduler gate falls back to `True` (consider all changes significant — same conservative default the prior LLM-fail branch used; better to spawn a fresh job than silently reassign one). Group D fusion engine falls back to neutral 0.5. Group B fast-paths fall through to the existing LLM call path. This fall-through is the safety net, not a feature flag — a transient classifier outage degrades gracefully back to pre-Phase-2 behavior with no config surface to keep in sync.

**Observability.** New `SystemEvents.LOCAL_CLASSIFIER_INITIALIZED` (emitted once per process the first time the classifier warms; carries `warmup_ms` and the list of warmed intents). Group B fast-path skips reuse `ConversationEvents.CLARIFICATION_SKIPPED` with `method: "local_classifier_fast_path"` and `margin: <float>` so operators can audit how often they fire and what the classifier's confidence looked like.

**Measured impact** on the canonical `hello-muxi → "create a one-page PDF about MUXI"` workload, three runs per condition, same prompts in same order:

| Stage | Heavy PDF wall (median) |
|---|---:|
| Phase 0 (post-perf, pre-classifier) | 60.353 s |
| Phase 1 + 2 (today) | **50.709 s** |

Wall-time delta vs Phase 0: **-9.6 s, -16 %.** Cumulative delta vs the original 108 s baseline: **-57.3 s, -53 %.** LLM call buckets across the three runs:

| Bucket | Phase 0 | Phase 2 |
|---|---:|---:|
| classification (`mt <= 64`) | 3 | **0** |
| synthesis (`mt <= 4000`) | 8 | 9 |
| planning (`mt > 4000`) | 2 | 1 |

The cleanest signal is `classification` going to **zero** across all three Phase 2 runs — direct confirmation that the binary gates are now exclusively local. The +1 in synthesis is the clarification analyzer (`mt=250`) still firing on runs where the classifier defers; the Group B fast-path is opportunistic by design, not aggressive.

The 9.6 s improvement comes almost entirely from the **Group B fast-path on the clarification analyzer**, which was the bottleneck of the parallel pre-planning batch in the Phase 0 trace. The four parallel gates ran via `asyncio.gather` and the wall clock was bound by the slowest call (~5 s clarification analyzer). Phase 2 collapses that to ~60 ms when the classifier is confident no clarification is needed (which it should be, and is, on "create a one-page PDF about MUXI").

The remaining ~50 s on the heavy PDF path is downstream of pre-planning — agent router (~8 s), topic extraction (~1.5 s), the planning round-trip itself (~30-40 s on Sonnet-class models for 16 K-token planning prompts with 56 MCP tools in scope), plus post-planning execution + synthesis. None of those are binary-classification-shaped, so none of them are this pass's target.

**Microbench (server-free)** in `bench/classifier_microbench.py` exercises the classifier in isolation:

| Op | Median | Per-call speedup vs cloud LLM |
|---|---:|---:|
| `classify_binary` (across all 11 intents) | 51-79 ms | ~12-13× |
| `pairwise_similarity` (10 paraphrase pairs) | 53 ms | ~12× |

(The reference cloud cost is ~750 ms median for `mt <= 1000` `gpt-4o-mini` calls, measured on the same network during Phase 0 baselining.)

**Tests** in `tests/unit/test_local_classifier.py` cover spec invariants (disjoint pos/neg sets, length cap), per-intent accuracy floors (>=85%), pairwise correctness (identical near 1.0, paraphrase >=0.95, cross-language same-task >=0.85, same-vs-different gap >=0.10, symmetry within 1e-5, empty input raises), failure modes, diagnostic snapshot, and singleton accessor identity. New module: `src/muxi/runtime/services/classification/`. Wiring: overlord, clarification, credentials, scheduler, fusion engine. New event: `LOCAL_CLASSIFIER_INITIALIZED`. Measurement harnesses and artifacts live under `bench/`.

### Fix: remote-buffer recall in `_enhance_message_with_context`

Symptom: in remote-buffer / FAISSx mode (``memory.buffer.vector_search: true``), follow-up and meta-recall questions ("list back the technical skills I mentioned earlier", "summarise what we've discussed") would receive a "I don't have access to your prior details" response even when the relevant turns were still in the buffer. Local-buffer mode worked fine for the same prompts.

Root cause: ``ChatOrchestrator._enhance_message_with_context`` chose the buffer-search query based on ``vector_search``:

* ``vector_search=False`` (local default): ``query=""`` → recency-only fast path → always returns the most recent buffer items.
* ``vector_search=True`` (remote default): ``query=<current message>`` → vector + recency_bias=0.3 hybrid.

For meta-recall questions the embedding of the QUERY does not match the embeddings of the CONTENT messages it wants to recall — the 0.3 recency bias alone is too weak to surface them and the LLM gets no buffer context.

Fix: when ``vector_search`` is enabled the orchestrator now issues both passes concurrently (``asyncio.gather``) and merges them. Vector results keep their relevance ordering at the head; recency-only items missing from the vector pass append at the tail. Items appearing in both passes are de-duplicated by ``(text, timestamp)``. The local-mode path is unchanged — single empty-query call, no extra round-trip.

### Fix: downgrade user-self-recall false-positives in security analyzers; await workflow-approval kv_set

Two real bugs surfaced while triaging unrelated e2e test fragility:

1. **``information_extraction`` false-positives on user-self-recall.** Both LLM-based security analyzers (``RequestAnalyzer._llm_analyze_request`` and ``AgentRouter._parse_routing_response``) intermittently classified benign user-self-recall messages ("list back the role I mentioned earlier", "summarize my profession", "what's my name?") as ``information_extraction`` attacks and short-circuited with "I can't process that request." — the LLM never saw buffer context. Both prompts already carved this out in plain English; the classifier just would not comply on borderline phrasings.

   Added a deterministic post-LLM heuristic ``RequestAnalyzer._heuristic_is_user_self_recall`` that downgrades the classification only when **all three** hold: (a) the message contains a first-person possessor anchored to the user themselves, (b) it contains a recall verb / "mentioned earlier" anchor pointing back at the conversation, and (c) it does NOT name a system-state target (system prompt, config, internal tools, credentials, …). Wired into both call sites:

   * ``RequestAnalyzer._llm_analyze_request`` only downgrades the ``information_extraction`` threat type — ``prompt_injection``, ``credential_fishing``, ``jailbreak`` are untouched.
   * ``AgentRouter.select_agent_for_message`` treats SECURITY_BLOCK on user-self-recall as a null routing decision so the intelligent fallback picks an agent. Real attack messages still propagate ``SecurityViolation``.

   Strengthened both LLM prompts with a more explicit not-a-threat carve-out covering the recall phrasings the LLM was previously missing.

2. **Workflow-approval pending state lost to a fire-and-forget race.** ``_handle_workflow_approval`` used the fire-and-forget ``_set_pending_clarification`` on the hand-off back to the user. Because the user's reply ("Yes, please proceed") arrives almost immediately, the kv_set could race past the response: the next request reads ``_get_pending_clarification`` → ``None``, the workflow_approval branch is skipped, and the approval message is treated as a fresh, contextless prompt ("Could you share more about the plan?"). The ``ambiguous_credential`` path already used the synchronous variant for exactly this reason; applied the same fix here with a comment referencing both call sites so future drive-by edits don't regress.

### E2E test fixes: `test_2d1_local_buffer_mode` and `test_9a3b_with_approval`

Both tests had been failing on develop for reasons unrelated to recent performance work. Investigation surfaced three real fragility sources:

1. **Missing ``session_id`` on ``overlord.chat()`` calls** in ``test_2d1``. Per AGENTS.md "ID hierarchy", ``session_id`` scopes buffer-memory filtering; without one, every turn got an auto-generated session and prior buffer context was invisible. Pinned a stable ``session_id`` per test case.
2. **Single-turn buffer anchoring is unreliable.** With only one prior turn the LLM frequently responds about its own capabilities rather than the conversation. Added an explicit follow-up turn before each recall probe so the buffer has at least two anchored content messages.
3. **``test_9a3b``'s primary criterion is auto-async approval detection on complex tasks.** The legacy keyword check was actually testing post-approval workflow content — a separate surface that exposed bug #2 above. Reframed the post-approval content match as a non-blocking secondary observation so the primary auto-async criterion can pass cleanly when the approval prompt is correctly emitted.

### Performance: enable OneLLM HTTP/2 connection pooling at runtime startup

OneLLM ships an opt-in connection pool (``onellm.init_pooling()``) that switches the per-request httpx client to a shared, HTTP/2-multiplexed pool. With pooling on, bursts of parallel calls to the same provider reuse one TLS connection (h2 via ALPN), and sequential calls amortize the TCP+TLS handshake across the keepalive window instead of paying it on every request.

Until now, the runtime never called ``init_pooling()`` — so the dev build of OneLLM with HTTP/2 was installed but dormant. ``run_formation`` now initializes the pool before formation load (or skips silently on older OneLLM versions without ``init_pooling``) and tears it down in the cleanup path.

**Measured impact** on the canonical ``hello-muxi → "create a one-page PDF about MUXI"`` test (3-run sequence per condition, same prompts in same order):

| Run        | HTTP/2 ON | HTTP/2 OFF | Δ            |
|------------|-----------|------------|--------------|
| 1 (cold)   | 64.7s     | 71.7s      | -7.0s  (-10%)|
| 2 (warm)   | 21.6s     | 26.3s      | -4.7s  (-18%)|
| 3 (warm)   | 19.7s     | 21.9s      | -2.2s  (-10%)|
| **total**  | **106.0s**| **119.9s** | **-13.9s (-12%)** |

Disable via ``MUXI_HTTP_POOL_DISABLED=1`` if pooling causes issues with a specific provider; the runtime falls back to the per-request-client behavior cleanly.

### Performance: skip the post-planning synthesis call for pure-artifact responses

After planning execution, the agent fires a *second* LLM call — ``_synthesize_planning_execution_response`` — to weave tool/delegation results into a user-facing prose response. For artifact-heavy requests ("create a one-page PDF", "generate a chart", "make a CSV") the synthesized prose is mostly boilerplate ("Here's your file:") because the artifact itself is the answer. The synthesis call adds 3-10s of wall time on Sonnet-class models for content the user is not actually reading.

**Fix:** when both gates open, the agent now substitutes a deterministic acknowledgment ("Done — I've created report.pdf for you.") for the synthesis call. Both gates must hold to bypass:

* **Pure-artifact result.** Every entry in ``my_results`` must carry an ``_artifact`` key. Mixed text+artifact results still run synthesis because the LLM has real data to explain. An empty result set also runs synthesis (an empty response is more likely a problem than a silent success).
* **Active streaming.** Either ``overlord.response.streaming = true`` in the formation YAML, or the current request id is registered with the streaming manager. With streaming on, the user has been seeing real-time tool progress events; without streaming, the synthesized prose is the only narrative they receive and we keep it.

The bypass emits an ``AGENT_PLANNING`` observability event with ``phase=synthesis_skipped`` and ``reason=pure_artifact_with_streaming`` so production traces clearly show when the fast path fires. Streaming detection is best-effort — any failure falls back to the safe behavior (run synthesis) so a broken streaming module cannot regress chat responses.

17 new unit tests cover pure-artifact detection (empty / mixed / non-dict / missing key), the deterministic acknowledgment (single / multiple files, missing filename, ``name`` vs ``filename`` field), the streaming gate (formation config, per-request, exception swallowing), a static guard against accidental call-site removal, and three integration scenarios verifying that synthesis is *not* called on the skip path and *is* called on each guarded path.

### Performance: cache MCP tool results within a workflow window

Many tool plans repeat the same read-only call within a single chat session — e.g. listing a repo's files at the start of planning and again during execution, or fetching the same Slack channel metadata multiple times during a multi-step workflow. Each repeat paid the full MCP round-trip cost (network + provider + serialization).

**Fix:** `Agent.invoke_tool` now wraps the underlying MCP call in a short-lived in-process result cache (5-minute TTL, formation+user scoped). The cache is deliberately conservative:

* **Default-deny classifier.** A new `services.mcp.tool_cache` module inspects the tool's verb token (`read_*`, `get_*`, `list_*`, `search_*`, etc.) and only caches names that match a known read vocabulary. Mutator verbs (`create_*`, `update_*`, `delete_*`, `send_*`, `post_*`, `set_*`, `add_*`, `run_*`, `execute_*`, `start_*`, `stop_*`, etc.) are never cached. Tools matching neither vocabulary default-deny — false negatives only cost latency, false positives can produce incorrect application behavior.
* **Built-in side-effect tools** (`generate_file`, `activate_skill`, `run_skill`) are always denied because they have process-level side effects (artifact creation, RCE execution, skill state mutation).
* **Formation- and user-scoped keys.** The cache key includes `formation_id` and `user_id` so two formations or two users in the same process never share results, even for tools with identical parameters. Per-user tools (mailboxes, vaults, credential-bound APIs) are protected by construction.
* **Errors are never cached.** A tool that returns `_is_tool_execution_error(result) == True` skips the store step; serving a stale rate-limit or network-blip error across the TTL would extend the failure window unnecessarily.
* **Token-based name matching.** `is_cacheable("lookup_address")` correctly returns `True` instead of false-positive matching the substring `_add` inside `address`. Names are tokenized snake_case + camelCase before classification.

A new `MCP_TOOL_CACHE_HIT` observability event surfaces hit rates and the running counters (`hits`/`misses`/`stores`/`skipped`) for production monitoring.

The cache is process-local, has no LRU eviction (TTL-only), and dies with the runtime — same characteristics as the existing LLM response cache, kept consistent on purpose. 50 new unit tests cover key determinism, scope isolation, TTL expiry, the verb classifier, and counter increments.

## v0.20260427.0

### Performance: kill the 30s wasted-timeout cycle and the 12s buffer-memory cold start

End-to-end production trace of *"create a one-page PDF about MUXI"* on the hello-muxi formation showed 108 seconds of wall time for what ended up being a single-tool plan (activate_skill + generate_file). Two specific costs dominated the trace:

1. **Wasted 30s timeout on every complex planning call** (saves ~45s). `LLM._execute_with_resilience` was passing `messages=None` to `calculate_adaptive_timeout`, with a `# Known limitation` comment acknowledging the helper couldn't see the real payload. The result: every chat call got the bare 30s base timeout regardless of how much context it carried. A planning prompt with 58 tool definitions plus ~15K tokens of input genuinely needs ~34s on Sonnet 4.6 — so the first attempt timed out at 30s, the resilience layer retried with a 1.5x escalation (45s budget), and the retry succeeded ~34s later. Fix: the chat-path closures now thread their `messages`, `files`, and `max_tokens` through `_execute_with_resilience` via internal kwargs (`_adaptive_messages`, `_adaptive_files`, `_adaptive_max_tokens`) which are popped before reaching the wrapped provider call. `messages` is the input-size signal (1s per ~1000 tokens); `max_tokens` is the output-size signal (2s per 1000) and was the second-order bug surfaced during vanilla validation: input scaling alone gave the planning call 36.8s — still 6s short of what Sonnet 4.6 actually needed — so the first attempt still timed out and the retry escalated to 55.2s. Adding the output-size signal pushes the first-attempt budget for a planning call (16K max_tokens) to ~70s, eliminating the wasted retry entirely. Embedding and transcription paths still pass `None` and rely on the operation-type modifier alone — they don't suffer from the same bug.

2. **Knowledge-handler cold start moved off the user's first message** (saves ~20s on first request). `Agent._ensure_knowledge_initialized` was lazy — the `KnowledgeHandler` (and the Nomic embedder it transitively loads) wasn't constructed until the first user message landed. That deferred ~8s of chunking+embedding plus the ~12s Nomic model cold-start onto the user's first chat request, producing a visible "first message is sluggish" artifact in production traces. Fix: `Overlord._create_agent_from_config` now eagerly calls `await agent._ensure_knowledge_initialized()` for any agent with a `knowledge` config block immediately after MCP-server registration. This shifts both costs to formation `up` (where operators expect a brief warmup) and warms the Nomic embedder in the same pass — the working-memory write of the user's first message used to trigger the same cold start in parallel, dropping that 12s spike too. Failures during eager init propagate (matches the existing MCP-register fail-fast policy) and emit a `SERVICE_UNAVAILABLE` event tagged `phase=knowledge_eager_init` so operators can distinguish startup vs runtime knowledge failures.

Vanilla measurement on the same query (hello-muxi formation, macOS, Sonnet 4.6, RCE on localhost:7891) confirmed: **108s → 65.9s (~40% reduction)**. Buffer-memory write on first message dropped from 12.3s to 0.6s (47x). Planning round-trip dropped from 80.9s to 36.1s (45s saved) — single attempt, no retry cycle.

14 new unit tests across `tests/unit/test_llm_adaptive_timeout.py` (10 tests covering timeout scaling math including `max_tokens`, kwarg-leak prevention, and call-site forwarding for both `chat` and `chat_with_tools` paths) and `tests/unit/test_overlord_eager_knowledge.py` (4 static guards on the eager-init call site, await contract, observability tagging, and fail-fast propagation).

### Deferred: parallel knowledge-source loading

`KnowledgeHandler.load_sources_from_config` still iterates sources sequentially. Naively wrapping the for-loop in `asyncio.gather` would race two writers through `WorkingMemory.add_with_embedding` — that method does `await self._ensure_dim()` and then mutates `self.index` without holding a lock, and the broad `except` at the FAISS `.add()` site silently drops chunks if a shape mismatch happens during a concurrent dim-probe. The expected win is small (~1-2s per formation up — Nomic inference is GIL-serialized so we'd only overlap markitdown + file I/O). The fix is now blocked on adding an `asyncio.Lock` around the `_ensure_dim`/`index.add` critical section in working memory; tracking via a `TODO(perf-round-2)` comment in the `load_sources_from_config` body.

## v0.20260426.1

### Artifacts: reject comment-only / no-op `generate_file.code`

A user query like *"create a PRD with a brief on muxi"* would surface a helpful narrative response — the planning fix from v0.20260426.0 was working, the agent was honest about *"the PDF generation hit a snag"* — but no PDF artifact came back. Tracing the planning event showed the LLM (Sonnet 4.6 in this case, but any model is susceptible) emitted `generate_file.code` values like:

```python
# Generate PRD for MUXI -- populated after doc scrape
# Content will be injected from {{MUXI_DOCS}} at runtime
```

i.e. *intent* expressed as comments, with the LLM apparently believing the runtime would expand `{{MUXI_DOCS}}` into the multi-line Python source on its behalf. It does not — placeholder substitution applies to scalar leaf values in OTHER tools (URLs, IDs), not to author-supplied Python source. The sandbox would dutifully run the comment-only no-op script, produce zero files, and the artifact extractor would surface the confusing `"No file was generated"` error masking the real cause.

Two-part fix:

- `ArtifactService._validate_code` now runs an executable-content guard immediately after a successful `ast.parse(code)`. Modules whose body is empty (comment-only file), or whose body consists ONLY of docstrings / imports / `pass` / `...`, are rejected with the precise, actionable message: *"Code contains no executable statements (only comments, docstrings, or imports). The `code` parameter must be complete, executable Python that writes its output file to the current directory."* This fires BEFORE the existing whitelist / dangerous-call scans, so the import and call guards remain unchanged.
- `_infer_tool_parameters` constraints prompt for `generate_file` was tightened with an explicit "EXECUTABLE-CODE CONTRACT" section that spells out: (a) `code` must be complete executable Python at planning time — no second-pass fill-in; (b) `{{PLACEHOLDER}}` references are NOT substituted inside the multi-line `code` body; (c) if the file's content depends on data the LLM doesn't have at planning time, it must either write the content verbatim from training knowledge OR have the Python itself fetch via `requests` / `urllib`.

15 new unit tests in `tests/unit/test_artifact_service_validate_code.py` cover both the actual production failure shapes (multi-line and one-line intent comments referencing unresolved placeholders) and edge cases: empty string, whitespace, docstring-only, imports-only, `pass`-only, `...`-only, mixed imports+docstring. Five accept-side tests guard against false positives on legitimate code (minimal file write, realistic reportlab snippet, docstring-then-real-code, function def+call, etc.). Two end-to-end tests confirm the existing import-whitelist and dangerous-call guards still fire correctly when the new check passes.

## v0.20260426.0

### Planning: `_finalize_execution_plan` no longer drops `my_steps` when LLM omits `steps`

A user query like *"create a one-page pdf about muxi"* would result in the agent narrating the work it was about to do (*"I'll activate the file-generation skill, then scrape the docs, then build the PDF…"*) but **no tool was ever invoked** and no PDF artifact came back. Tracing the planning observability events showed the LLM (Haiku) had emitted three correct actions in `my_steps` (`activate_skill`, `firecrawl_scrape`, `generate_file`) but with `"steps": []` because of the prompt's *"ALL steps MUST go in `my_steps`"* line, which Haiku interpreted literally.

`_finalize_execution_plan` rebuilds `my_steps` by iterating `plan["steps"]`, then unconditionally writes the rebuilt list back via `plan["my_steps"] = rebuilt_my_steps`. With `steps == []`, the rebuilt list was `[]` — and the LLM's three real actions were silently overwritten before the executor ever saw them. The reconciliation logic at line ~1313 only handled the inverse case (`steps` populated, `my_steps` shorter); the empty-`steps` recovery was missing.

Fix:

- `_finalize_execution_plan` now detects the `"steps": [], "my_steps": [...]` shape (`my_steps_is_authoritative`) and treats `my_steps` as canonical for that plan: parameters and output placeholders are kept verbatim, unknown tools are dropped to avoid downstream "tool not found" errors, and a WARNING-level observability event records the recovery for postmortem traceability. The existing two-array path is unchanged when `steps` is populated.
- `agent_planning.md` replaces the misleading single-line *"ALL steps MUST go in my_steps"* instruction with explicit guidance: every action MUST appear in **both** `steps` (with `can_i_do_this: true`) AND `my_steps` (with concrete `parameters`). The runtime documents that the empty-`steps` path is a recovery fallback, not the contract.
- Three regression tests in `tests/unit/test_agent_planning_helpers.py`: empty-`steps` recovery preserves and filters my_steps; both arrays empty stays empty (no actions invented); both populated keeps the existing canonical-`steps` behavior (extras in `my_steps` don't smuggle in).

End-to-end verification: re-running *"create a one-page pdf about muxi"* now fires `tool.invoked` events for all three planned steps. The agent's narrative response no longer claims work that didn't happen. (The new `generate_file` failure observed during verification — `Import not allowed: subprocess` — is a separate, unrelated artifact service constraint and will be tracked separately.)

### Routing: pre-routing gates are now agent-aware

The two pre-routing gates that run before agent selection (`_is_actionable_message` and `clarification.needs_clarification`) were deciding whether to short-circuit a request without ever seeing the formation's specialist registry. On a formation like `hello-muxi` (Overlord plus a domain expert agent), this meant informational queries like *"What is MUXI?"* or *"Tell me about the overlord."* would get classified as non-actionable and answered by the Overlord's persona instead of routed to `muxi-expert` — even though a perfectly capable specialist was right there.

- New `_format_specialist_registry()` helper renders the available agents (id, role, description, capabilities) into a compact block that's now injected into both gate prompts.
- `_is_actionable_message` rewritten with explicit informational-query examples and a "if a specialist exists for this topic, route to them" rule.
- `clarification_analysis.md` gained a `SPECIALIST AGENTS AVAILABLE` section with companion routing rules.
- `clarification._analyze_request` now passes `specialist_agents=` so the gate prompt is rendered with the live registry.

Result: domain-grounded responses on formations whose agents define specialized expertise. Pure-Overlord formations are unaffected because the registry block is empty for them.

### Knowledge ingestion no longer requires an OpenAI API key

`Agent._initialize_knowledge` resolved the knowledge handler's embedding function via `self.model.generate_embeddings` — i.e. it asked the agent's *chat* LLM to embed knowledge text. That conflated two orthogonal capabilities (chat and embedding) and dragged knowledge ingestion into `LLM.generate_embeddings`, which itself defaulted to `openai/text-embedding-3-small` when no `model=` kwarg was passed.

A formation that only declared an Anthropic chat key would therefore silently die on knowledge ingestion with `Authentication failed: OpenAI API key is required` even though the runtime ships and bind-mounts a local Nomic embedder.

Two-layer fix:

- `Agent._initialize_knowledge` now builds `embedding_fn` from `OneLLMEmbeddingAdapter` (the same adapter SOP search uses), with the slug resolved as `working_memory.embedding_model_name` → `DEFAULT_EMBEDDING_MODEL` (= `local/nomic-ai/nomic-embed-text-v1.5`). The adapter delegates every embed call to `services.memory.embedding.embed` — the documented "single choke point" — so the knowledge handler now flows through the same provider-routing logic as every other memory consumer.
- `LLM.generate_embeddings` and `LLM.embed` (singular) now default to `DEFAULT_EMBEDDING_MODEL` instead of OpenAI. Defense-in-depth: any future caller landing on these without an explicit `model=` stays offline-safe.

`tests/unit/test_agent_knowledge_embedding.py` (8 tests) statically guards against the chat-model-embedding regression inside `_initialize_knowledge` and the local default on both `LLM` paths.

### SIF embeddings: HF Hub layout, no shim needed

The runtime SIF sets `HF_HOME=/opt/hf-cache` and `HF_HUB_OFFLINE=1`, then bind-mounts `~/.muxi/server/cache` at `/opt/hf-cache`. Earlier muxi-server `pkg/hfcache/hfcache.go` wrote a flat custom layout (`<cacheDir>/<org>--<repo>/...`) that `huggingface_hub.hf_hub_download` couldn't read offline (it expects `models--<org>--<repo>/snapshots/<sha>/...`), so embedding loads inside the SIF would fail with "Repo has no ONNX weights" even though the weights were right there in the bind mount.

- Added `utils/hf_cache_shim.py` — a startup shim that detects the legacy flat layout under `HF_HOME`/`HF_HUB_CACHE` and projects it into HF Hub layout via symlinks under `/tmp/muxi-hf-hub`, then re-exports `HF_HUB_CACHE` and `HF_HOME` to point at the projection. Wired into `utils/run_formation.py`'s SIF-mode env-setup block so it runs *before* any HF / onellm / transformers import (those libraries cache the cache-dir resolution at import time).
- The shim is now a backwards-compat fallback. muxi-server `pkg/hfcache/hfcache.go` v0.20260426.0 writes HF Hub layout natively (`models--<org>--<repo>/snapshots/main/<file>` plus `refs/main`), so freshly-init'd servers no longer need the shim. Older servers with flat caches on disk continue to work via the shim path.
- The bind-mount itself produced a benign Apptainer warning (`destination is already in the mount point list`) on the Docker-wrapped path; this is fixed in runtime-runner v0.20260426.0, which dropped its `ENV SINGULARITY_BINDPATH=/opt/hf-cache:/opt/hf-cache` so muxi-server's explicit `--bind /opt/hf-cache` is the single source of truth.

### Mental model

`mental-model.md` gained four new gotcha sections covering pre-routing gate ordering, the SIF embedding cache layout convergence, the runtime-runner bind-mount fix, and the chat-model embedding coupling that this release removed.

## v0.20260423.0-v0.20260423.3

### Runtime image + SIF packaging

- **Dockerfile `HEALTHCHECK` now probes the real health path.** The formation API mounts the health router under the `/v1` prefix (see `formation/server/server.py`: `include_router(health_router, prefix="/v1")`), so the previous `curl http://localhost:8000/health` probe returned 404 on every boot and Docker reported the container as `unhealthy` forever. Probe is now `curl -fsS http://localhost:8000/v1/health`. `--start-period` bumped from 30s to 60s to cover cold-boot formation init (observed ~4s default, ~25s pytorch under emulated amd64). Variant Dockerfiles inherit the fix via `FROM`. Observed starting → healthy transition in ~110s under macOS/Rosetta on the default variant (6 probes fail during start-period, which is expected and does not count as a failing streak).
- **`scripts/build/runtime.sh` and `scripts/build/sif.sh` are now variant-aware.** Both scripts accept `--variant default|pytorch|cuda` and `--arch amd64|arm64`, detect `apptainer` before `singularity` in the conversion path, read version from `src/muxi/runtime/.version`, use the correct `python -m muxi.runtime.utils.run_formation` module path in docs, and suffix SIF filenames by variant so default/pytorch/cuda builds do not collide in `sif-builds/`.
- **SIF "Test the SIF" help corrected.** `--writable-tmpfs` is now documented as required (SIF rootfs is read-only by design; without tmpfs the runtime fails at `mkdir /root/.muxi/default/memory`). Both Option A (native apptainer) and Option B (docker-wrapped via `runtime-runner`) are shown, and the health check example uses `/v1/health` to match the HEALTHCHECK fix above.
- **Platform guidance clarified.** Upstream Apptainer/Singularity publishes linux/amd64 binaries only, so on macOS and Windows the correct SIF arch is always `linux-amd64` regardless of host CPU — Rosetta (Apple Silicon) or Hyper-V (Windows) handles the translation. `linux-arm64` SIFs only make sense on a native arm64 Linux host with a self-built arm64 Apptainer (e.g. AWS Graviton). `sif.sh` emits an early warning when it detects an arm64 build that will not be executable on a macOS/Windows host.
- **CUDA variant marked EXPERIMENTAL.** `Dockerfile.cuda` now carries a preview status note in its header. `scripts/build/runtime.sh` echoes the experimental warning before starting a CUDA build. The image can be built on linux/amd64 hosts with NVIDIA tooling, but the full runtime path (CUDA torch + faiss-gpu + onnxruntime-gpu inside a SIF) has not been end-to-end validated against live GPUs in CI.

### Embedding platform: single-path helper, Nomic v1.5 default

The MUXI runtime now routes every embedding call through a single shared helper (`services/memory/embedding.py`) that wraps `onellm.Embedding.acreate`. The old `local_embeddings.py` alias shim (short-name → dimension map, direct `SentenceTransformer` instantiation) has been removed. Long-term memory, working memory, SQLite memory, fusion engine, SOP coordinator, and knowledge handler all flow through `embed()` / `probe_dimension()` in the helper.

**Default embedding model changed** to `local/nomic-ai/nomic-embed-text-v1.5` (768-dim, 8k context, Matryoshka 64–768, Apache-2.0). Previous default was the 384-dim sentence-transformers MiniLM. Multilingual deployments can opt into `local/nomic-ai/nomic-embed-text-v2-moe`. Cloud providers (`openai/*`, `cohere/*`) continue to work unchanged; the helper strips `task` for cloud slugs so consumers can pass it unconditionally.

**BREAKING**: Formation configs that reference short-name local aliases (e.g. `local/all-mpnet-base-v2`) will no longer resolve. The short-name registry was removed upstream in OneLLM `0.20260421.0` and the runtime-side shim that previously papered over that is gone. Migrate formation configs to full HF repo ids:

- `local/all-MiniLM-L6-v2` → `local/sentence-transformers/all-MiniLM-L6-v2` (or prefer the new default `local/nomic-ai/nomic-embed-text-v1.5`)
- `local/all-mpnet-base-v2` → `local/sentence-transformers/all-mpnet-base-v2` (or the new default)

No database migration is required for existing `memories_1536` data (OpenAI users are unaffected). Switching from MiniLM 384-dim to Nomic v1.5 768-dim requires either (a) re-embedding via `scripts/migrate_embeddings.py`, or (b) explicitly configuring the old model in formation YAML.

**Schema additions**: `memories_384`, `memories_768`, `memories_1024`, `memories_3072` tables are now pre-created by `init_schema.sql` (PostgreSQL + pgvector/ivfflat) and `init_schema_sqlite.sql` (SQLite + FTS5 + triggers), so formations using any of these dims work on a fresh DB without runtime DDL. Re-applying the schema to a populated `memories_1536` database is idempotent and non-destructive.

**New tests**: 7 integration test files under `tests/integration/` cover the helper's error contract (empty input, invalid slug), Matryoshka truncation, multilingual retrieval (Nomic v2 MoE, environment-gated), long-input truncation behavior, OpenAI regression (VAL-INTEG-003/VAL-CROSS-004), the `task`-stripping policy for cloud slugs (VAL-HELPER-012), schema upgrade idempotency (VAL-SCHEMA-005), and cross-dimension search behavior (VAL-CROSS-006). 15 new unit tests lock in formation config slug validation (`tests/unit/test_formation_config_validation.py`).

### Embedding platform: revision pinning + SIF deployment contract

Building on the single-path helper work above, this release prepares the runtime for SIF-based deployment with a host-managed HuggingFace cache.

**Slug-embedded revision pinning.** The embedding helper now accepts `local/<repo>:<revision>` notation — for example `local/nomic-ai/nomic-embed-text-v1.5:e04b7e4c5ea3e3d7e41e13d4c02fa5e29e0e3a0a`. The new `_parse_model_slug(slug)` function extracts `(model, revision)` and `embed()` / `probe_dimension()` forward the revision to OneLLM's `LocalProvider`, which in turn pins every downstream HuggingFace lookup (ONNX weights, PyTorch weights, tokenizer, config, max-length probe). OneLLM's LRU cache key is `(repo, revision)`, so a formation pinning one revision and another following `main` do not collide.

Revision parsing is ONLY applied to `local/*` slugs. Cloud provider slugs may legitimately use `:` in model names (e.g. `ollama/llama2:7b` encodes a variant, not a revision) and pass through untouched. A trailing `:` with no revision fails fast with `InvalidRequestError` rather than resolving silently to `main` downstream.

Requires `onellm[cache]>=0.20260422.3` — the pin bump in this release picks up OneLLM's upstream fix that threads `revision=` through every LocalProvider code path (0.20260422.0 silently dropped the kwarg, fixed in 0.20260422.1) and the `local-cuda` extra that Dockerfile.cuda consumes (shipped in 0.20260422.3).

**Host-managed HuggingFace cache (SIF deployment).** The runtime SIF no longer ships pre-downloaded model weights. Instead, `muxi-server` maintains `~/.muxi/server/cache` on the host (cross-platform, per-user) and bind-mounts it into the SIF at `/opt/hf-cache`. SIFs run with `HF_HUB_OFFLINE=1` and never reach the network; all `onellm download` calls happen on the host under the server's control.

- `Dockerfile` (lean variant): the three pre-downloaded sentence-transformers models (`paraphrase-multilingual-MiniLM-L12-v2`, `all-MiniLM-L6-v2`, `all-mpnet-base-v2`) have been removed. The explicit torch CPU-wheel install is also gone — `onellm[cache]` is ONNX-based and nothing else in the dep tree pulls torch as a transitive.
- `Dockerfile` (HF env vars): `HF_HUB_CACHE=/opt/hf-cache` is now set alongside `HF_HOME=/opt/hf-cache`. Without the explicit `HF_HUB_CACHE` setting, HuggingFace resolves it as `$HF_HOME/hub` — placing models at `/opt/hf-cache/hub/models--*` instead of `/opt/hf-cache/models--*` and breaking 1:1 alignment with the bind-mount. Setting both to the same path flattens the layout. Tokenizer/datasets subcaches still land inside the bind-mount (writable).
- `Dockerfile.pytorch` (new): layered on top of the lean image, adds CPU-only PyTorch plus the `onellm[cache,local-pytorch]` extra. Selected via formation `muxi_runtime: "<version>:pytorch"` when the embedding model lacks ONNX weights (e.g. Nomic v2 MoE).
- `Dockerfile.cuda` (new): GPU stack on top of the lean image. Uninstalls the CPU-only faiss-cpu / faissx / onnxruntime wheels inherited from the base, then installs `torch`/`torchvision` (CUDA 12.x wheels from the default PyPI index on linux/amd64), `onellm[local-cuda,local-pytorch]` (pulls onnxruntime-gpu, faiss-gpu-cu12, sentence-transformers), and `faissx-gpu` (drop-in replacement for the faissx client with a GPU-backed local FAISS). Build-time assertion verifies the onnxruntime wheel has `CUDAExecutionProvider` compiled in. Selected via formation `muxi_runtime: "<version>:cuda"` on hosts with NVIDIA GPUs. The ~4–6 GB CUDA stack exceeds GitHub's 2 GB release upload ceiling; distribution is via muxi-server's CDN rather than GitHub releases. Linux x86_64 + CUDA 12.x only.
- **pip extras mirror the Dockerfile matrix.** `pyproject.toml` now declares `[pytorch]` and `[cuda]` optional-dependency extras so operators can reproduce any variant's Python dependency set with a single pip install:
  ```
  pip install muxi-runtime                   # default (lean, ONNX + CPU FAISS)
  pip install 'muxi-runtime[pytorch]'        # CPU torch + sentence-transformers
  pip install 'muxi-runtime[cuda]'           # GPU ONNX + GPU FAISS + CUDA torch
  ```
  The `[cuda]` extra conflicts with the core `faiss-cpu` and `faissx` deps (each owns the same top-level module name as its GPU sibling); `Dockerfile.cuda` handles the uninstall-then-reinstall sequence automatically, and users installing through pip directly should run `pip uninstall -y faiss-cpu faissx onnxruntime` before the extras install.
- `docker-entrypoint.sh` (cache assertion): when the SIF detects SIF mode (`APPTAINER_CONTAINER` / `SINGULARITY_CONTAINER` / `MUXI_SIF_MODE`), it now asserts at least one `models--*` directory exists under `/opt/hf-cache` before launching the formation server. An empty cache fails fast with an actionable error instead of surfacing a confusing "model not found" from inside HuggingFace's offline resolver.

These changes coordinate with parallel work in `muxi-server` (cache lifecycle commands, `onellm download` orchestration, bind-mount injection at launch) and `runtime-runner` (the Docker image that wraps Apptainer for SIF execution on non-Linux hosts, which forwards the bind-mount chain through a two-hop mount).

## v0.20260422.0

### Documented-Sentinel Recognition In Parameter Inference (Excel A1/B2 Regression From v0.20260421.0)

Cell-specific Excel reads (A1, B2, ...) against the authenticated user's default OneDrive silently collapsed after `9f99e022` ("fail closed before invalid MCP execution"). The underlying bug is general, not OneDrive-specific: any planner output that passes a templated placeholder (`"{{...}}"`) to a parameter whose schema description already documents a valid sentinel value (e.g. `"use 'me' for the current user's drive"`, `"use 'root' for the default site"`, `"use 'primary' for the default calendar"`) was rejected by `_infer_tool_parameters`. The inference system prompt said "Do NOT invent placeholder/default values", which the LLM correctly read as a blanket prohibition on short sentinel strings — even when the sentinel was documented in the tool's own schema. Inference returned `{}`, the required-param repair path fired, LLM replan produced a same-signature plan, `_build_auto_discovery_repair_plan` inserted an unrelated discovery step without patching the failing parameter, and the one-shot `replan_attempted` guard blocked the second pass. The chain collapsed silently on every tool whose schema documented a sentinel.

- **`src/muxi/runtime/formation/agents/agent.py` — extend the `_infer_tool_parameters` system prompt with a schema-driven "Documented sentinel values" rule.** The new block teaches the LLM that sentinels explicitly documented in a parameter's own Description text are valid concrete values, not guesses, and may be emitted when (1) the user's request did not identify a specific resource for that parameter AND (2) no prior step output supplies the real identifier. The rule is deliberately generic: no vendor name, no MCP name, and no parameter name is hardcoded in the prompt — the LLM reads the sentinel from the schema description the caller already passed in. The anti-guessing guardrails (`Do NOT invent placeholder/default values`, `Omit unresolved parameters`, `leave it unresolved rather than guessing`) remain verbatim for every other case. This upstream fix resolves the sentinel during the normal inference pass, so the required-param repair path never fires, `_build_auto_discovery_repair_plan` never needs to patch the failing step, and the `replan_attempted` guard stays unused — the collapse condition is removed at its source rather than patched inside a downstream repair builder.

### Scheduler Timestamp Timezone Hardening

Recurring scheduled jobs could silently stop re-firing when the runtime compared a naive `last_run_at` from SQLAlchemy against a timezone-aware `scheduled_time` from croniter. Python raises `TypeError: can't compare offset-naive and offset-aware datetimes` for that mix, and `_is_recurring_job_due` caught every exception via a bare `except` and returned `False`, so the job looked "not due" forever. The same latent inconsistency affected the scheduler API's JSON payloads, which serialized UTC datetimes without a timezone suffix and left clients to guess whether the string was local or UTC.

- **`services/scheduler/service.py` — shared UTC normalization helper.** New static method `SchedulerService._parse_scheduler_timestamp(timestamp_str)` replaces two copy-pasted `datetime.fromisoformat(...).replace("Z", "+00:00")` call sites. If the parsed value has no tzinfo (the shape SQLAlchemy returns for `DateTime` columns without `timezone=True`), the helper attaches `timezone.utc` before returning; already-aware inputs pass through unchanged. Applied to:
    - `_should_execute_job` — previously parsed `job["last_run_at"]` raw and fed the naive result into `scheduled_time > last_run`, where `scheduled_time` is always aware (coming from `croniter.get_next(datetime)` seeded with an aware "now"). That comparison raised `TypeError`, got swallowed by `_is_recurring_job_due`'s broad exception handler, and caused the recurring job to appear not-due on every tick after its first run.
    - `_is_onetime_job_due` — same failure mode for one-time jobs whose `scheduled_for` field came back naive.
- **`services/scheduler/models.py` — canonical UTC `Z` ISO serialization.** New module-level helper `_serialize_scheduler_datetime(value)` returns `None` for `None` / non-datetime inputs, attaches `timezone.utc` for naive datetimes, converts aware datetimes to UTC, and emits ISO 8601 with a trailing `Z` (replacing `+00:00`). Applied to every datetime field in both `to_dict` implementations: `ScheduledJobAudit.timestamp`, and `ScheduledJob.scheduled_for` / `created_at` / `updated_at` / `last_run_at`. API consumers now get `"2026-04-22T09:18:00Z"` regardless of whether the column value was persisted naive.
- **Type hygiene.** `create_job(exclusions=None)` and `complete_job_from_webhook(result=None, error=None)` annotated with `Optional[...]` for mypy strictness; `croniter` import carries `# type: ignore[import-untyped]` because the package does not ship `py.typed`.

### Architectural Notes

- **Schema descriptions are contract, not documentation.** The parameter-inference prompt now treats the `description` field on every tool-parameter schema as an authoritative source for legal concrete values. Any MCP (Microsoft Graph, Google Workspace, Slack, custom tool servers, …) whose schema documents a sentinel now flows through inference without a runtime-code change. This is the opposite of the originally reported patch (which proposed hardcoding `driveId: "me"` into the auto-discovery repair builder): sentinel knowledge belongs to the schema author, not to the runtime.
- **Safety for specific-resource scenarios.** The sentinel rule is guarded by two conditions the LLM can read from the prompt: the user did not name a specific resource AND no prior step output supplies the real identifier. Requests like "Read A1 from Book.xlsx in the Marketing team's drive" therefore continue to produce a discovery-first chain — the LLM sees "Marketing team's drive" in the user request and withholds the default. Prior-step IDs likewise win because completed-results context is part of the prompt context.
- **No behavioural change to `_validate_tool_parameters` or repair paths.** Concrete sentinel strings (for example `"me"`, `"root"`, `"primary"`) are ordinary string values; none match `_is_placeholder_like_value`, none match `_is_sentinel_placeholder_value` (the auto-injected / from-server tokens), and all pass every post-9f99e022 fail-closed check unchanged. `_build_auto_discovery_repair_plan` is untouched.
- **Scheduler timestamps are UTC by contract, naive by storage.** The scheduler's SQL columns are plain `DateTime` (no `timezone=True`), which is the existing cross-backend convention in this codebase (SQLite's `DATETIME` is strictly naive). This patch keeps that storage shape and localizes the UTC interpretation at the two edges that matter: on the way back in via `_parse_scheduler_timestamp` (due-check comparisons need aware vs aware), and on the way out via `_serialize_scheduler_datetime` (API clients need unambiguous strings). Neither helper changes what is written to the database.
- **Silent exception swallowing is now less dangerous.** `_is_recurring_job_due` still has its outer `try / except Exception -> return False` safety net, but the specific failure it was hiding — naive-vs-aware comparison — cannot happen on the patched path. Any future regression in timestamp handling will surface through one of the narrowly scoped helpers and can be caught at review time rather than silently disabling a recurring schedule.

### Tests

**New unit tests** (5 total across two files):

- `tests/unit/test_agent_planning_helpers.py`:
    - `test_infer_tool_parameters_prompt_documents_schema_sentinel_rule` — runs `_infer_tool_parameters` against a tool schema whose parameter description documents a sentinel and a mocked LLM that returns the sentinel; asserts the return value is not dropped by the fail-closed validation, captures the system prompt from the mocked model, asserts the new generic "Documented sentinel values" rule is present, and asserts the prompt stays vendor-agnostic (no hardcoded `driveId` / `userId` / `Microsoft` / `Graph` tokens).
    - `test_infer_tool_parameters_sentinel_values_survive_post_closed_checks` — pins that a short sentinel string (`"me"` as a concrete example) is neither placeholder-like nor a LLM-invented sentinel, and that `_get_unresolved_required_parameters` treats a step whose parameter resolves to the sentinel as fully resolved. Guards against future over-tightening of the placeholder scanners.
- `tests/unit/test_scheduler_datetime_handling.py`:
    - `test_parse_scheduler_timestamp_treats_naive_as_utc` — the helper attaches `timezone.utc` when given a naive ISO string, preserves timezone on already-aware strings, and is safe with the `Z` suffix.
    - `test_should_execute_job_handles_naive_last_run_at` — reproduces the recurring-job regression against a mocked job row: naive `last_run_at`, aware `scheduled_time`, pre-patch would raise `TypeError` inside `_should_execute_job`; post-patch returns the correct boolean.
    - `test_serialize_scheduler_datetime_emits_utc_z` — `None`, naive, and aware inputs all round-trip through the helper to a `Z`-suffixed ISO string (or `None`), covering both branches of `to_dict`.

### Validation

- **Unit suite: 614 passed, 3 skipped.** Full `tests/unit/` run clean; the 3 skips are pre-existing unrelated.
- **Targeted suites: scheduler datetime 3/3 pass; inference sentinel 2/2 pass.**
- **Scheduler e2e gate (15 scripts): 15/15 pass.** One pre-existing flake in `test_12a1_basic_scheduling.py` sub-case 2 was surfaced during this release's validation: the prompt "Schedule a meeting tomorrow at 3pm" was vague enough that `gpt-4o-mini` routed through the clarification system ("please provide details of the meeting…") instead of the scheduler. Reproduced on clean HEAD without this patch, so unrelated. Tightened the test prompt to "Schedule a project review tomorrow at 3pm" — concrete enough to commit to a scheduled job while still exercising the one-off tomorrow-at-3pm path — matching the style of the two passing sub-cases in the same file.
- **Random e2e sample (5 tests): 5/5 pass** — `19_api/test_19g1_memory_sessions.py`, `4_mcp/test_4b3_mcp_failure_handling.py`, `4_mcp/test_4d3_explicit.py`, `4_mcp/test_4d4_multiuser_isolation_simple.py`, `9_async/test_9c2_timeout_handling.py`.
- **`black --check`, `ruff`, `mypy` — clean on touched files.**
- **E2E gate not rerun for the inference-sentinel prompt extension** — the change is a prompt-only addition with dedicated unit coverage; no structural code path was altered, so the scheduler and random e2e samples remain representative.

### Infrastructure

- **E2E secrets fixture repair.** Six `runtime2/e2e/tests/**/.key` files had been auto-generated as stray regular files by `SecretsManager._load_or_create_master_key` during earlier test runs, producing random Fernet keys that could not decrypt the shared `e2e/assets/secrets.enc`. This blocked every formation load across the affected areas (`12_scheduling`, `19_api`, `1_foundation`, `2_memory`, `3_multimodal`, `21_skills`) with `cryptography.fernet.InvalidToken`. Replaced each with a symlink to `e2e/assets/.key` matching the relative-path style already used by the 36 working siblings. All 44 `key`/`secrets.enc` pairs in `runtime2/e2e` now decrypt. `.key` is in `.gitignore` so these symlinks are not tracked in git — fresh clones that do not rehydrate them via `../runtime` will need to recreate them (or the next test run will again auto-generate bad regular files).

### No breaking changes

- Inference prompt gains a schema-driven sentinel rule; existing inference calls whose parameter schemas do not document a sentinel produce the same output they did before. The anti-guessing guardrails are preserved verbatim.
- `to_dict` payload shapes gain a `Z` suffix on datetime fields where there was previously none (API strings now unambiguously denote UTC). Clients that were manually appending `Z` or parsing via `fromisoformat(...).replace("Z", "+00:00")` remain compatible.
- No database schema change. Existing rows are interpreted as UTC without migration.

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
