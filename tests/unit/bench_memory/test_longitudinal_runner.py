"""Longitudinal runner helper tests (pure logic; no formation boot)."""

from bench.memory.longitudinal_runner import merge_rebuild_report


class TestMergeRebuildReport:
    def test_sums_counts(self):
        totals = merge_rebuild_report(
            {"events": 5, "applied": 5, "failed": 0},
            {"events": 6, "applied": 6, "failed": 1},
        )
        assert totals == {"events": 11, "applied": 11, "failed": 1}

    def test_none_values_treated_as_zero(self):
        # The service response can carry explicit None values (not just
        # missing keys); int(None) killed Scenario D mid-run.
        totals = merge_rebuild_report(
            {"events": None, "applied": 2, "failed": None},
            {"events": 3, "applied": None, "failed": None, "available": True},
        )
        assert totals == {"events": 3, "applied": 2, "failed": 0}

    def test_missing_keys_treated_as_zero(self):
        assert merge_rebuild_report({}, {}) == {"events": 0, "applied": 0, "failed": 0}
