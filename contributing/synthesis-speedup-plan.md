# Synthesis Speedup Plan

**Branch:** `feature/synthesis-speedup`
**Date:** 2026-04-30
**Status:** Implemented (merged in PR #162, 2026-04-30)
**Predecessor commit:** `9650a95e` (overlord prompt now renders raw task outputs)
**Implementation commit:** `2cc1d23e` (perf(synthesis): collapse three LLM passes into one persona call)

---

## 1. Goal

Remove one redundant LLM call from every chat reply by deleting the **agent-level synthesis pass** and letting the overlord's existing persona pass produce the user-facing reply. The agent returns raw tool outputs; a deterministic consolidator merges multi-agent results; persona LLM does both synthesis-from-raw and styling in a single call.

Quoted goal from the user:

> Currently live (on develop branch):
> overlord does its thing → assigns to agent(s) → agent(s) do the work → agent(s) synthesise response → overlord receives responses from agent(s) → overlord synthesise the response → overlord gets back to user
>
> What I thought we'll do:
> overlord does its thing → assigns to agent(s) → agent(s) do the work → overlord receives responses from agent(s) → overlord synthesise the response → overlord gets back to user
>
> Just one step removed!

The implementation goes one step further: the overlord's "synthesise" step also collapses into the persona pass, since `_apply_persona` already runs on every reply and is a smart-enough LLM with a loose-enough brief to absorb structured input.

---

## 2. Pipelines compared

### Today (live on `develop @ 8487ed37`)

```
CHAT MODE
  user → overlord → agent
                     ├─ tool calls (LLM × N)
                     ├─ AGENT SYNTHESIS (LLM × 1)              ← delete
                     └─ return prose
         overlord
           └─ _apply_persona (LLM × 1)
                              → user

WORKFLOW MODE (N tasks)
  user → overlord → decompose
                     └─ for each task:
                          ├─ agent tool calls (LLM × M)
                          ├─ AGENT SYNTHESIS (LLM × 1)         ← delete
                          └─ return prose
         overlord
           ├─ WORKFLOW SYNTHESIS (LLM × 1)                     ← replace with deterministic consolidator
           └─ _apply_persona (LLM × 1)
                              → user
```

### After (this plan)

```
CHAT MODE
  user → overlord → agent
                     ├─ tool calls (LLM × N)
                     └─ return RAW outputs (no synthesis)
         overlord
           └─ _apply_persona (LLM × 1, prompt updated to handle raw)
                              → user

WORKFLOW MODE (N tasks)
  user → overlord → decompose
                     └─ for each task:
                          ├─ agent tool calls (LLM × M)
                          └─ return RAW outputs (no synthesis)
         overlord
           ├─ CONSOLIDATE (deterministic, NO LLM)
           │     – one section per task, headers + raw outputs
           │     – artifact filenames listed
           │     – budget-bounded
           └─ _apply_persona (LLM × 1, prompt updated to handle raw)
                              → user
```

### Final shape

```
                              ╔════════════════════════════════════╗
                              ║   ONE LLM PASS at the overlord     ║
                              ║   with persona + raw-data brief    ║
                              ╚════════════════════════════════════╝
                                              ▲
                                              │
                       ┌──────────────────────┴──────────────────────┐
                       │  consolidate (deterministic, no LLM)        │
                       │  — chat: agent's raw_response passed thru   │
                       │  — workflow: per-task sections concatenated │
                       └──────────────────────┬──────────────────────┘
                                              ▲
                                              │
              ┌───────────────────────────────┼───────────────────────────────┐
              │                               │                               │
       Agent A returns RAW          Agent B returns RAW          Agent N returns RAW
       (tool outputs, no synth)     (tool outputs, no synth)     (tool outputs, no synth)
              ▲                               ▲                               ▲
              │                               │                               │
              └─────────────── decompose ←── overlord ──→ chat ───────────────┘
```

One LLM pass at the end. Everything before it is mechanical.

---

## 3. LLM-call count savings

| Path | Today | After | Saved |
|---|---|---|---|
| Chat (single agent) | tools + agent synth + persona = M + 2 | tools + persona = M + 1 | **1 LLM call** (~4 s) |
| Workflow (4 tasks) | tools + 4×agent synth + workflow synth + persona = M + 6 | tools + persona = M + 1 | **5 LLM calls** (~20 s) |

The numbers above match what the live formation log showed on 2026-04-29:
- Turn 2 (chat-mode, 3 tool calls): `planning_response_synthesis_start` at +29.7 s, `planning_response_synthesis_completed` at +33.9 s — confirming the 4.2 s agent synthesis call we want to delete.

---

## 4. What `_apply_persona` actually does today

System prompt (verbatim from `overlord.py:2766`):

> "Reformat the agent's response to match your persona while preserving all technical details and information. Make it conversational and friendly while keeping accuracy."

User content: `"User request: {X}\nAgent response: {raw_response}"`. `max_tokens=2000`, `temperature=0.7`, runs on `routing_model` (or fallback to text model).

Implication: the persona LLM is already smart enough and given enough latitude to absorb structured input. With a small system-prompt addition acknowledging that input may be raw structured tool outputs, it can take over the synthesis-from-raw job that agent-level synthesis currently does. No new LLM call is needed.

---

## 5. Code changes

All on `feature/synthesis-speedup` on top of `9650a95e`.

### 5.1 `src/muxi/runtime/formation/agents/agent.py`

**Skip the agent synthesis call universally** at the synthesis decision branch (~line 2299). Replace the LLM call path with a deterministic raw-response builder.

```python
if my_results and not has_successful_delegation:
    if (
        self._is_pure_artifact_result(my_results)
        and self._is_streaming_active()
    ):
        # existing pure-artifact + streaming-active fast path (kept)
        synthesized_planning_response = self._build_artifact_only_response(my_results)
        observability.observe(... reason="pure_artifact_with_streaming" ...)
    else:
        # NEW: skip the synthesis LLM call always; return raw outputs
        synthesized_planning_response = self._build_raw_response(
            my_results, planning_response_parts
        )
        observability.observe(... reason="always_skip_v2" ...)
```

**New helper `_build_raw_response(my_results, planning_response_parts)`**:
- Renders `my_results` as `### {placeholder}\n{result_text}` blocks
- Appends `### Delegated Response N\n{response}` for each `planning_response_parts` entry
- Notes artifact filenames inline
- Pure string formatting, no LLM call

### 5.2 `src/muxi/runtime/formation/overlord/overlord.py`

**Replace `_synthesize_workflow_results` body with a deterministic consolidator** that reuses `_render_task_body(outputs, budget)` from commit `9650a95e`. No LLM call. Output goes directly into `_apply_persona` as `raw_response`.

`_create_synthesis_prompt` (introduced in `9650a95e`) is no longer needed for the LLM path. Two options:
- **Option 1**: delete it; keep `_render_task_body` as a standalone helper used by the consolidator
- **Option 2**: rename to `_consolidate_workflow_results`, reuse the rendering work directly

Either way, the work in `9650a95e` is not wasted — `_render_task_body` is exactly the consolidation building block.

**Extend `_apply_persona`'s system prompt** with ~50 tokens telling the persona LLM that input may be raw structured tool outputs:

```text
The agent response may be either polished prose or raw structured tool outputs
(JSON-like dicts, key/value blocks, or numbered step results). In either case,
extract every fact, ID, URL, and number, and present them as a clear, friendly
reply in your persona's voice. Do not summarize away or omit specific data.
```

All existing constraints (preserve technical details, length-matching, format) are kept.

### 5.3 `src/muxi/runtime/formation/workflow/executor.py`

**No change.** Since we're skipping agent synthesis universally, no `in_workflow` flag is needed. `_execute_task_with_agent` calls `agent.process_message(...)` exactly as today; the agent now returns raw outputs by default.

---

## 6. Tests

Total: **31 tests** for this change set.

### 6.1 New: `tests/unit/test_agent_skip_synthesis_always.py` (8 tests)

1. `test_agent_skips_synthesis_call_when_my_results_present` — `_synthesize_planning_execution_response` not called
2. `test_agent_skips_synthesis_call_in_chat_mode` — same as above without workflow context
3. `test_pure_artifact_path_still_takes_priority` — existing fast path untouched
4. `test_build_raw_response_renders_each_result_with_placeholder`
5. `test_build_raw_response_renders_delegated_responses`
6. `test_build_raw_response_includes_artifact_filenames`
7. `test_build_raw_response_empty_inputs_returns_fallback`
8. `test_synthesis_skipped_observability_event_emitted`

### 6.2 Update: `tests/unit/test_overlord_synthesis_prompt.py` (15 tests, shipped in `9650a95e`)

- Lift tests to assert the consolidator (deterministic) is what runs, not an LLM call
- Drop the `pytest` and `patch` imports if no longer needed
- Tighten assertions: no LLM mock; assert direct return value

### 6.3 New: `tests/unit/test_workflow_consolidator.py` (5 tests)

1. `test_consolidator_renders_each_task_section_with_header`
2. `test_consolidator_uses_render_task_body_per_task`
3. `test_consolidator_respects_total_budget`
4. `test_consolidator_does_not_call_llm` — assert `model.chat` NOT invoked
5. `test_consolidator_lists_artifact_filenames`

### 6.4 New: `tests/unit/test_apply_persona_handles_raw.py` (3 tests)

1. `test_persona_prompt_includes_raw_input_acknowledgment` — the new prompt fragment is present
2. `test_persona_called_with_raw_dict_string_does_not_error`
3. `test_persona_max_tokens_unchanged` — still 2000 (don't break length expectations)

---

## 7. Verification

1. Full unit suite (903 + new) → must stay green
2. `ruff` + `black` + `isort` clean
3. `python3 scripts/validate_events.py` — `synthesis_skipped` reuses `AGENT_PLANNING`, no new event types needed
4. Live test: restart formation via `run_formation.py`, send 2 turns:
   - Turn 1: a single-agent chat that triggers tool calls. Expected savings: ~4 s vs. last night's runs.
   - Turn 2: a multi-task workflow request. Expected savings: ~20 s vs. last night's 38 s turn.
5. Commit + push. SIF rebuild only after replies are validated.

---

## 8. Risk and rollback

| Risk | Mitigation |
|---|---|
| Persona produces lower-quality replies in chat mode | The 50-token prompt addition + `temperature=0.7` + `max_tokens=2000` gives the model plenty of room. If quality drops, add a chat-mode mini-consolidator (still no LLM) that pre-formats structured data before persona |
| Loss of agent persona voice (each agent had its own system prompt shaping output) | Agent's own persona was already being overwritten by overlord's `_apply_persona` — we lose nothing the user previously saw |
| Workflow consolidator misses edge cases (artifacts, errors, partial failures) | Tests cover artifact filenames, empty results, errored steps. Existing `_render_task_body` already handles these |
| `_create_synthesis_prompt` from `9650a95e` becomes dead code | Either delete it or keep `_render_task_body` as the consolidator's core helper. Either way, the test work isn't wasted |
| Breakage in chat mode | `test_agent_skips_synthesis_call_in_chat_mode` + `test_persona_called_with_raw_dict_string_does_not_error` cover the new behavior. Live test with `run_formation.py` validates end-to-end |

Rollback path: revert this commit. Branch is isolated; `develop` stays untouched until we explicitly merge.

---

## 9. Out of scope

- Touching the SOP file
- Forcing the workflow path to fire
- Changes to decomposition / clarification / planning code
- Modifying `develop`
- SIF rebuild (deferred until replies are validated end-to-end)

---

## 10. Estimated time

- Implementation: ~45 min (4 small edits + 1 helper + 1 prompt edit)
- Tests: ~45 min (31 tests, many are simple assertions)
- Live verification + commit + push: ~30 min

**Total: ~2 hours.**

---

## 11. References

- Predecessor commit: `9650a95e` (overlord prompt renders raw task outputs)
- Branch base: `8487ed37` (`pre-synthesis-speedup-2026-04-29` tag)
- Relevant files:
  - `src/muxi/runtime/formation/agents/agent.py` — `process_message` (L1139), synthesis decision (L2299), `_synthesize_planning_execution_response` (L973)
  - `src/muxi/runtime/formation/overlord/overlord.py` — `_apply_persona` (L2573), `_synthesize_workflow_results` (L9560), `_create_synthesis_prompt` (L9712)
  - `src/muxi/runtime/formation/workflow/executor.py` — `_execute_task_with_agent` (L1371), `_parse_task_response` (L1507)
- Existing tests:
  - `tests/unit/test_agent_skip_synthesis.py` — pure-artifact + streaming-active fast path (separate optimization, kept untouched)
  - `tests/unit/test_overlord_synthesis_prompt.py` — 15 tests for `_render_task_body` / `_create_synthesis_prompt`
