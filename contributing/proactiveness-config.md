# Proactiveness Configuration Reference

Formation config reference for the two proactiveness surfaces:
`proactive:` (notification channels + heartbeat) and `commands:` (slash
commands).

Both are optional and inert: a formation without them behaves
exactly as before. Parsing is fail-fast -- any structural problem is a
descriptive load-time error, never a silent default.

## `proactive:`

Declares notification channels and the heartbeat. Channels are trigger
transformers (see [channel-templates.md](channel-templates.md)); there
is no separate notification delivery stack.

```yaml
proactive:
  channels:
    telegram:
      transformer: telegram-notify            # transformers/telegram-notify.yaml
    slack:
      transformer: slack                      # bundled template (payload only)...
      url: "${{ secrets.SLACK_BRIDGE_URL }}"  # ...so the channel supplies the URL
  default_channel: telegram                   # optional: channel name or "webhook"
  heartbeat:
    enabled: true                             # default true when block present
    interval: "30m"                           # 45s / 30m / 2h; optional "every " prefix
    target: last                              # last | preferred | webhook | <channel>
    active_hours:                             # optional: absent means always active
      start: "09:00"                          # 24-hour HH:MM
      end: "18:00"                            # start > end wraps past midnight
      timezone: "UTC"                         # IANA name, or "user" for per-user tz
      weekends: true                          # false suppresses Saturday/Sunday
    sop: my-heartbeat                         # optional: formation SOP as base prompt
    instruction: "Focus on meeting prep"      # optional: appended to the prompt
```

### `proactive.channels`

| Key | Required | Meaning |
|---|---|---|
| `transformer` | yes | Transformer name. Formation `transformers/<name>.yaml` first, then a bundled template (`slack`, `telegram`, `discord`, `email`). |
| `url` | when the transformer has no `endpoint.url` | Delivery destination. Literal http(s) URL or a `${{ ... }}` template (e.g. a secret). Wins over the transformer's own URL. |

Channel names use `[a-zA-Z0-9_-]+` and may not be a reserved routing
target (`last`, `preferred`, `webhook`). A channel whose transformer is
missing, or that ends up with no URL from either source, fails at load
time.

### `proactive.default_channel`

Fallback channel when a notification names no channel and the user has
no preference. Must be a declared channel name or `webhook`. Absent:
delivery falls back to the standard payload posted to
`async.webhook_url`.

Routing precedence for every notification: explicit channel(s) > user
preferred channel > `default_channel` > webhook.

### `proactive.heartbeat`

Periodic proactive check-ins. Rides the existing scheduler loop --
`heartbeat.enabled: true` requires `scheduler.enabled: true` (which
requires persistent memory).

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Turn the heartbeat on/off (block absent = off). |
| `interval` | `30m` | How often the heartbeat considers running (`45s`, `30m`, `2h`, optionally `every 30m`). |
| `target` | `last` | Where reports go: `last` (user's most recent inbound channel), `preferred`, `webhook`, or a declared channel name. |
| `active_hours` | absent (always active) | Per-user quiet-hours gate. `timezone: user` uses each user's stored timezone (UTC when unset). `start > end` wraps past midnight. `weekends: false` skips Saturday/Sunday. |
| `sop` | absent | Formation SOP name used as the base prompt, replacing the bundled default heartbeat SOP entirely. |
| `instruction` | absent | Extra guidance appended to the base prompt (whichever one is active) under an `## Additional Instructions` heading. |

**Default heartbeat SOP.** When `sop:` is not configured, the bundled
default SOP (`formation/proactive/builtin/heartbeat.md`, shipped with
the runtime) drives the check: review scheduled jobs, open loops, and
time-sensitive context; message only when something genuinely needs
attention; otherwise reply `HEARTBEAT_OK`. A formation `sop:` overrides
it entirely; `instruction:` appends to either.

**HEARTBEAT_OK suppression.** A heartbeat response that mentions
`HEARTBEAT_OK` is never delivered -- the agent wakes up, checks, and
stays silent. The sentinel is matched anywhere in the response (agent
pipelines routinely wrap the raw sentinel in prose); it exists only
inside the heartbeat prompt, so mentioning it always means "nothing to
report". Anything else routes to `target` through the normal
notification precedence.

The heartbeat runs once per known user (users with recorded channel
state), each in a fresh session, with per-user failure isolation: one
user's failure never blocks another's heartbeat or interactive chat.

## `commands:`

Opt-in slash commands. Without the block, messages starting with `/`
are normal messages.

```yaml
commands:
  enabled: true          # default true when block present
  aliases:
    tasks: weekly-report # /tasks runs the weekly-report SOP
  builtin:
    reset: false         # hide a specific built-in
```

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Master switch for slash-command interception. |
| `aliases` | `{}` | Alias -> command name map, expanded before resolution. |
| `builtin` | `{}` | Built-in name -> boolean; `false` hides that built-in. Unknown names fail validation. |

**Resolution order:** alias expansion, then formation SOPs by name,
then built-ins. A formation SOP named like a built-in shadows it
entirely (formation-author overrides win). Unknown commands
short-circuit with the available command list -- no LLM round-trip.

**Built-in commands** (all deterministic; a formation lacking the
backing service gets a friendly "not configured" reply):

| Command | Usage | Backed by |
|---|---|---|
| `/setup` | `/setup` | Guided channel + timezone setup (deterministic flow, not an LLM conversation) |
| `/help` | `/help` | Command registry: built-ins + formation SOPs + aliases |
| `/status` | `/status` | Formation id, channel state, heartbeat on/off, job counts |
| `/jobs` | `/jobs [pause\|resume\|cancel\|logs <id>]` | Scheduler (caller's own jobs only) |
| `/identity` | `/identity [link\|unlink <identifier>]` | `user_identifiers` table (multi-user formations) |
| `/channels` | `/channels [default\|test <channel>]` | Declared channels + user preference |
| `/preferences` | `/preferences [timezone <tz>\|channel <name>]` | User channel store |
| `/reset` | `/reset` | Buffer memory (current session only) |

## Soul document (overlord-level)

Soul is an overlord-only concept: a `SOUL.md` (or `soul.md`) file next
to `formation.yaml` is auto-discovered at load time and feeds the
overlord's default persona (precedence: `SOUL.md` > `soul.md` > inline
`overlord.soul` > built-in default). Individual agents are single-file
contained -- an agent's character lives entirely in its
`system_message`. See [soul-documents.md](soul-documents.md) for the
template and writing guide.

## API surface

Client-key endpoints (also in the formation's OpenAPI spec at `/docs`):

**`POST /v1/notifications`** -- send a text notification through the
routing precedence. 503 when the formation has no `proactive:` block;
502 when no channel delivery succeeded.

```bash
curl -X POST http://localhost:8000/v1/notifications \
  -H "X-Muxi-Client-Key: $CLIENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "usr_abc123", "message": "Deploy finished",
       "channels": ["telegram"]}'
```

**`GET /v1/users/{user_id}/channels`** -- a user's channel state:
preferred channel, per-channel addressing context, last-used channel,
timezone.

**`PUT /v1/users/{user_id}/channels`** -- update preferences. Only
provided fields change; addressing contexts merge per channel (empty
mapping removes a channel).

```bash
curl -X PUT http://localhost:8000/v1/users/usr_abc123/channels \
  -H "X-Muxi-Client-Key: $CLIENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"preferred_channel": "telegram",
       "channels": {"telegram": {"chat_id": "123456"}},
       "timezone": "Europe/London"}'
```
