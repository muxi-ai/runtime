# Watching asynchronous jobs

Some tools submit background work: instead of the result they return a
job identifier and a non-terminal status (for example `{"job_id": "...",
"status": "queued"}`). The result is collected with the `watch_job`
tool -- never by re-calling tools yourself.

- When a tool responds with a job identifier and a non-terminal status
  instead of a result, call `watch_job` with the service's status tool
  and a `done_when` matching its terminal states.
- When you plan tool calls in advance and a call will submit an
  asynchronous job (its description mentions a job id, queue, or
  polling), plan a `watch_job` step immediately after that call. The
  `watch_job` step's parameters MUST include `args` carrying the job
  identifier from the submit step's output placeholder, e.g.
  `"args": {"job_id": "{{SUBMIT_OUTPUT.job_id}}"}`.
- After registering the watch, tell the user the work is underway and
  that you will report back. Do not re-call the original tool and do
  not poll the status tool yourself -- the finished result re-enters
  the conversation automatically.

Example: a `submit` tool returned `{"job_id": "job_42", "status":
"queued"}` and the service exposes a `check_status` tool. Call:

```
watch_job({
  "tool": "check_status",
  "args": {"job_id": "job_42"},
  "done_when": {"path": "$.status", "in": ["succeeded", "failed", "canceled"]}
})
```
