# Memory Speedup Validation Report

## Problem Summary

The original production trace showed a memory path that was far slower than it
should be.

From the log we analyzed:

- About 92% of request time was spent in long-term memory lookup.
- The request searched multiple collections one by one instead of issuing one
  unified query.
- The same user query was embedded repeatedly across collections.
- A second long-term-memory pass ran again from the background extraction path.
- The cheap synopsis/profile path degraded on the PostgreSQL backend.
- The pgvector query path had no visible ANN index support on the embedding
  column.

## Target Outcome

Reduce profile and recall requests from minutes to low seconds, and make the
semantic memory path scale cleanly as memory volume grows.

## Executive Summary

The memory speedup work is implemented and validated.

- Unified multi-collection semantic search is shipped.
- The synopsis/profile fast path is restored on PostgreSQL.
- Memory tables now get best-effort lookup and IVFFlat indexes.
- The full unit suite, targeted PostgreSQL/memory end-to-end tests, and live
  PostgreSQL `EXPLAIN ANALYZE` checks all passed.
- On a benchmark user with `5,000` rows in `memories_1536`, the natural unified
  semantic query used the IVFFlat ANN index and completed in about `10.1 ms`.
- The cheap profile-facts query completed in about `0.94 ms`.

This does not yet reproduce the exact production flow. It does show that the
memory retrieval layer is no longer behaving like a minutes-class bottleneck in
local PostgreSQL validation.

## Delivered Changes

### 1. Unified long-term semantic search

#### Original bottleneck

The orchestration path requested multiple collections, then searched those
collections sequentially. Each search could generate the same query embedding
again.

#### Delivered change

- Added direct multi-collection support to the long-term memory backends.
- Extended the search path to accept `query_embedding` and `collections`.
- Reused one query embedding across the whole multi-collection search.
- Collapsed the multi-collection lookup flow into one backend query where
  supported.
- Kept a compatibility fallback for backends that still require per-collection
  calls.
- Centralized result sorting and top-`k` truncation in
  `persistent_manager.py`.

#### Current evidence

- Unit tests cover single-embedding reuse, unified search, fallback search, and
  deterministic ranking/top-`k` behavior.
- The preference-system e2e test passed with explicit
  `collections=["preferences"]` retrieval on PostgreSQL.

### 2. Cheap synopsis/profile fast path

#### Original bottleneck

The PostgreSQL synopsis path degraded because `user_context.py` called a recent
memory API shape that did not support `external_user_id`. The failure was
swallowed, so profile-style requests could fall back to broader semantic
search.

#### Delivered change

- Switched synopsis generation to user-scoped recent-memory reads.
- Restored the cheap PostgreSQL synopsis path by using `list_memories()`.
- Routed broad profile-recall prompts through synopsis first.
- Added cheap recent profile-facts retrieval from profile-related collections.
- Fell back to semantic search only when both synopsis and cheap recent facts
  were empty.

#### Current evidence

- Unit tests cover user-scoped synopsis reads and the profile-facts fallback.
- `e2e/tests/14_user_synopsis/test_14a1_synopsis_enabled.py` passed.

#### Known caveat

The explicit profile-recall heuristic still matches broad prompts such as
`"What do you know about me?"`, but it does not yet match narrower prompts such
as `"What's my current role?"`.

### 3. PostgreSQL index support for semantic search

#### Original bottleneck

The semantic query path ordered directly by vector distance but had no clear ANN
index support on the embedding column.

#### Delivered change

- Added best-effort memory-table index creation during initialization.
- Added a lookup index on `(user_id, collection)`.
- Added a best-effort IVFFlat pgvector index on the embedding column.
- Switched PostgreSQL distance queries to the pgvector operator form
  `embedding.l2_distance(...)` for index compatibility.
- Made index creation non-fatal and observable when it fails.

#### Current evidence

- Local PostgreSQL validation confirmed the new lookup and IVFFlat indexes exist
  on `memories_384`, `memories_768`, and `memories_1536`.
- Forced plans on the tiny local dataset proved both indexes were usable.
- On the `5,000`-row benchmark user, the natural unified semantic query used
  `idx_memories_1536_embedding_ivfflat`.

## Files Changed

- `src/muxi/runtime/services/memory/long_term.py`
- `src/muxi/runtime/services/memory/sqlite.py`
- `src/muxi/runtime/services/memory/memobase.py`
- `src/muxi/runtime/formation/memory/persistent_manager.py`
- `src/muxi/runtime/formation/memory/user_context.py`
- `src/muxi/runtime/formation/overlord/chat_orchestrator.py`
- `src/muxi/runtime/formation/initialization.py`
- `tests/unit/test_memory_speedup.py`

## Validation Evidence

### Unit and static validation

- `python3 -m pytest tests/unit/ -v` -> `388 passed, 27 skipped`
- `ruff check src tests/unit/test_memory_speedup.py`
- `python3 -m black --check --line-length 100 src tests/unit/test_memory_speedup.py`
- `python3 -m mypy --config-file mypy.ini` on the touched source files

### Live PostgreSQL validation

- Ran the runtime index creation helper against
  `local PostgreSQL test database (muxi_test)`
- Confirmed both new indexes exist on `memories_384`, `memories_768`, and
  `memories_1536`:
  - `idx_memories_<dimension>_user_collection`
  - `idx_memories_<dimension>_embedding_ivfflat`
- On the small local dataset, the planner could still prefer sequential scans.
  Forced plans showed the new indexes were usable.
- Loaded a dedicated benchmark user with `5,000` rows in `memories_1536`,
  evenly split across `activities`, `preferences`, `relationships`,
  `user_identity`, and `work_projects`.
- On that larger dataset:
  - the natural unified semantic query used
    `idx_memories_1536_embedding_ivfflat`
  - execution time was about `10.1 ms`
  - the cheap profile-facts query completed in about `0.94 ms`

### End-to-end validation

- `python3 e2e/tests/14_user_synopsis/test_14a1_synopsis_enabled.py` -> pass
- `python3 e2e/tests/2_memory/test_2o_preference_system.py` -> pass
- `python3 e2e/tests/2_memory/test_2c1_postgresql_user_isolation.py` -> pass

## Risks and Guards

### Risk 1: Result ordering changes after search unification

Guard:

- Always re-sort long-term memory results by score in
  `persistent_manager.py` before truncating to top `k`, regardless of whether
  the backend returns a unified multi-collection result set or a merged fallback
  set.
- Keep focused tests for unified and fallback ranking/top-`k` behavior.

Status:

Implemented and unit tested.

### Risk 2: Fast-path recall returns stale or incomplete data

Guard:

- Reuse the existing synopsis cache invalidation rules.
- Fetch cheap recent profile facts from profile-related collections and include
  them alongside the synopsis.
- Fall back to semantic search only if both the synopsis and the cheap recent
  profile facts are empty.

Status:

Implemented and unit tested.

### Risk 3: Index creation fails on some PostgreSQL deployments

Guard:

- Make index creation best-effort and non-fatal.
- Keep exact-search fallback behavior.
- Log failures through `observability.observe(...)` at warning level instead of
  swallowing them silently.
- Keep the unit test that forces index creation failure and verifies the
  function returns normally while emitting warning events.

Status:

Implemented and explicitly tested.

## Remaining Known Gaps

- Background extraction still needs its own clean context instead of inheriting
  the active request context or request ID.
- The explicit profile-recall heuristic should cover narrower prompts such as
  `"What's my current role?"`.
- The exact production request flow still needs a like-for-like replay once the
  developer shares the real prompt sequence and formation.
- Collection narrowing is still optional. It should only be revisited if the
  exact production replay shows a remaining material bottleneck.

## Current Confidence

### Regression risk

Confidence is about `8.5/10`.

Reasons:

- The full unit suite passed.
- The focused memory speedup tests passed.
- Three targeted PostgreSQL/memory end-to-end tests passed.
- Live PostgreSQL index creation and query-plan checks behaved as expected.

### Performance outcome

Confidence is about `8/10` for the claim that the path dropped from minutes to
seconds, and about `9/10` for the claim that the memory retrieval layer is now
materially faster.

Reasons:

- The structural sources of the original latency were removed.
- The live PostgreSQL benchmark showed the natural unified query using the ANN
  index at about `10.1 ms`.
- The remaining uncertainty is mostly outside the raw query plan:
  embedding latency, background extraction overlap, and the exact production
  flow that triggered the original report.

## Inputs Still Needed From The Developer

To close the remaining confidence gap, we still need the exact production-style
request shape:

- the formation YAML and any local overrides
- the exact user prompt or prompt sequence
- whether synopsis and auto-extraction were enabled
- the embedding model and dimension in that environment
- a representative request trace or request ID if one is available
