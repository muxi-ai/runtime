"""Longitudinal dataset loader tests (fixture + generated roundtrips)."""

import json
from pathlib import Path

import pytest

from bench.memory.longitudinal_corpus import SCENARIOS, generate_dataset
from bench.memory.longitudinal_dataset import load_longitudinal
from bench.memory.structured_corpus import write_dataset

FIXTURE = Path(__file__).resolve().parents[3] / "bench" / "memory" / "fixtures"


@pytest.fixture(scope="module")
def scenarios(tmp_path_factory):
    path = tmp_path_factory.mktemp("longitudinal") / "dataset.json"
    write_dataset(generate_dataset(preset="fixture", seed=42), path)
    return load_longitudinal(path)


class TestLoader:
    def test_all_scenarios_loaded(self, scenarios):
        assert set(scenarios) == set(SCENARIOS)
        for key, scenario in scenarios.items():
            assert scenario.key == key
            assert scenario.dataset.cases
            assert scenario.config

    def test_question_categories_map_to_question_type(self, scenarios):
        buffer_cycle = scenarios["buffer_cycle"]
        types = {question.question_type for _, question in buffer_cycle.dataset.iter_questions()}
        assert types == {"evicted_recall", "recent_recall"}

    def test_ground_truth_extras_loaded(self, scenarios):
        cross = scenarios["cross_agent"]
        truth = next(iter(cross.ground_truth.values()))
        assert truth.artifacts
        assert truth.question_meta
        assert truth.decisions

        isolation = scenarios["isolation"]
        for truth in isolation.ground_truth.values():
            assert truth.canaries

        contradiction = scenarios["contradiction"]
        truth = next(iter(contradiction.ground_truth.values()))
        assert truth.contradictions
        assert truth.distractors
        assert {c["expected_detection"] for c in truth.contradictions} == {
            "conflicted",
            "superseded",
        }

    def test_relationships_keep_confidence(self, scenarios):
        truth = next(iter(scenarios["contradiction"].ground_truth.values()))
        confidences = {rel["confidence"] for rel in truth.relationships}
        assert len(confidences) > 1  # per-fact confidences survived the roundtrip

    def test_session_dates_mapped(self, scenarios):
        truth = next(iter(scenarios["buffer_cycle"].ground_truth.values()))
        case = scenarios["buffer_cycle"].dataset.cases[0]
        assert set(truth.session_dates) == {s.session_id for s in case.sessions}

    def test_zero_question_scenario_allowed(self, scenarios):
        assert scenarios["contradiction"].dataset.question_count == 0

    def test_committed_fixture_loads(self):
        scenarios = load_longitudinal(FIXTURE / "longitudinal_sample.json")
        assert set(scenarios) == set(SCENARIOS)

    def test_committed_fixture_is_regenerable(self):
        # The committed fixture must equal the generator's output for
        # the documented (preset, seed) so it can always be rebuilt.
        committed = json.loads((FIXTURE / "longitudinal_sample.json").read_text())
        assert committed == json.loads(
            json.dumps(generate_dataset(preset="fixture", seed=42), sort_keys=True)
        )

    def test_wrong_name_rejected(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"name": "other", "scenarios": {}}))
        with pytest.raises(ValueError, match="Unexpected dataset name"):
            load_longitudinal(path)

    def test_missing_file_rejected(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_longitudinal(tmp_path / "absent.json")

    def test_unknown_scenario_rejected(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text(
            json.dumps(
                {
                    "name": "muxi-longitudinal",
                    "scenarios": {"mystery": {"cases": [{"case_id": "x"}]}},
                }
            )
        )
        with pytest.raises(ValueError, match="Unknown scenario"):
            load_longitudinal(path)
