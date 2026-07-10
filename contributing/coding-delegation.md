# Coding-Agent Delegation

How MUXI formations hand coding tasks to external **headless coding CLIs**
(claude-code, droid, ...) as fire-and-collect background work.

A formation declares a top-level `coding:` block. That registers one
built-in tool, `delegate_coding`, which spawns the configured CLI as a
tracked subprocess and returns a job handle immediately -- the chat turn
never blocks. When the run finishes, the result re-enters the conversation
through the same middleware + RBAC pipeline heartbeats and scheduled jobs
use (`route_class: delegation`), and the agent's summary is delivered via
the proactiveness notification router when one is configured. Running
tasks are visible in the built-in `/jobs` command.

MUXI ships the mechanism only:

- **Adapters are declarative content.** Bundled dormant templates per tool
  (inert until `coding.client:` references one by name), formation-local
  shadowing via `coding/<name>.yaml`, inline definition as escape hatch --
  the same convention as channel transformer templates.
- **Installation, auth, and sandboxing are yours.** MUXI fails fast at
  formation load if the binary is absent and contains zero install/auth
  logic. Your sandbox and your safety flags (via `extra_args`) are your
  setup.
- **Vendor taxonomies are not modeled.** Permission modes, safety levels,
  and model names pass through opaquely.

## Ready-to-paste formation blocks

Each block below is complete and working -- copy it into `formation.yaml`
and edit. Bundled templates today: `claude-code` and `droid`. (`opencode`
and `pi` templates ship in a later phase; their blocks will slot into this
list the same way.)

### claude-code

Prerequisite: install the Claude Code CLI and authenticate it
(`claude login` or `ANTHROPIC_API_KEY`) -- your responsibility, MUXI only
checks the binary exists.

```yaml
coding:
  client: claude-code            # bundled adapter template
  model: sonnet                  # alias (sonnet/opus/haiku) or full model name
  workdirs: ["./workspace"]      # roots must exist; runs get a fresh subdir each
  cleanup: delete                # delete (default) | keep (debugging)
  timeout: 30m
  max_concurrent: 3
  groups: []                     # empty/absent = every group may delegate
  extra_args:
    # Vendor permission surface, passed through verbatim. Pick YOUR policy:
    - "--permission-mode"
    - "acceptEdits"
    # or: ["--dangerously-skip-permissions"] in a sandboxed environment
    # also useful: --allowedTools/--disallowedTools, --max-turns, --max-budget-usd
  env:
    # The ONLY place ${{ secrets.* }} resolves (argv is ps-visible; env is not).
    ANTHROPIC_API_KEY: "${{ secrets.ANTHROPIC_API_KEY }}"
```

### droid (Factory)

Prerequisite: install the droid CLI and authenticate it (`droid` login
flow or `FACTORY_API_KEY`) -- your responsibility, MUXI only checks the
binary exists.

```yaml
coding:
  client: droid                  # bundled adapter template
  model: claude-sonnet-5         # vendor ids; custom:-prefixed for custom models
  workdirs: ["./workspace"]
  cleanup: delete
  timeout: 30m
  max_concurrent: 3
  groups: []
  extra_args:
    # droid's default autonomy is READ-ONLY. A formation that should edit
    # files needs --auto medium; git push needs --auto high.
    - "--auto"
    - "medium"
    # or: ["--skip-permissions-unsafe"] in an isolated container
  env:
    FACTORY_API_KEY: "${{ secrets.FACTORY_API_KEY }}"
```

## How it behaves

### The tool

`delegate_coding(prompt, workdir?, model?, continue_job_id?)` -- always
asynchronous. It returns `{"job_id": ..., "status": "started"}` at once;
there is no synchronous mode. `prompt` goes to the CLI verbatim (context
injection is the calling agent's job). `workdir` selects one of the
declared roots (default: the first). `model` opaquely overrides
`coding.model` per call.

### Disposable workdirs; git is the persistence layer

Every delegation runs in a fresh `<root>/<user_id>/<request_id>` directory
as subprocess cwd -- never the root itself. `cleanup: delete` (default)
removes it when the job reaches a terminal state; a TTL sweep removes
stray directories left by crashed runs. Nothing durable should live there:
ad-hoc tasks need nothing durable, new projects are git-inited and pushed
by the tool, existing projects are cloned/coded/push-branched within the
run. Consequently a resumed session gets a fresh directory --
conversational continuity comes from the vendor session id, file
continuity comes from git (have the continuation prompt re-clone/pull its
branch). Do not put the tool's own cwd flags (droid `--cwd`, worktree
flags) in `extra_args`; MUXI sets the cwd and rejects those flags at load.

### Sessions and continuation

The vendor session id is persisted on the tracked job (MUXI-generated for
claude-code and droid; captured from output for tools that assign their
own). To continue a task -- including answering a question a run ended
with -- call `delegate_coding` again with `continue_job_id: <job id>`;
MUXI replays the stored session id. Agents never see vendor session ids.

### Completion re-entry and escalation

Headless CLIs never block mid-task: a run that needs human input ends its
turn with the question as its final message. On completion the runtime
synthesizes an internal request into the originating session
(`route_class: delegation`, full middleware + RBAC pipeline); the agent
summarizes the outcome (or relays the question), and the reply is
delivered via the notification router (user-preferred channel >
`proactive.default_channel` > async webhook). The user's answer resumes
the session via `continue_job_id`.

### /jobs

Coding tasks appear in `/jobs` alongside scheduled jobs, ownership-scoped.
`cancel` kills the delegation's whole process group (the session id is
retained, so the task stays resumable); `logs` shows the job's activity
trail; `pause`/`resume` are not supported for coding tasks -- a one-shot
headless run has no meaningful pause.

### Fail-fast load validation

All of these fail the formation load, never a delegation: unknown
client/adapter schema errors, binary not on PATH, missing workdir roots,
`groups:` entries with no matching `groups/` file (when RBAC is active),
bad `output`/`cleanup`/`timeout` values, and any `${{ secrets.* }}`
reference outside `env:` (`extra_args` especially -- the error points at
`env:`). No `coding:` block means nothing is constructed and no tool is
registered.

## Shadowing and the inline escape hatch

To pin different flags (vendor releases drift), copy a bundled template
into your formation as `coding/<name>.yaml` -- the local file shadows the
bundled one -- or define the adapter inline:

```yaml
coding:
  command: "droid"
  args:
    base: ["exec", "--output-format", "json"]
    prompt: ["{prompt}"]           # or the literal string "stdin"
    session: ["--session-id", "{id}"]   # one idempotent create-or-resume flag
    # or a distinct pair (claude style):
    # session_new: ["--session-id", "{id}"]
    # session_resume: ["--resume", "{id}"]
    model: ["--model", "{model}"]
  output: json                     # stream-json | json | text
  parse:
    result: "$.result"
    session_id: "$.session_id"
  workdirs: ["./workspace"]
```

Command assembly is an exec array (never a shell): `command` + `args.base`
+ model fragment (when a model is set) + session fragment + `extra_args` +
prompt (or stdin).

## Observability

`delegation.started`, `delegation.progress` (coarse vendor event type,
stream-json only), `delegation.completed`, `delegation.failed`,
`delegation.timed_out`, `delegation.cancelled`, `delegation.orphaned`.
Events carry the job id, adapter name, and delegation directory -- never
env values. `/jobs logs` reads the same trail.

## What MUXI deliberately does NOT do

No vendor permission/safety/model modeling, no tool installation or auth
flows, no sandboxing beyond disposable workdirs under declared roots, no
synchronous delegation mode, no pause/approval primitive, no workdir
backup (git is the persistence layer), no per-inner-tool permissioning,
no auto-discovery of installed tools, no fallback chains across tools.
