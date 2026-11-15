# Trigger Auth

How a webhook provider (Stripe, HubSpot, a database listener) calls a trigger directly. A trigger normally requires the formation's client key, which providers cannot send. Each provider proves who it is in its own way, usually a signature header, so a trigger can name its own auth check instead.

## The frontmatter key

A trigger file (`triggers/<name>.md`) may declare `auth` with a script path or an http(s) URL:

```yaml
---
auth: ./auth/stripe.py
---
A Stripe event arrived: ${{ data.type }}
```

```yaml
---
auth: https://auth.internal/stripe
---
```

A relative path is resolved from the formation directory.

## Load-time checks

On load the runtime scans `triggers/*.md` once and keeps `{trigger name: script or URL}`. The formation fails to load, with an error naming the trigger and the target, when:

- the script does not exist or is not executable;
- the URL gives no HTTP response at all (DNS failure, connection refused, timeout); any HTTP status counts as reachable;
- the value is neither a path nor an http(s) URL.

The scan reads only `auth`. Any other frontmatter problem (bad YAML, an unknown key) stays a call-time 400, as before, so a formation with one broken trigger file still boots.

## What happens on a request

A small middleware in front of the routes acts only on `POST /v1/triggers/{name}` for a name with `auth`. It reads the raw body and runs the check:

- **Pass:** the request continues as a normal key-authenticated call. The middleware sets `X-Muxi-Client-Key` to the formation's key, wraps the body as `{"data": ...}` and drops any `X-Muxi-User-Id` the caller sent, so the user is `"0"` (a request middleware, if configured, may still set the identity). The run is async, in its own session.
- **Fail:** the request continues unchanged. The client-key check rejects it with the usual 401, or admits it if the caller sent the real key.

The middleware never builds a response itself, and the route behind it is unchanged: client-key check, body validation, `X-Muxi-Idempotency-Key`, request middleware, RBAC, rendering and the run all apply as for any keyed call. `GET /v1/triggers/{name}` still requires the key, and formations with no `auth` line never get the middleware.

The body after a pass:

| Provider body | `data` |
|---|---|
| A JSON object | the object as-is |
| Anything else (form-encoded, plain text, a JSON array, empty) | `{"body": "<the body as text>"}` |

A caller holding the client key can always call an `auth` trigger the normal way, with a `{"data": ...}` body. That is how replays and scheduled catch-ups reach it: a stored provider event cannot pass a signature check twice.

## The check

Both kinds receive the same JSON:

```json
{
  "trigger": "stripe",
  "method": "POST",
  "url": "https://formation.example/v1/triggers/stripe",
  "headers": {"stripe-signature": "...", "content-type": "application/json"},
  "body": "<base64 of the exact request bytes>"
}
```

Header names are lowercase. A repeated header arrives as one comma-joined value.

- **Script:** the runtime executes it with the JSON on stdin and the runtime's environment, which is how the script gets its signing secret. Exit code 0 passes; any other code fails. Its stdout and stderr are discarded.
- **URL:** the runtime POSTs the JSON. A 2xx response passes; anything else fails.

The check fails closed: an error, a timeout (2 seconds, fixed) or an unreachable target is a fail. A fail is logged as `error.authentication.failed` with the trigger name and the failure kind (`exit_code`, `http_status`, `timeout`, `error`); the event never carries headers or body.

## Example: Stripe

[`templates/stripe_auth.py`](templates/stripe_auth.py) checks a `Stripe-Signature` header with the Python standard library only. Copy it into the formation, make it executable and point a trigger at it:

```
mkdir -p my-formation/auth
cp <runtime>/contributing/templates/stripe_auth.py my-formation/auth/stripe.py
chmod +x my-formation/auth/stripe.py
```

It reads the endpoint's signing secret from `STRIPE_WEBHOOK_SECRET` in the runtime's environment and rejects signatures older than five minutes.

## Not supported

- Responses beyond pass or fail. Slack's one-time `url_verification` handshake, which must echo a challenge, cannot be answered, so Slack Events cannot be pointed at a trigger yet.
- A configurable timeout, auth headers on the auth URL, or retries.

One edge to know: when the check fails on a body declared `Content-Type: application/json` that is not valid JSON, the caller gets a 422, not the 401. The framework parses JSON bodies before the client-key check, as it does today on every route.
