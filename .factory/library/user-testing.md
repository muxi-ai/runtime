# User Testing

Validation surface findings for this mission. Validators reference this document.

## Validation Surface

This mission is a **Python library refactor**, not a user-facing application. There is no browser UI, no TUI, no interactive CLI to exercise. Validation is programmatic and shell-based.

### Available validation tools

| Tool | Use | Required skill |
|---|---|---|
| `pytest` | Unit + integration assertions | standard (no special skill) |
| `sqlite3` CLI | Schema DDL validation | standard shell |
| `rg` (ripgrep) | Sweep assertions (zero-hit patterns) | standard shell |
| `python -c "..."` | Import-graph and attribute-existence checks | standard shell |
| `cd e2e && python run_random_tests.py N` | E2E regression sample | standard shell |

### NOT applicable

- **agent-browser** — no browser surface
- **tuistory** — no TUI surface
- **curl** — no HTTP endpoints exposed by this mission's deliverables

## Validation Concurrency

**Max concurrent validators: 1** (sequential).

Rationale:
- Integration tests share the HuggingFace cache on disk. Parallel writes to the same cache directory are unsafe.
- ONNX session loading is IO-bound on model weights; parallel loads compete for disk bandwidth rather than speeding up.
- OpenAI rate limits apply per-key; parallel calls risk 429s on long test runs.
- `pytest` + its subprocess model already handles within-test parallelism where appropriate.

No meaningful speedup from multiple concurrent validator sessions on this mission.

## Environment setup (for validators)

Before running the first integration test:
1. Confirm `OPENAI_API_KEY` is set (env or sourced from `e2e/tests/*/secrets.enc`).
2. Confirm `~/.cache/huggingface/hub/` is writable (or `HF_HOME` is set to a writable path).
3. Confirm network access to `huggingface.co` if the cache is cold.
4. Confirm OneLLM is installed at `>=0.20260421.0`: `python -c "import onellm; print(onellm.__version__)"`.

## Evidence conventions

Assertions in `validation-contract.md` specify `Tool: shell` or `Tool: pytest` or `Tool: pytest (integration)`:

- **shell** — run the literal command; exit code 0 (or match specified output) is pass.
- **pytest** — run pytest with the specified `-k` expression; exit code 0 is pass; verify PASS in output for the specific test name.
- **pytest (integration)** — same, with `-m slow` flag. Downloads may happen on first run.

All evidence must include: the exact command run, the exit code, and (for pytest) the test names that ran and their individual PASS/FAIL status.

## Known limitations

- **Stochasticity in `run_random_tests.py`**: the e2e random sample picks 10 tests from ~200. A single run may include known-flaky tests in areas this mission does not touch (MCP, a2a, RCE). Re-run once on failure before flagging; persistent failures in non-embedding areas are pre-existing and documented under "Known pre-existing issues" in `AGENTS.md`.
- **First-time Nomic v2 MoE download is slow**: ~1.9 GB over network. On a cold cache, VAL-INTEG-002 may take 2-5 minutes.
- **ONNX cold start**: each fresh pytest process pays ~3.5s to load the ONNX session. Not a bug; noted in the PRD's Decisions log.

## Mid-mission discoveries

(Validators and workers append findings here as they arise.)

- _(none yet)_
