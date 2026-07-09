"""Cost-runner QA-phase accounting tests (stubbed adapter, no formation)."""

import pytest

from bench.memory.cost_runner import _qa_phase
from bench.memory.datasets import Question


class _StubAdapter:
    """Deterministic answer/judge stub with a controllable failure script.

    ``script`` maps question_id -> "ok" | "wrong" | "answer_fail" |
    "judge_fail". Every answer call consumes 100 tokens.
    """

    def __init__(self, script):
        self.script = script
        self.tokens = 0

    async def search_question(self, user_id, question, fetch_limit):
        return []

    def usage_snapshot(self):
        return {"tokens": {"total": self.tokens}}

    async def answer_question(self, question, items, context_limit):
        if self.script[question.question_id] == "answer_fail":
            raise RuntimeError("answer call failed")
        self.tokens += 100
        return "predicted"

    async def judge_answer(self, question, predicted):
        outcome = self.script[question.question_id]
        if outcome == "judge_fail":
            raise RuntimeError("judge call failed")
        return outcome == "ok"


def _questions(ids):
    return [
        (
            "user",
            Question(
                question_id=question_id,
                question="q?",
                answer="a",
                question_type="kg_relationship",
            ),
        )
        for question_id in ids
    ]


class TestQAPhase:
    @pytest.mark.asyncio
    async def test_all_success(self):
        adapter = _StubAdapter({"q1": "ok", "q2": "wrong"})
        block = await _qa_phase(adapter, _questions(["q1", "q2"]), 10, 5)
        assert block["questions"] == 2
        assert block["correct"] == 1
        assert block["errors"] == 0
        assert block["answer_tokens"] == 200
        assert block["tokens_per_accurate_recall"] == 200.0

    @pytest.mark.asyncio
    async def test_judge_failure_excluded_from_both_tallies(self):
        # q2's answer call succeeds (tokens consumed on the wire) but the
        # judge fails: the question must NOT contribute its answer tokens
        # to the numerator, NOT count in the denominator, and land in
        # errors — otherwise tokens-per-accurate-recall is inflated.
        adapter = _StubAdapter({"q1": "ok", "q2": "judge_fail"})
        block = await _qa_phase(adapter, _questions(["q1", "q2"]), 10, 5)
        assert block["questions"] == 1
        assert block["correct"] == 1
        assert block["errors"] == 1
        assert block["answer_tokens"] == 100  # q2's 100 wire tokens excluded
        assert block["tokens_per_accurate_recall"] == 100.0

    @pytest.mark.asyncio
    async def test_answer_failure_counts_as_error(self):
        adapter = _StubAdapter({"q1": "answer_fail", "q2": "ok"})
        block = await _qa_phase(adapter, _questions(["q1", "q2"]), 10, 5)
        assert block["questions"] == 1
        assert block["errors"] == 1
        assert block["answer_tokens"] == 100

    @pytest.mark.asyncio
    async def test_no_correct_answers_yields_null_ratio(self):
        adapter = _StubAdapter({"q1": "wrong"})
        block = await _qa_phase(adapter, _questions(["q1"]), 10, 5)
        assert block["tokens_per_accurate_recall"] is None
        assert block["accuracy"] == 0.0

    @pytest.mark.asyncio
    async def test_all_failed_yields_null_accuracy(self):
        adapter = _StubAdapter({"q1": "judge_fail"})
        block = await _qa_phase(adapter, _questions(["q1"]), 10, 5)
        assert block["questions"] == 0
        assert block["accuracy"] is None
        assert block["errors"] == 1
