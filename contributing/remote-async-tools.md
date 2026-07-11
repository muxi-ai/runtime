# Remote Async Tools (`watch_job`)

How MUXI formations handle MCP-reachable work that outlives a chat turn:
image/video generation, long renders, batch jobs. The service submits
fine (a normal sync tool call returning `{job_id, status: "processing"}`)
but nothing ever collects it -- the turn ends, nobody polls, the
conversation forgets the job. The built-in `watch_job` tool closes that
loop.

MUXI never classifies tools as async. Async-ness is a property of the
**response**, not the tool: a well-designed server answers inline when
fast and returns a job handle when slow -- same tool, both behaviors,
decided at call time. The component that recognizes "this response is a
job handle, not an answer" is the agent, contextually, guided by a
bundled SOP fragment.

## The four long-running patterns

| Long-running pattern | Answer |
|---|---|
| Slow-but-sync tool call | Existing per-tool MCP timeout config -- nothing new |
| Job-id + poll (MCP-native) | **`watch_job` built-in** (this document) |
| Webhook, app-level (Stripe-style) | Triggers: register `POST /v1/triggers/<id>` in the vendor dashboard |
| Webhook, per-call (Replicate-style) | Triggers: pass the trigger URL as a tool argument |

Only the second row is new code. The webhook rows are already shipped as
triggers -- recipes below.

### Pattern 1: slow-but-sync

The tool blocks for 20-60 seconds and then answers inline. No job handle,
no watching -- just give the server room to breathe with its per-server
timeout in `mcp/<server>.yaml`:

```yaml
# mcp/renderer.yaml
schema: "1.0.0"
id: renderer
description: "Renders diagrams (slow but synchronous)"
type: command
command: "npx"
args: ["-y", "some-render-mcp"]
timeout_seconds: 90        # give the sync call room; nothing else needed
```

### Pattern 2: job-id + poll (`watch_job`)

The tool answers immediately with `{job_id, status}` and the service
exposes a status tool. This is the `watch_job` case -- everything below
this table.

### Pattern 3: webhook, app-level (Stripe-style)

The vendor POSTs every event for your account to one URL you register
once in their dashboard. That URL is a MUXI **trigger**:

1. Create `triggers/render-events.md` in the formation (a trigger with a
   `parse:` block mapping the vendor payload to a message).
2. Register `https://<your-runtime>/v1/triggers/render-events` in the
   vendor's webhook settings.
3. Events re-enter the conversation through the trigger pipeline --
   middleware, RBAC, and delivery included. No polling at all.

### Pattern 4: webhook, per-call (Replicate-style)

The submit tool accepts a callback URL argument. Pass a trigger URL as
that argument -- the agent can do this itself when the tool's schema
documents the parameter:

```
create_prediction({"model": "...", "input": {...},
                   "webhook": "https://<your-runtime>/v1/triggers/render-events"})
```

Same trigger machinery as pattern 3; the URL just travels per call. When
the service offers webhooks, prefer them over watching -- push beats
poll. `watch_job` is for the (common) MCP-native case where the service
only offers a status tool.

## The `watch_job` tool

Registered automatically for every agent whenever the formation declares
MCP servers (zero config). The agent calls it when a tool returns a job
handle:

```json
watch_job({
  "tool": "image-gen.check_status",   // any MCP tool visible to the caller
  "args": {"id": "job_abc123"},       // arguments for each poll
  "done_when": {"path": "$.status", "in": ["succeeded", "failed", "canceled"]},
  "result": "$.output",               // optional selector; default: full final body
  "label": "logo render"              // optional; shows on /jobs
})
```

Returns immediately (`watch_job` is always asynchronous; there is no
blocking mode and none will be added):

```json
{"success": true, "job_id": "wch_9f2...", "status": "watching",
 "status_url": "/jobs/wch_9f2..."}
```

- `tool` accepts `server.tool`, `server__tool`, or a bare tool name
  (resolved against the servers the calling user can see).
- `done_when` is evaluated **mechanically** -- a dot-path selector plus
  `equals` or `in`. No LLM in the poll loop; polls cost zero tokens.
  Include every terminal state the service can report, not just success.
- There are deliberately **no interval/timeout arguments**: cadence and
  deadline are formation configuration (below), because numeric knobs
  are exactly what LLMs pick badly.

Poll semantics:

- First poll after one `interval`; fixed cadence thereafter (no backoff).
- Terminal condition met -> extract `result` -> the outcome re-enters the
  conversation (`route_class: watch`, same middleware + RBAC pipeline as
  heartbeats and coding delegations) with the payload wrapped in
  untrusted-content fencing, and the agent's summary is delivered via the
  proactiveness notification router (user's channel > formation default).
- Deadline reached -> the watch resolves as `timed_out` and re-enters
  with that status; nothing silently vanishes.
- `max_consecutive_failures` consecutive poll errors -> the watch fails
  with the last error, fenced.
- Cancellation via `/jobs cancel <id>` stops polling; no re-entry.
- Runtime restart/shutdown -> active watches are marked `orphaned`
  (poll loops carry the user's request-scoped permission context, which
  is never persisted).

Every poll executes the status tool **as the watching user**: the
request's resolved GBAC permissions are captured at watch creation and
restored around each poll. A user who cannot call `check_status` cannot
watch it -- rejected at creation, and fail-closed per poll if permissions
change mid-watch.

## Formation configuration

Zero-config by default: `watch_job` registers whenever the formation has
MCP servers, with conservative clamps. An optional block under `mcp:`
adjusts them (it configures behavior *over* MCP tools, so it lives with
them):

```yaml
mcp:
  watch:                        # optional; all fields optional
    interval: 30                # THE poll cadence (seconds) -- not agent-pickable
    timeout: 7200               # THE watch deadline (seconds)
    max_concurrent: 10          # active watches per user (formation default)
    max_consecutive_failures: 3
  servers:
    - image-gen
```

There is no `enabled:` key. The tool grants no new capability (it can
only call MCP tools the caller could already call, under the caller's
own permissions, with zero-token deterministic polls), so the only
switch is the one-line escape hatch:

```yaml
mcp:
  watch: false                  # removes the watch_job tool entirely
  servers: [...]
```

Unknown keys and invalid values fail at formation load, never at watch
time.

### Group-level quota override

Group templates may raise (or lower) the per-user watch quota, mirroring
the formation shape so overrides look like the thing they override:

```yaml
# groups/power-users.yaml
mcp:
  watch:
    max_concurrent: 25          # overrides the formation default for members
```

A user in multiple groups gets the **highest** of their groups' values
(grants are additive -- the same semantics as every other GBAC list); no
group value = formation default. This quota governs watches only.

## The recognition SOP fragment

A bundled SOP fragment is appended to every agent's instructions whenever
`watch_job` registers (default ON, behaviorally invisible until a tool
returns a job-shaped response):

> When a tool responds with a job identifier and a non-terminal status
> instead of a result, call `watch_job` with the service's status tool
> and a `done_when` matching its terminal states, then tell the user the
> work is underway and that you will report back. Do not repeatedly
> re-call the original tool.

Editable/removable like any SOP: a formation-local `sops/watch_job.md`
shadows the bundled text; an **empty** `sops/watch_job.md` removes the
fragment while keeping the tool.

## Worked example: image generation end to end

An image service exposes `submit` (returns `{"job_id": "...", "status":
"queued"}`) and `check_status` (returns `{"status": "...", "output":
"..."}`, flipping to `succeeded` when the render finishes).

Formation:

```yaml
mcp:
  watch:
    interval: 15
    timeout: 900
  servers:
    - image-gen

agents:
  - id: assistant
    name: Assistant
    description: Generates images on request
    default: true
```

The conversation:

1. **User:** "Generate a logo of a fox reading a newspaper."
2. The agent calls `image-gen.submit(...)` -- an ordinary sync tool call
   -- and gets `{"job_id": "job_42", "status": "queued"}`.
3. The SOP fragment kicks in: the agent recognizes the job-shaped
   response and calls

   ```json
   watch_job({
     "tool": "image-gen.check_status",
     "args": {"job_id": "job_42"},
     "done_when": {"path": "$.status", "in": ["succeeded", "failed"]},
     "result": "$.output",
     "label": "fox logo"
   })
   ```

4. **Agent:** "The image service is on it -- I'll monitor progress and
   let you know." The turn ends. `/jobs` now lists the watch.
5. The runtime polls `check_status` every 15 seconds under the user's
   own permissions. Poll 4 returns `{"status": "succeeded", "output":
   "https://cdn.example/fox.png"}` -- `done_when` matches, `$.output` is
   extracted.
6. The result re-enters the conversation (fenced as untrusted data) and
   the agent's summary reaches the user through their notification
   channel: "Your fox logo is ready: https://cdn.example/fox.png".

If the render hangs past 900 seconds, step 6 happens with status
`timed_out` instead -- the user learns the job stalled.

## Observability

Validated events, following the `delegation.*` set: `watch.started`,
`watch.poll` (debug tier, one per poll), `watch.completed`,
`watch.failed`, `watch.timed_out`, `watch.cancelled`, `watch.orphaned`.
Event data carries the job id, server, tool, and poll count -- never
poll bodies or credentials.

## What this is not

- **Not an MCP protocol extension** -- no new transport, no push channel;
  submit and poll are ordinary sync tool calls.
- **Not a webhook framework** -- webhooks stay triggers (patterns 3-4).
- **Not a task queue** -- watches poll *external* systems; MUXI-internal
  background work stays on the existing tracked-jobs machinery.
- **Not a classifier of tools** -- MUXI holds no opinion about which
  tools are async; that knowledge lives in the agent's judgment per
  response.
