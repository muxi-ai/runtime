"""Unit tests for the tune step (Self-Improving Formation, Phase 2).

Pins the tuner end-to-end against a real spool, a real CaptainsLogService
and real files (LLM mocked): distillation into MUXI.md (auto_apply) or
PENDING-MUXI.md (manual), the privacy gate on tuner-written content, the
bounded-file contract, experiment recording and dismissal semantics, the
morning report delivery (widget included), the apply/dismiss surfaces,
and the /learnings command.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from muxi.runtime.formation.builtin_commands import BuiltinCommandContext, _cmd_learnings
from muxi.runtime.formation.overlord.overlord import Overlord
from muxi.runtime.services.db import Base, DatabaseManager
from muxi.runtime.services.memory.log.service import CaptainsLogService
from muxi.runtime.services.observability import spool as spool_module
from muxi.runtime.services.observability.spool import reset_event_spool
from muxi.runtime.services.tuning import ExperimentStore, MuxiMdFile, TuningConfig, TuningService
from muxi.runtime.services.tuning.experiments import STATUS_ACTIVE, STATUS_PENDING
from muxi.runtime.services.tuning.muxi_md import MUXI_MD_MAX_BYTES
from muxi.runtime.services.tuning.tuner import MAX_LEARNINGS_PER_RUN, TunerStep

FORMATION_ID = "tuner-test-formation"

DIGEST_RESPONSE = '{"summary": "Traffic was steady; one tool flaked.", "context": ""}'

TUNER_RESPONSE = json.dumps(
    {
        "muxi_md": "# Learnings\n\n- Back off the jira MCP during afternoon spikes.",
        "learnings": [
            {
                "learning": "Back off the jira MCP during afternoon spikes.",
                "evidence": "mcp.tool.failed clustered",
                "metric_key": "problem:mcp.tool.failed",
            }
        ],
        "recommendations": ["Consider a jira plan upgrade."],
    }
)


class SequencedModel:
    """generate_text returns queued responses in order (digest, tune)."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    async def generate_text(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return self.responses.pop(0) if self.responses else ""


class FakeRouter:
    def __init__(self):
        self.calls = []

    async def notify(self, *, user_id, message, channels=None, request_id=None, source, ui=None):
        self.calls.append({"user_id": user_id, "message": message, "source": source, "ui": ui})
        return {"request_id": "r", "channels": ["chan"], "delivered": ["chan"], "failed": []}


class FakeOverlord:
    def __init__(self, captains_log, muxi_md, router=None):
        self.captains_log = captains_log
        self.muxi_md = muxi_md
        self.notification_router = router


def spool_event(name="agent.processing", level="info", user_id=None, data=None):
    event = {"event": name, "level": level, "timestamp": 1783862400000}
    payload = dict(data or {})
    if user_id:
        payload["user_id"] = user_id
    if payload:
        event["data"] = payload
    return event


@pytest.fixture
def isolated_spool(tmp_path, monkeypatch):
    monkeypatch.setattr(spool_module, "_spool_dir", lambda: str(tmp_path / "spool"))
    reset_event_spool()
    yield spool_module.get_event_spool()
    reset_event_spool()


@pytest.fixture
def captains_log(tmp_path):
    manager = DatabaseManager(f"sqlite:///{tmp_path}/log.db")
    manager.create_tables(Base.metadata)
    yield CaptainsLogService(manager, FORMATION_ID)
    manager.engine.dispose()


def make_tuning(tmp_path, captains_log, auto_apply=True, router=None):
    formation_dir = tmp_path / "formation"
    formation_dir.mkdir(exist_ok=True)
    muxi_md = MuxiMdFile(str(formation_dir))
    overlord = FakeOverlord(captains_log, muxi_md, router)
    tuning = TuningService(TuningConfig(auto_apply=auto_apply), overlord)
    tuning.experiments_dir = str(tmp_path / "tuner")
    return tuning, muxi_md


class TestTunerStepParse:
    def test_valid_response(self):
        parsed = TunerStep().parse_response(TUNER_RESPONSE)
        assert parsed["muxi_md"].startswith("# Learnings")
        assert parsed["learnings"][0]["metric_key"] == "problem:mcp.tool.failed"
        assert parsed["recommendations"] == ["Consider a jira plan upgrade."]

    def test_fenced_response(self):
        parsed = TunerStep().parse_response(f"```json\n{TUNER_RESPONSE}\n```")
        assert parsed is not None
        assert len(parsed["learnings"]) == 1

    def test_garbage_parses_to_none(self):
        step = TunerStep()
        assert step.parse_response("not json") is None
        assert step.parse_response("") is None
        assert step.parse_response('["a list"]') is None

    def test_malformed_items_are_dropped_and_capped(self):
        payload = {
            "muxi_md": "",
            "learnings": [{"learning": f"L{i}"} for i in range(10)]
            + ["junk", {"evidence": "no learning"}],
            "recommendations": [f"R{i}" for i in range(10)] + [42],
        }
        parsed = TunerStep().parse_response(json.dumps(payload))
        assert parsed["muxi_md"] is None
        assert len(parsed["learnings"]) == MAX_LEARNINGS_PER_RUN
        assert all(item["metric_key"] is None for item in parsed["learnings"])
        assert len(parsed["recommendations"]) == 5

    def test_prompt_carries_every_input(self):
        prompt = TunerStep().build_prompt(
            activity_report="THE-REPORT",
            current_muxi_md="EXISTING-GUIDANCE",
            formation_log_block="LOG-BLOCK",
            active_learnings=[{"learning": "KEEP-ME", "metric_key": "error_rate"}],
            retired_learnings=[{"learning": "RETIRE-ME"}],
            dismissed_learnings=["NEVER-AGAIN"],
            metric_keys=["error_rate", "problem:mcp.tool.failed"],
            max_bytes=MUXI_MD_MAX_BYTES,
        )
        for needle in (
            "THE-REPORT",
            "EXISTING-GUIDANCE",
            "LOG-BLOCK",
            "KEEP-ME",
            "RETIRE-ME",
            "NEVER-AGAIN",
            "problem:mcp.tool.failed",
            str(MUXI_MD_MAX_BYTES),
        ):
            assert needle in prompt


class TestTuneStep:
    def test_auto_apply_writes_live_file_and_records_learnings(
        self, tmp_path, isolated_spool, captains_log
    ):
        router = FakeRouter()
        tuning, muxi_md = make_tuning(tmp_path, captains_log, auto_apply=True, router=router)
        isolated_spool.write_lines(
            [json.dumps(spool_event(name="mcp.tool.failed", level="warning"))]
        )

        result = asyncio.run(tuning.run_once(SequencedModel([DIGEST_RESPONSE, TUNER_RESPONSE])))

        assert result["muxi_md_applied"] is True
        assert result["muxi_md_suggested"] is False
        assert result["learnings_recorded"] == 1
        assert "jira MCP" in muxi_md.read()
        assert muxi_md.read_pending() is None

        store = ExperimentStore(tuning.experiments_dir)
        [record] = store.by_status(STATUS_ACTIVE)
        assert record["metric_key"] == "problem:mcp.tool.failed"
        assert record["baseline"] == 1.0  # the only event was the failure
        assert record["watch"]["opened_at"] is not None

        # Morning report delivered without a widget (nothing to approve).
        [call] = router.calls
        assert call["source"] == "tuning"
        assert call["ui"] is None
        assert "jira MCP" in call["message"]
        assert "Consider a jira plan upgrade." in call["message"]
        assert tuning.pending_widget is None

    def test_manual_mode_writes_pending_with_widget(self, tmp_path, isolated_spool, captains_log):
        router = FakeRouter()
        tuning, muxi_md = make_tuning(tmp_path, captains_log, auto_apply=False, router=router)
        muxi_md.write("hand-written")
        isolated_spool.write_lines([json.dumps(spool_event())])

        result = asyncio.run(tuning.run_once(SequencedModel([DIGEST_RESPONSE, TUNER_RESPONSE])))

        assert result["muxi_md_suggested"] is True
        assert result["muxi_md_applied"] is False
        assert muxi_md.read() == "hand-written"
        assert "jira MCP" in muxi_md.read_pending()

        store = ExperimentStore(tuning.experiments_dir)
        [record] = store.by_status(STATUS_PENDING)
        assert record["watch"]["opened_at"] is None

        [call] = router.calls
        assert call["ui"] is not None and call["ui"][0]["type"] == "options"
        assert [o["value"] for o in call["ui"][0]["options"]] == ["apply", "dismiss"]
        assert "/learnings apply" in call["message"]
        assert tuning.pending_widget == {
            "ui_id": call["ui"][0]["id"],
            "ui_options": ["apply", "dismiss"],
        }

    def test_privacy_lint_drops_user_lines_from_candidate(
        self, tmp_path, isolated_spool, captains_log
    ):
        tuning, muxi_md = make_tuning(tmp_path, captains_log, auto_apply=True)
        response = json.dumps(
            {
                "muxi_md": "# Learnings\n- alice keeps asking about invoices.\n- Back off jira.",
                "learnings": [],
                "recommendations": [],
            }
        )
        isolated_spool.write_lines([json.dumps(spool_event(user_id="alice"))])

        result = asyncio.run(tuning.run_once(SequencedModel([DIGEST_RESPONSE, response])))

        assert result["muxi_md_applied"] is True
        content = muxi_md.read()
        assert "alice" not in content
        assert "Back off jira." in content

    def test_empty_candidate_falls_back_to_appending_learnings(
        self, tmp_path, isolated_spool, captains_log
    ):
        tuning, muxi_md = make_tuning(tmp_path, captains_log, auto_apply=False)
        muxi_md.write("hand-written")
        response = json.dumps(
            {
                "muxi_md": "",
                "learnings": [
                    {
                        "learning": "Back off the jira MCP during afternoon spikes.",
                        "evidence": "clustered failures",
                        "metric_key": None,
                    }
                ],
                "recommendations": [],
            }
        )
        isolated_spool.write_lines([json.dumps(spool_event())])

        result = asyncio.run(tuning.run_once(SequencedModel([DIGEST_RESPONSE, response])))

        assert result["muxi_md_suggested"] is True
        assert muxi_md.read() == "hand-written"
        pending = muxi_md.read_pending()
        assert pending.startswith("hand-written")
        assert "- Back off the jira MCP during afternoon spikes." in pending

    def test_oversized_candidate_is_never_written(self, tmp_path, isolated_spool, captains_log):
        tuning, muxi_md = make_tuning(tmp_path, captains_log, auto_apply=True)
        response = json.dumps(
            {"muxi_md": "x" * (MUXI_MD_MAX_BYTES + 1), "learnings": [], "recommendations": []}
        )
        isolated_spool.write_lines([json.dumps(spool_event())])

        result = asyncio.run(tuning.run_once(SequencedModel([DIGEST_RESPONSE, response])))

        assert result["muxi_md_applied"] is False
        assert result["muxi_md_rejected_oversize"] is True
        assert muxi_md.read() is None

    def test_unparseable_tuner_response_skips_but_pass_commits(
        self, tmp_path, isolated_spool, captains_log
    ):
        tuning, muxi_md = make_tuning(tmp_path, captains_log)
        isolated_spool.write_lines([json.dumps(spool_event())])

        result = asyncio.run(tuning.run_once(SequencedModel([DIGEST_RESPONSE, "garbage"])))

        assert result["spool_committed"] is True
        assert result["tuner_skipped"] == "unparseable_response"
        assert muxi_md.read() is None

    def test_dismissed_idea_is_not_re_recorded(self, tmp_path, isolated_spool, captains_log):
        router = FakeRouter()
        tuning, muxi_md = make_tuning(tmp_path, captains_log, auto_apply=False, router=router)

        isolated_spool.write_lines([json.dumps(spool_event())])
        asyncio.run(tuning.run_once(SequencedModel([DIGEST_RESPONSE, TUNER_RESPONSE])))
        tuning.dismiss_pending()
        assert muxi_md.read_pending() is None

        # The tuner proposes the same idea again on the next pass.
        isolated_spool.write_lines([json.dumps(spool_event())])
        result = asyncio.run(tuning.run_once(SequencedModel([DIGEST_RESPONSE, TUNER_RESPONSE])))

        assert result["learnings_recorded"] == 0
        store = ExperimentStore(tuning.experiments_dir)
        assert len(store.records) == 1
        assert store.records[0]["status"] == "dismissed"

    def test_no_muxi_md_surface_skips_the_tune_step(self, isolated_spool, captains_log):
        overlord = FakeOverlord(captains_log, muxi_md=None)
        tuning = TuningService(TuningConfig(), overlord)
        isolated_spool.write_lines([json.dumps(spool_event())])

        result = asyncio.run(tuning.run_once(SequencedModel([DIGEST_RESPONSE])))
        assert result["spool_committed"] is True
        assert "muxi_md_applied" not in result


class TestPendingSurfaces:
    def _suggested(self, tmp_path, captains_log):
        tuning, muxi_md = make_tuning(tmp_path, captains_log, auto_apply=False)
        muxi_md.write_pending("# Suggested\n- Learning.")
        store = ExperimentStore(tuning.experiments_dir)
        store.propose("Learning.", "e", None, None, STATUS_PENDING)
        store.save()
        tuning.pending_widget = {"ui_id": "ui_x", "ui_options": ["apply", "dismiss"]}
        return tuning, muxi_md

    def test_apply_pending_promotes_and_activates(self, tmp_path, captains_log):
        tuning, muxi_md = self._suggested(tmp_path, captains_log)
        result = tuning.apply_pending()

        assert result["learnings_activated"] == 1
        assert muxi_md.read() == "# Suggested\n- Learning."
        assert muxi_md.read_pending() is None
        assert tuning.pending_widget is None
        store = ExperimentStore(tuning.experiments_dir)
        assert store.records[0]["status"] == STATUS_ACTIVE

    def test_dismiss_pending_discards_and_remembers(self, tmp_path, captains_log):
        tuning, muxi_md = self._suggested(tmp_path, captains_log)
        result = tuning.dismiss_pending()

        assert result["learnings_dismissed"] == 1
        assert muxi_md.read() is None
        assert muxi_md.read_pending() is None
        assert tuning.pending_widget is None

    def test_apply_without_pending_raises(self, tmp_path, captains_log):
        tuning, _ = make_tuning(tmp_path, captains_log)
        with pytest.raises(ValueError, match="No pending"):
            tuning.apply_pending()
        with pytest.raises(ValueError, match="No pending"):
            tuning.dismiss_pending()


class TestMuxiMdPending:
    def test_pending_roundtrip_and_promote(self, tmp_path):
        muxi_md = MuxiMdFile(str(tmp_path))
        muxi_md.write("live")
        assert muxi_md.read_pending() is None
        muxi_md.write_pending("suggested")
        assert muxi_md.read_pending() == "suggested"
        assert muxi_md.read() == "live"

        path = muxi_md.promote_pending()
        assert path.endswith("MUXI.md")
        assert muxi_md.read() == "suggested"
        assert muxi_md.read_pending() is None

    def test_discard_pending(self, tmp_path):
        muxi_md = MuxiMdFile(str(tmp_path))
        assert muxi_md.discard_pending() is False
        muxi_md.write_pending("suggested")
        assert muxi_md.discard_pending() is True
        assert muxi_md.read_pending() is None

    def test_promote_without_pending_raises(self, tmp_path):
        with pytest.raises(ValueError, match="No pending"):
            MuxiMdFile(str(tmp_path)).promote_pending()

    def test_pending_without_directory_raises(self):
        with pytest.raises(ValueError, match="no directory"):
            MuxiMdFile(None).write_pending("content")


class TestTuningUiIntercept:
    def _fake_overlord(self, tuning):
        return SimpleNamespace(tuning_service=tuning)

    def test_apply_button_press(self, tmp_path, captains_log):
        tuning, muxi_md = make_tuning(tmp_path, captains_log)
        muxi_md.write_pending("suggested")
        store = ExperimentStore(tuning.experiments_dir)
        store.propose("Learning.", "e", None, None, STATUS_PENDING)
        store.save()
        tuning.pending_widget = {"ui_id": "ui_abc", "ui_options": ["apply", "dismiss"]}

        response = Overlord._process_tuning_ui_response(
            self._fake_overlord(tuning), {"id": "ui_abc", "value": "apply"}
        )
        assert response is not None
        assert "Applied" in response.content
        assert muxi_md.read() == "suggested"
        assert tuning.pending_widget is None

    def test_dismiss_button_press(self, tmp_path, captains_log):
        tuning, muxi_md = make_tuning(tmp_path, captains_log)
        muxi_md.write_pending("suggested")
        tuning.pending_widget = {"ui_id": "ui_abc", "ui_options": ["apply", "dismiss"]}

        response = Overlord._process_tuning_ui_response(
            self._fake_overlord(tuning), {"id": "ui_abc", "index": 1}
        )
        assert response is not None
        assert "Dismissed" in response.content
        assert muxi_md.read_pending() is None

    def test_unknown_widget_falls_through(self, tmp_path, captains_log):
        tuning, _ = make_tuning(tmp_path, captains_log)
        tuning.pending_widget = {"ui_id": "ui_abc", "ui_options": ["apply", "dismiss"]}
        fake = self._fake_overlord(tuning)

        assert (
            Overlord._process_tuning_ui_response(fake, {"id": "ui_other", "value": "apply"}) is None
        )
        assert Overlord._process_tuning_ui_response(fake, None) is None
        tuning.pending_widget = None
        assert (
            Overlord._process_tuning_ui_response(fake, {"id": "ui_abc", "value": "apply"}) is None
        )

    def test_no_tuning_service_falls_through(self):
        fake = SimpleNamespace(tuning_service=None)
        assert (
            Overlord._process_tuning_ui_response(fake, {"id": "ui_abc", "value": "apply"}) is None
        )


class TestLearningsCommand:
    def _ctx(self, overlord, args=""):
        return BuiltinCommandContext(
            overlord=overlord, user_id="0", session_id="s", args=args, config=None
        )

    def _overlord(self, tmp_path, captains_log, multi_user=False):
        tuning, muxi_md = make_tuning(tmp_path, captains_log)
        overlord = SimpleNamespace(muxi_md=muxi_md, tuning_service=tuning, is_multi_user=multi_user)
        tuning.overlord = overlord
        return overlord

    def test_show_without_file(self, tmp_path, captains_log):
        overlord = self._overlord(tmp_path, captains_log)
        reply = asyncio.run(_cmd_learnings(self._ctx(overlord)))
        assert "No MUXI.md exists yet" in reply

    def test_show_with_live_and_pending(self, tmp_path, captains_log):
        overlord = self._overlord(tmp_path, captains_log)
        overlord.muxi_md.write("# Learnings\n- Live guidance.")
        overlord.muxi_md.write_pending("# Suggested")
        reply = asyncio.run(_cmd_learnings(self._ctx(overlord)))
        assert "Live guidance." in reply
        assert "/learnings pending" in reply

    def test_pending_view(self, tmp_path, captains_log):
        overlord = self._overlord(tmp_path, captains_log)
        reply = asyncio.run(_cmd_learnings(self._ctx(overlord, "pending")))
        assert "no pending" in reply.lower()
        overlord.muxi_md.write_pending("# Suggested")
        reply = asyncio.run(_cmd_learnings(self._ctx(overlord, "pending")))
        assert "# Suggested" in reply

    def test_apply_and_dismiss(self, tmp_path, captains_log):
        overlord = self._overlord(tmp_path, captains_log)
        overlord.muxi_md.write_pending("# Suggested")
        reply = asyncio.run(_cmd_learnings(self._ctx(overlord, "apply")))
        assert "Applied" in reply
        assert overlord.muxi_md.read() == "# Suggested"

        overlord.muxi_md.write_pending("# Another")
        reply = asyncio.run(_cmd_learnings(self._ctx(overlord, "dismiss")))
        assert "Dismissed" in reply
        assert overlord.muxi_md.read_pending() is None

    def test_apply_without_pending_is_friendly(self, tmp_path, captains_log):
        overlord = self._overlord(tmp_path, captains_log)
        reply = asyncio.run(_cmd_learnings(self._ctx(overlord, "apply")))
        assert "Could not apply" in reply

    def test_mutating_verbs_refused_in_multi_user(self, tmp_path, captains_log):
        overlord = self._overlord(tmp_path, captains_log, multi_user=True)
        overlord.muxi_md.write_pending("# Suggested")
        reply = asyncio.run(_cmd_learnings(self._ctx(overlord, "apply")))
        assert "multi-user" in reply
        assert overlord.muxi_md.read_pending() == "# Suggested"

    def test_bad_action_shows_usage(self, tmp_path, captains_log):
        overlord = self._overlord(tmp_path, captains_log)
        reply = asyncio.run(_cmd_learnings(self._ctx(overlord, "bogus")))
        assert reply.startswith("Usage:")

    def test_no_surface(self):
        overlord = SimpleNamespace(muxi_md=None)
        reply = asyncio.run(_cmd_learnings(self._ctx(overlord)))
        assert "not available" in reply
