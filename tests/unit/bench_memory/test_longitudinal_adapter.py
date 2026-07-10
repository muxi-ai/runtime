"""Longitudinal adapter tests (state handling; no formation boot)."""

from bench.memory.longitudinal_adapter import LongitudinalMemoryAdapter


class TestClearCase:
    def test_resets_per_case_counters(self):
        adapter = LongitudinalMemoryAdapter(buffer_max_mb=0.4)
        adapter.buffer_ingested_turns = 228
        adapter.cleanup_passes = 18
        adapter.flush_hand_offs = 11
        adapter.flush_items_handed = 131

        adapter.clear_case()

        assert adapter.buffer_ingested_turns == 0
        assert adapter.cleanup_passes == 0
        assert adapter.flush_hand_offs == 0
        assert adapter.flush_items_handed == 0

    def test_still_resets_tier2_provenance(self):
        adapter = LongitudinalMemoryAdapter()
        adapter._rel_provenance = {("a", "works_at", "b"): [("s1", "s1:0")]}
        adapter._entity_provenance = {"a": [("s1", "s1:0")]}
        adapter._log_sources = {"2026-01-01": ["s1"]}

        adapter.clear_case()

        assert adapter._rel_provenance == {}
        assert adapter._entity_provenance == {}
        assert adapter._log_sources == {}
