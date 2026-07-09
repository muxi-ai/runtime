"""Cost-model math tests (Tier 4)."""

import json
from pathlib import Path

import pytest

from bench.memory.cost_model import (
    USAGE_SCENARIOS,
    cost_per_query_usd,
    cost_projection,
    footprint_summary,
    latency_summary,
    percentile,
    pricing_snapshot,
    tokens_per_accurate_recall,
)

PRICING_JSON = Path(__file__).resolve().parents[3] / "bench/memory/pricing.json"


class TestPercentile:
    def test_median_of_odd_sequence(self):
        assert percentile([3, 1, 2], 50) == 2.0

    def test_median_interpolates_even_sequence(self):
        assert percentile([1, 2, 3, 4], 50) == 2.5

    def test_p95_linear_interpolation(self):
        values = list(range(1, 101))  # 1..100
        assert percentile(values, 95) == pytest.approx(95.05)

    def test_extremes(self):
        assert percentile([5, 1, 9], 0) == 1.0
        assert percentile([5, 1, 9], 100) == 9.0

    def test_single_sample(self):
        assert percentile([7.5], 99) == 7.5

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            percentile([], 50)

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError):
            percentile([1], 101)


class TestLatencySummary:
    def test_converts_to_milliseconds(self):
        summary = latency_summary([0.1, 0.2, 0.3])
        assert summary["p50_ms"] == 200.0
        assert summary["mean_ms"] == 200.0
        assert summary["min_ms"] == 100.0
        assert summary["max_ms"] == 300.0
        assert summary["samples"] == 3
        assert set(summary) >= {"p50_ms", "p95_ms", "p99_ms"}

    def test_empty_returns_none(self):
        assert latency_summary([]) is None


class TestTokensPerAccurateRecall:
    def test_simple_ratio(self):
        assert tokens_per_accurate_recall(7000, 10) == 700.0

    def test_zero_correct_is_undefined(self):
        assert tokens_per_accurate_recall(7000, 0) is None

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            tokens_per_accurate_recall(-1, 1)


class TestCostPerQuery:
    def test_priced_model(self):
        # 1000 in + 100 out on gpt-4o-mini: 1000*0.15/1M + 100*0.60/1M
        per_query = cost_per_query_usd({"openai/gpt-4o-mini": [1100, 1000, 100]})
        assert per_query == pytest.approx((1000 * 0.15 + 100 * 0.60) / 1_000_000)

    def test_local_model_free(self):
        assert cost_per_query_usd({"local/nomic-ai/nomic-embed-text-v1.5": [500, 500, 0]}) == 0.0

    def test_unknown_model_returns_none(self):
        assert cost_per_query_usd({"mystery/model": [10, 10, 0]}) is None


class TestCostProjection:
    def test_scenarios_match_prd(self):
        assert USAGE_SCENARIOS == {"light": 10, "moderate": 50, "heavy": 200}

    def test_monthly_math(self):
        block = cost_projection(0.001)
        assert block["per_1000_queries_usd"] == 1.0
        assert block["scenarios"]["light"]["queries_per_month"] == 300
        assert block["scenarios"]["light"]["monthly_usd"] == pytest.approx(0.3)
        assert block["scenarios"]["heavy"]["monthly_usd"] == pytest.approx(6.0)

    def test_unpriced_projects_null(self):
        block = cost_projection(None)
        assert block["per_1000_queries_usd"] is None
        assert block["scenarios"]["moderate"]["monthly_usd"] is None


class TestFootprint:
    def test_bytes_per_turn(self):
        block = footprint_summary(
            db_bytes=1_000_000,
            working_memory_items=100,
            embedding_dimension=768,
            ingested_turns=100,
        )
        assert block["working_memory_vector_bytes"] == 100 * 768 * 4
        assert block["bytes_per_ingested_turn"] == pytest.approx(
            (1_000_000 + 100 * 768 * 4) / 100, abs=0.1
        )

    def test_zero_turns_is_null(self):
        block = footprint_summary(0, 0, 768, 0)
        assert block["bytes_per_ingested_turn"] is None

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            footprint_summary(-1, 0, 0, 0)


class TestPricingConfig:
    def test_snapshot_echoes_json_table(self):
        snapshot = pricing_snapshot()
        table = json.loads(PRICING_JSON.read_text())["models"]
        assert snapshot["usd_per_mtok"] == table
        assert snapshot["source"] == "bench/memory/pricing.json"

    def test_json_table_schema(self):
        config = json.loads(PRICING_JSON.read_text())
        assert config["free_prefixes"] == ["local/"]
        for model, price in config["models"].items():
            assert "/" in model
            assert set(price) == {"in", "out"}
            assert price["in"] >= 0 and price["out"] >= 0
