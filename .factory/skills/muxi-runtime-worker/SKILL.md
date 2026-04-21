---
name: muxi-runtime-worker
description: Builds Python library features for the MUXI runtime (helpers, consumer migrations, schema, tests, docs). All work is library + pytest + ripgrep; no servers, no browsers.
---

# MUXI Runtime Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE for implementation work on the MUXI embedding platform migration mission.

## When to Use This Skill

Every feature in `features.json` for this mission. There is a single worker type because every feature is Python library work on a well-scoped codebase:

- Building `services/memory/embedding.py` helper
- Migrating memory consumers (`long_term.py`, `working.py`, `sqlite.py`)
- Migrating non-memory consumers (`fusion_engine.py`, `sops.py`, `knowledge/handler.py`, `persistent_manager.py`)
- Updating schema migrations
- Adding unit tests, integration tests
- Running ripgrep sweeps to verify cleanup
- Updating runtime `AGENTS.md`, `mental-model.md`, `CHANGELOG.md`

## Required Skills

- **mental-model** — Invoke at session start for any feature that touches a module you haven't worked in this mission. Rebuild the mental model before editing.
- **muxi-runtime** — Invoke before non-trivial edits to `src/muxi/runtime/` to load deep knowledge of formation/memory/services internals.

These are required because the codebase is large and the migration must preserve subtle invariants (lazy-dim, formation load order, memory tier partitioning). Don't skip them.

## Work Procedure

Follow this procedure STRICTLY. Cutting corners here causes review failures and rework.

### 0. Ground yourself

1. Read the assigned feature in `features.json`. Note its `fulfills` assertion IDs — those are the contract this feature must satisfy.
2. Open `{missionDir}/validation-contract.md` and read every assertion ID in `fulfills`. Understand the pass/fail criteria in detail.
3. Open `{missionDir}/AGENTS.md` and re-read the Decisions log. If your feature appears to conflict with a decision, STOP and return to orchestrator.
4. Invoke the `mental-model` skill if you are touching a module you haven't worked with in this mission. Invoke `muxi-runtime` if editing runtime internals.

### 1. Investigate before editing

1. Use `Grep` (not shell `grep`) to find the exact call sites, attribute reads, and imports you will modify. Pay attention to attribute contracts — the `embedding_model` attribute was a provider object pre-migration and is now a string. The review surfaced that this will break `persistent_manager.py` and similar consumers if not migrated.
2. Use `Read` on the target files BEFORE editing. Do not guess at line contents.
3. If the feature involves a ripgrep sweep assertion, run the sweep command BEFORE you edit so you have the baseline hit count. You will re-run it after edits and confirm the count is zero.

### 2. Write tests FIRST (TDD — mandatory)

1. For every `fulfills` ID whose `Tool` is `pytest` or `pytest (integration)`, write the test file(s) in the exact location referenced in Evidence (e.g., `tests/unit/test_memory_embedding_helper.py`).
2. Each test case MUST be named as stated in the Evidence field of the corresponding assertion. Don't rename. Validators `grep` for these names.
3. Run the test(s): they MUST fail (red) before you write implementation. Capture the red output for your handoff.
4. Write the implementation to make them pass (green). Re-run the tests — all green.
5. Run `verification.commandsRun` entries for both states: red pre-impl and green post-impl.

For unit tests that mock `onellm.Embedding.acreate`:
- The real OneLLM returns an `EmbeddingResponse` dataclass (see `/Users/ran/Projects/muxi/code/onellm/onellm/models.py:355`), NOT a dict. Your mock must return an object with `.data[0].embedding` attribute access — ideally `types.SimpleNamespace`. If you use a dict, VAL-HELPER-006 will catch the regression in a different test and fail you later.
- Assert `task` kwarg is forwarded only for `local/*` models (VAL-HELPER-012 requirement). Test via mock kwarg capture.

For integration tests (marked `@pytest.mark.slow @pytest.mark.integration`):
- Use the real Nomic / OpenAI models. No mocks.
- Gate on `OPENAI_API_KEY`: `if not os.getenv("OPENAI_API_KEY"): pytest.skip("OPENAI_API_KEY required")`.
- First-run latency is 2-3 minutes due to HF download. Don't set a pytest timeout below 300s.

### 3. Implement

1. Edit in the narrowest scope that satisfies the `fulfills` contract. Do not "improve" unrelated code while you're in the file.
2. Preserve existing patterns (line length 100, Python 3.10+ syntax, relative imports within the package, `isort --profile=black`).
3. If the feature involves ripgrep-sweep cleanup, the edits are done when the sweep returns zero hits. Don't declare done before that.
4. If a file isn't in the mission's AGENTS.md scope list, STOP and return to orchestrator. Don't silently expand scope.

### 4. Verify

1. Run `pytest` on every unit test touched (use `-v` and the `--no-header` flag to keep output short).
2. Run `ruff check src/`, `black --check src/`, `isort --check src/` on every file you edited. Fix before committing. (Not required on every feature, but required before the Quality-gate feature.)
3. For ripgrep-sweep assertions: run the EXACT command from the Evidence field and capture the result. Zero hits = pass.
4. For integration-test features: run the integration test once. If HF download takes too long for your budget, note the expected latency and proceed — the validator will re-run it later.

### 5. Commit

1. Stage only files that are part of your feature scope plus any new tests you created.
2. Commit with a message like `feat(embeddings): F{N} {short description} [VAL-X-Y, VAL-X-Z]`. List the fulfilled assertion IDs in brackets so scrutiny can trace coverage.
3. Do NOT touch `.factory/` files — those are orchestrator-managed.

### 6. Handoff

Write a COMPLETE handoff. See Example Handoff below for the format. Specifically:
- List every `fulfills` ID, state "passed" or "not yet green" for each.
- Every command you ran in `verification.commandsRun` with its exit code and a one-line observation of what it proved.
- Every test you added with `tests.added` entries.
- Every ripgrep sweep you ran with the exact command and the hit count.
- Any discovered issues — even minor ones — in `discoveredIssues`.

Missing any of these makes the handoff useless for orchestrator accountability.

## Example Handoff

```json
{
  "salientSummary": "Built services/memory/embedding.py helper module with embed() + probe_dimension() + DEFAULT_EMBEDDING_MODEL. Wrote 9 unit tests (all fulfills IDs from VAL-HELPER-001..006, 009, 011, 013). Red-green-refactor: all tests red initially, green after implementation. Ruff/black/isort clean on the new file.",
  "whatWasImplemented": "New module src/muxi/runtime/services/memory/embedding.py with: (1) DEFAULT_EMBEDDING_MODEL = 'local/nomic-ai/nomic-embed-text-v1.5'; (2) async def embed(model, input, dimensions=None, task=None, pooling=None) that normalizes input to list, forwards dimensions/task/pooling kwargs to onellm.Embedding.acreate, uses dataclass attribute access (resp.data[0].embedding), and strips task kwarg when model does not start with 'local/' (VAL-HELPER-012); (3) async def probe_dimension(model) that issues a single embed call with a placeholder string and returns len(resp.data[0].embedding). Module docstring documents empty-input behavior (raises InvalidRequestError) and pooling default (forwarded when provided, otherwise OneLLM default mean). Tests at tests/unit/test_memory_embedding_helper.py with 9 cases matching the names in validation-contract.md Evidence fields.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      {
        "command": "pytest tests/unit/test_memory_embedding_helper.py -v",
        "exitCode": 1,
        "observation": "Pre-impl: all 9 tests fail with ModuleNotFoundError. Confirmed red state."
      },
      {
        "command": "pytest tests/unit/test_memory_embedding_helper.py -v",
        "exitCode": 0,
        "observation": "Post-impl: 9 passed in 0.42s. test_embed_uses_dataclass_attribute_access passes with SimpleNamespace mock that raises TypeError on __getitem__ (VAL-HELPER-006 guard)."
      },
      {
        "command": "python -c 'from muxi.runtime.services.memory.embedding import embed, probe_dimension, DEFAULT_EMBEDDING_MODEL; assert DEFAULT_EMBEDDING_MODEL == \"local/nomic-ai/nomic-embed-text-v1.5\"'",
        "exitCode": 0,
        "observation": "VAL-HELPER-001, VAL-HELPER-002 pass."
      },
      {
        "command": "ruff check src/muxi/runtime/services/memory/embedding.py",
        "exitCode": 0,
        "observation": "Clean."
      },
      {
        "command": "black --check src/muxi/runtime/services/memory/embedding.py tests/unit/test_memory_embedding_helper.py",
        "exitCode": 0,
        "observation": "Clean."
      },
      {
        "command": "isort --check src/muxi/runtime/services/memory/embedding.py tests/unit/test_memory_embedding_helper.py",
        "exitCode": 0,
        "observation": "Clean."
      }
    ],
    "interactiveChecks": []
  },
  "tests": {
    "added": [
      {
        "file": "tests/unit/test_memory_embedding_helper.py",
        "cases": [
          { "name": "test_embed_returns_list_of_vectors_for_single_input", "verifies": "VAL-HELPER-003 (single-string input returns 1-elem list)" },
          { "name": "test_embed_returns_list_of_vectors_for_batch_input", "verifies": "VAL-HELPER-003 (list input returns same-length list)" },
          { "name": "test_embed_passes_dimensions_kwarg", "verifies": "VAL-HELPER-004 (dimensions forwarded)" },
          { "name": "test_embed_passes_task_kwarg", "verifies": "VAL-HELPER-005 (task forwarded for local/*)" },
          { "name": "test_embed_uses_dataclass_attribute_access", "verifies": "VAL-HELPER-006 (SimpleNamespace mock, __getitem__ raises TypeError)" },
          { "name": "test_embed_empty_string_behavior", "verifies": "VAL-HELPER-009 (raises InvalidRequestError)" },
          { "name": "test_embed_whitespace_only_behavior", "verifies": "VAL-HELPER-009 (raises InvalidRequestError)" },
          { "name": "test_embed_task_none_path", "verifies": "VAL-HELPER-011 (no synthesized default)" }
        ]
      }
    ]
  },
  "discoveredIssues": [
    {
      "severity": "info",
      "description": "OneLLM 0.20260421.0's LocalProvider exposes a `pooling` kwarg but doesn't document the default in its public API. Helper forwards it when provided; default falls through to OneLLM's behavior. Noted in module docstring.",
      "suggestedFix": "Upstream OneLLM should document pooling default. Not blocking this mission."
    }
  ]
}
```

## When to Return to Orchestrator

Return (don't push through) if any of these happen:

- A file you need to modify is not in the AGENTS.md scope list.
- A ripgrep sweep returns hits in a file outside your feature's scope. You found collateral damage — orchestrator needs to know.
- The Decisions log (AGENTS.md §Critical Conventions) appears to conflict with the feature description.
- An integration test fails in a way that traces to OneLLM internals. OneLLM is off-limits; file this as an upstream bug via orchestrator.
- `OPENAI_API_KEY` is missing AND your feature requires a cloud regression test.
- HuggingFace is unreachable from the host AND your feature requires a fresh download.
- The ONNX cold-start on your machine takes so long that an integration test would exceed reasonable mission budget (>5 minutes). Report it; don't bypass the test.
- You discover a pre-existing failure unrelated to embeddings that blocks your work. Document it in the handoff and return.
- TDD-violation scenario: the feature has no `pytest` assertion in `fulfills` (e.g., pure ripgrep-sweep). Still write tests where the helper behavior warrants it. If that's impossible, explicitly note it.
