"""Unit tests for Memory Revamp Phases 3-5 config validation.

Fail-fast validation of the new formation config sections:
``memory.compaction`` (pre-compaction flush), ``memory.pruning``
(cache-TTL pruning), ``memory.index`` (knowledge index), and
``memory.lint``. Uses the section-level validator methods directly, the
same pattern the slug validation tests use.
"""

from __future__ import annotations

from muxi.runtime.formation.config.validation import FormationValidator


def _validate_memory(memory_config: dict) -> list[str]:
    validator = FormationValidator()
    validator._validate_memory_config(memory_config)
    return validator.result.errors


class TestCompactionValidation:
    def test_valid_config_passes(self):
        assert not _validate_memory({"compaction": {"flush_enabled": True, "flush_threshold": 0.8}})

    def test_absent_section_passes(self):
        assert not _validate_memory({})

    def test_non_dict_fails(self):
        errors = _validate_memory({"compaction": "yes"})
        assert any("memory.compaction must be a dictionary" in e for e in errors)

    def test_flush_enabled_type_checked(self):
        errors = _validate_memory({"compaction": {"flush_enabled": "yes"}})
        assert any("flush_enabled must be a boolean" in e for e in errors)

    def test_flush_threshold_range_checked(self):
        for bad in (0, -0.5, 1.5):
            errors = _validate_memory({"compaction": {"flush_threshold": bad}})
            assert any("flush_threshold" in e for e in errors), bad


class TestPruningValidation:
    def test_valid_config_passes(self):
        assert not _validate_memory(
            {
                "pruning": {
                    "mode": "cache-ttl",
                    "cache_ttl_seconds": 300,
                    "keep_last_n_tool_results": 3,
                    "soft_trim_max_chars": 4000,
                }
            }
        )

    def test_invalid_mode_fails(self):
        errors = _validate_memory({"pruning": {"mode": "sometimes"}})
        assert any("memory.pruning.mode" in e for e in errors)

    def test_invalid_strategy_fails(self):
        errors = _validate_memory({"pruning": {"strategy": "medium"}})
        assert any("memory.pruning.strategy" in e for e in errors)

    def test_negative_numbers_fail(self):
        errors = _validate_memory({"pruning": {"cache_ttl_seconds": -1}})
        assert any("cache_ttl_seconds" in e for e in errors)
        errors = _validate_memory({"pruning": {"keep_last_n_tool_results": -1}})
        assert any("keep_last_n_tool_results" in e for e in errors)


class TestIndexValidation:
    def test_valid_config_passes(self):
        assert not _validate_memory(
            {
                "index": {
                    "enabled": True,
                    "max_tokens": 300,
                    "regenerate_on": ["lint", "log_entry"],
                    "entity_count_threshold": 10,
                }
            }
        )

    def test_invalid_max_tokens_fails(self):
        errors = _validate_memory({"index": {"max_tokens": 0}})
        assert any("memory.index.max_tokens" in e for e in errors)

    def test_unknown_regenerate_trigger_fails(self):
        errors = _validate_memory({"index": {"regenerate_on": ["full_moon"]}})
        assert any("regenerate_on" in e for e in errors)

    def test_regenerate_on_must_be_list(self):
        errors = _validate_memory({"index": {"regenerate_on": "lint"}})
        assert any("must be a list" in e for e in errors)


class TestLintValidation:
    def test_valid_config_passes(self):
        assert not _validate_memory(
            {
                "lint": {
                    "enabled": True,
                    "schedule": "weekly",
                    "conflict_resolution_days": 7,
                    "orphan_cleanup": True,
                    "stale_artifact_days": 90,
                }
            }
        )

    def test_numeric_schedule_passes(self):
        assert not _validate_memory({"lint": {"schedule": 3600}})

    def test_invalid_schedule_fails(self):
        errors = _validate_memory({"lint": {"schedule": "fortnightly"}})
        assert any("memory.lint.schedule" in e for e in errors)

    def test_day_counts_must_be_positive_integers(self):
        for key in ("conflict_resolution_days", "stale_artifact_days"):
            errors = _validate_memory({"lint": {key: 0}})
            assert any(key in e for e in errors), key

    def test_orphan_cleanup_type_checked(self):
        errors = _validate_memory({"lint": {"orphan_cleanup": "yes"}})
        assert any("orphan_cleanup must be a boolean" in e for e in errors)
