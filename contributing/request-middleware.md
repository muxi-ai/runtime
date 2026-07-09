# Request Middleware and RBAC

How group memberships reach a MUXI formation, and how requests are
gated. MUXI stores no memberships: groups arrive per request from a
formation-declared **request middleware** -- a standard MCP server the
runtime calls with every request payload.

## The two blocks

Top-level in `formation.afs` (not under `server:` -- the pipeline also
applies to embedded `overlord.chat(...)` use):

```yaml
rbac:
  active: auto            # auto (default) | true | false
  fallback: false         # false | <group_name>

middleware:
  # An actual MCP server. Exactly one transport:
  url: "${{ secrets.RESOLVER_URL }}"     # http
  headers:
    Authorization: "Bearer ${{ secrets.RESOLVER_TOKEN }}"
  # command: "./middleware.py"           # stdio (alternative)
  # args: ["--map", "groups.json"]
  timeout: 2s                            # the only runtime knob (default 10s)
```

### `rbac`

| Setting | Behavior |
|---|---|
| `active: auto` (default) | RBAC is on iff `groups/` contains group files |
| `active: true` | Explicit intent; no group files fails the load |
| `active: false` | Kill switch: groups may exist, filtering is disabled (logged loudly) |
| `fallback: false` (default) | A request that ends up with no groups is rejected (403) |
| `fallback: <group>` | No-group requests proceed with that group's permissions (`public` is the idiomatic open tier); the group file must exist |

Dead-config check: RBAC active + `fallback: false` + no `middleware`
block would reject every request -- the formation fails to load.

### `middleware`

The middleware MUST expose exactly one tool named `middleware`:

- Input: the full request payload -- `user_id`, `message`,
  `attachments`, `metadata`, `route_class`. `groups` is NEVER part of
  the input (declaring it fails the load): it cannot arrive as a
  caller's claim.
- Output: the same-shaped payload, possibly modified, plus an optional
  `groups` list -- the only channel through which memberships enter the
  runtime. Identity rewriting (`user_id`) and message policy are
  allowed; `route_class` must be echoed unchanged.
- `route_class` identifies the origin: `chat`, `audiochat`, `trigger`,
  `api` (memory routes), and the internal origins `heartbeat` and
  `scheduler` -- internal requests traverse the middleware identically.

At formation load the runtime connects (existing MCP client -- stdio or
http), lists tools, and fails fast if the tool is absent or its declared
schema does not match the contract
(`src/muxi/runtime/services/middleware/contract.py` is the single source
of truth).

**Fail-closed:** middleware error, timeout, or a malformed response
rejects the request (`error.middleware.failed` event, HTTP 403).
`rbac.fallback` never applies to errors. **No runtime-side caching:**
the middleware is called on every request; respond fast, cache
internally if you need to.

## The simple case

A stdio middleware is a one-file script in the formation directory --
no deployment, no service. Start from the shipped template:

```
cp <runtime>/contributing/templates/middleware.py my-formation/middleware.py
chmod +x my-formation/middleware.py
```

The template (Python stdlib only) implements the MCP stdio protocol
with the single `middleware` tool and resolves groups from a static
user -> groups map -- either embedded or from a JSON file passed as
`args: ["--map", "groups.json"]` (re-read on every call, so edits are
live). Replace the map lookup with whatever your organization uses:
your DB, WorkOS, LDAP.

Middleware wanting to persist context (profile data, embeddings) does
so through the public API/SDK -- its only voice into the request is the
returned payload.

## Everything downstream is unchanged

`groups/` YAML files, inheritance, the four-level tools cascade,
`memory.write` grants, and resource filtering all work as documented in
the group-based-access-control PRD. The middleware only changes where
memberships come from.

## Removed surfaces

- `server.auth: required|open` -- gone. The client key authenticates
  the caller; user-level gating is `rbac.fallback: false` (grouped
  users only) plus a middleware that returns no groups for unknown
  users. Formations still carrying the key fail the load with a
  migration error.
- The `user_groups` table -- gone (creation removed; pre-existing
  deployed tables are left orphaned, nothing destructive).
