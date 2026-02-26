#!/usr/bin/env python3
"""
LLM-as-Judge evaluation utility for e2e tests.

Usage:
    from utils.evals import evaluate, EvalResult

    result = evaluate(
        prompt="What is MUXI?",
        response=actual_response,
        expected="Explains MUXI as an AI agent platform with formations",
        assertions={"agent_used": "muxi-expert", "min_length": 50},
    )
    assert result.passed, result.reason
"""

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from onellm import ChatCompletion

EVAL_MODEL = "openai/gpt-4o-mini"
PASS_THRESHOLD = 7

JUDGE_SYSTEM = """You are a strict but fair evaluation judge for an AI agent platform.
You score responses on a 1-10 scale based on how well they match expected behavior.

Scoring guide:
- 10: Perfect match, exceeds expectations
- 8-9: Strong match, covers all key points
- 7: Acceptable, covers most key points
- 5-6: Partial match, missing important aspects
- 3-4: Weak match, mostly off-topic
- 1-2: Complete failure or refusal

You MUST return ONLY a JSON object with no markdown fencing:
{"score": N, "reason": "one sentence explanation"}"""

JUDGE_TEMPLATE = """Evaluate this AI agent response.

User prompt: {prompt}

Actual response:
{response}

Expected behavior: {expected}

Return ONLY: {{"score": N, "reason": "..."}}"""


@dataclass
class EvalResult:
    score: float
    reason: str
    passed: bool
    eval_time_ms: float
    assertion_failures: list = field(default_factory=list)

    def __repr__(self):
        status = "PASS" if self.passed else "FAIL"
        parts = [f"[{status}] score={self.score}/10 ({self.reason})"]
        if self.assertion_failures:
            parts.append(f"  assertion failures: {self.assertion_failures}")
        return "\n".join(parts)


def _check_assertions(
    response: str,
    assertions: dict,
    response_obj: Any = None,
) -> list:
    """Run structural assertions. Returns list of failure messages."""
    failures = []

    if "min_length" in assertions:
        if len(response) < assertions["min_length"]:
            failures.append(
                f"min_length: got {len(response)}, expected >= {assertions['min_length']}"
            )

    if "max_length" in assertions:
        if len(response) > assertions["max_length"]:
            failures.append(
                f"max_length: got {len(response)}, expected <= {assertions['max_length']}"
            )

    if "contains" in assertions:
        for term in assertions["contains"]:
            if term.lower() not in response.lower():
                failures.append(f"contains: '{term}' not found in response")

    if "not_contains" in assertions:
        for term in assertions["not_contains"]:
            if term.lower() in response.lower():
                failures.append(f"not_contains: '{term}' found in response")

    if "agent_used" in assertions and response_obj is not None:
        actual_agent = getattr(response_obj, "agent_used", None) or getattr(
            response_obj, "agent_id", None
        )
        if actual_agent and actual_agent != assertions["agent_used"]:
            failures.append(
                f"agent_used: got '{actual_agent}', expected '{assertions['agent_used']}'"
            )

    if "has_artifacts" in assertions and response_obj is not None:
        artifacts = getattr(response_obj, "artifacts", None) or []
        if assertions["has_artifacts"] and not artifacts:
            failures.append("has_artifacts: no artifacts found")
        elif not assertions["has_artifacts"] and artifacts:
            failures.append(f"has_artifacts: unexpected {len(artifacts)} artifacts")

    if "artifact_count" in assertions and response_obj is not None:
        artifacts = getattr(response_obj, "artifacts", None) or []
        if len(artifacts) != assertions["artifact_count"]:
            failures.append(
                f"artifact_count: got {len(artifacts)}, expected {assertions['artifact_count']}"
            )

    if "response_time_ms" in assertions and response_obj is not None:
        actual_time = getattr(response_obj, "processing_time_ms", None)
        if actual_time and actual_time > assertions["response_time_ms"]:
            failures.append(
                f"response_time_ms: got {actual_time:.0f}ms, "
                f"expected <= {assertions['response_time_ms']}ms"
            )

    return failures


async def aevaluate(
    prompt: str,
    response: str,
    expected: str,
    assertions: Optional[dict] = None,
    response_obj: Any = None,
    threshold: int = PASS_THRESHOLD,
    model: str = EVAL_MODEL,
) -> EvalResult:
    """Async LLM-as-judge evaluation."""
    t0 = time.time()

    assertion_failures = []
    if assertions:
        assertion_failures = _check_assertions(response, assertions, response_obj)

    judge_prompt = JUDGE_TEMPLATE.format(
        prompt=prompt,
        response=response[:2000],
        expected=expected,
    )

    try:
        resp = await ChatCompletion.acreate(
            model=model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": judge_prompt},
            ],
            max_tokens=1024,
            temperature=0.0,
        )
        raw = resp.choices[0].message["content"].strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw)
        score = float(parsed["score"])
        reason = parsed.get("reason", "")
    except Exception as e:
        score = 0
        reason = f"Eval failed: {e}"

    eval_time = (time.time() - t0) * 1000
    passed = score >= threshold and len(assertion_failures) == 0

    return EvalResult(
        score=score,
        reason=reason,
        passed=passed,
        eval_time_ms=eval_time,
        assertion_failures=assertion_failures,
    )


def evaluate(
    prompt: str,
    response: str,
    expected: str,
    assertions: Optional[dict] = None,
    response_obj: Any = None,
    threshold: int = PASS_THRESHOLD,
    model: str = EVAL_MODEL,
) -> EvalResult:
    """Synchronous wrapper for aevaluate."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(
                asyncio.run,
                aevaluate(prompt, response, expected, assertions, response_obj, threshold, model),
            ).result()
    else:
        return asyncio.run(
            aevaluate(prompt, response, expected, assertions, response_obj, threshold, model)
        )


if __name__ == "__main__":
    result = evaluate(
        prompt="What can you help me with?",
        response="I can help you with coding, research, writing, and analysis. What do you need?",
        expected="Should offer to help with various tasks and be welcoming",
        assertions={"min_length": 20, "contains": ["help"]},
    )
    print(result)
    print(f"  eval_time: {result.eval_time_ms:.0f}ms")
