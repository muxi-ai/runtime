# E2E Test Failure Tracker

**Baseline run:** 216/230 (2026-03-02)
**After table fixes:** ~222-223/230 (estimated, pending full re-run)
**Remaining failures:** 8 tests

---

## Fixed (committed + pushed)

| Test | Root Cause | Fix |
|------|-----------|-----|
| 2i2, 2i3, 2j1 | Raw SQL referenced `memories` table (now `memories_1536`) | Updated SQL |
| 2o1, 2o2, 2o_pref | Same + FK cascade failure on user delete | Rewrote cleanup, updated SQL |
| 2k1, 2i1, 2m1, 2l1 | Same pattern (proactive, were passing but fragile) | Updated SQL |
| postgres_isolation | INSERT/SELECT on bare `memories` | Changed to `memories_1536` |
| long_term.py search_text | Hardcoded `FROM memories m` in raw SQL | Dynamic `self.MemoryModel.__tablename__` |
| test_2j1, test_2l1 | `pg_indexes WHERE tablename = 'memories'` | Changed to `memories_1536` |

---

## Remaining Failures (8 tests)

### Flaky / LLM non-determinism -- pass on retry (4 tests)

| Test | Behavior on re-run | Notes |
|------|-------------------|-------|
| **1b_2** agent routing | PASSED | LLM picks wrong agent occasionally |
| **3b1** speech transcription | PASSED (found 2+ keywords) | Sometimes only 1 keyword in response |
| **6** routing_confirmed | PASSED (2/3 majority) | 1/3 queries routed wrong; test allows majority |
| **8a2** no false clarification | PASSED | LLM over-clarifies occasionally |

### Confirmed real issues (4 tests)

| Test | Root Cause | Confirmed How |
|------|-----------|---------------|
| **3c1** video analysis | **Video file not reaching Gemini.** LLM responds "Could you please provide the video" (64 chars). The 14MB `.mov` file is passed correctly in the `files` dict but the model never sees it. Possibly a file size or content_type handling bug in the multimodal pipeline. | Ran manually, got same "provide the video" response |
| **2k2** memory priority | **FAISS SIGSEGV (signal -6).** Crashes during rapid sequential buffer adds (15 msgs at 0.5s intervals). FAISS C library segfaults. Process exits 0 when run directly (C ext crash), runner detects signal -6. Pre-existing. | Ran manually, process dies silently mid-test |
| **8d1** safety critical | **Extraction wait too short.** User says "I'm allergic to peanuts", then only 3s later asks "Can I eat peanut butter?". Extraction pipeline needs 8-10s. LLM doesn't have the allergy in context yet. | Ran manually, LLM says "response unclear" -- no allergy warning |
| **9a3b** auto-async | **Webhook delivery timeout.** System correctly picks async mode and starts processing, but webhook at `127.0.0.1:8765` never receives callback after 60s wait. Infrastructure/timing issue. | Ran manually, webhook wait times out |

---

## Proposed Fixes

| Test | Fix | Complexity |
|------|-----|-----------|
| **3b1** | Relax keyword threshold from 2 to 1 | Trivial |
| **3c1** | Investigate multimodal file pipeline for large video files | Needs debugging |
| **8d1** | Increase extraction wait from 3s to 10s | Trivial |
| **2k2** | Increase delay between buffer adds, or accept as known FAISS issue | Low |
| **9a3b** | Check webhook server lifecycle in test setup | Medium |
| **1b_2, 6, 8a2** | No fix needed -- LLM flaky, pass on retry | None |
