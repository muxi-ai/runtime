"""
Regression tests for the prompt rewriter's "LLM returned unchanged" handling.

Background: rewrite_for_execution used to treat ``rewritten == original_prompt``
as an LLM failure and wrap the prompt with ``"Execute scheduled task: "``. The
rewriter prompt explicitly tells the LLM to return the input unchanged when
there are no timing words to strip, so equality is a *success* signal, not a
failure. Wrapping a clean prompt as a fallback caused recursive scheduling
when an agent looped its own execution_prompt back through create_job.
"""

from unittest.mock import AsyncMock

import pytest

from muxi.runtime.services.scheduler.rewriter import PromptRewriter


@pytest.fixture(autouse=True)
def _stub_prompt_loader(monkeypatch):
    """The rewriter loads its system prompt via PromptLoader at runtime;
    these tests don't care about the prompt content because the LLM is
    fully mocked. Stub the loader so tests don't need a full app bootstrap.
    """
    monkeypatch.setattr(
        "muxi.runtime.formation.prompts.loader.PromptLoader.get",
        staticmethod(lambda *_args, **_kwargs: "stub-prompt"),
    )


def _rewriter_with_llm_response(text: str) -> PromptRewriter:
    rewriter = PromptRewriter()
    fake_llm = AsyncMock()
    fake_llm.generate_text = AsyncMock(return_value=text)
    rewriter.llm = fake_llm
    return rewriter


@pytest.mark.asyncio
async def test_unchanged_llm_output_is_returned_verbatim():
    """LLM returning the input unchanged means 'nothing to strip' — keep it."""
    rewriter = _rewriter_with_llm_response("remind me to drink coffee")

    result = await rewriter.rewrite_for_execution("remind me to drink coffee")

    assert result == "remind me to drink coffee"
    assert "Execute scheduled task" not in result


@pytest.mark.asyncio
async def test_empty_llm_output_falls_back_to_prefix():
    """Real failure — empty response — falls back to the prefix wrapping."""
    rewriter = _rewriter_with_llm_response("   ")

    result = await rewriter.rewrite_for_execution("remind me to drink coffee")

    assert result == "Execute scheduled task: remind me to drink coffee"


@pytest.mark.asyncio
async def test_normal_rewrite_strips_timing():
    """Normal rewriting: LLM returns the prompt with timing removed."""
    rewriter = _rewriter_with_llm_response("remind me to drink coffee")

    result = await rewriter.rewrite_for_execution("remind me to drink coffee every 3 minutes")

    assert result == "remind me to drink coffee"


@pytest.mark.asyncio
async def test_surrounding_quotes_are_stripped():
    """LLMs sometimes add quotes despite the prompt saying not to."""
    rewriter = _rewriter_with_llm_response('"remind me to drink coffee"')

    result = await rewriter.rewrite_for_execution("remind me to drink coffee every 3 minutes")

    assert result == "remind me to drink coffee"


@pytest.mark.asyncio
async def test_llm_unavailable_returns_original(monkeypatch):
    """When no LLM is configured, fall back to returning the original prompt."""
    rewriter = PromptRewriter()
    rewriter.llm = None

    def _raise(*_args, **_kwargs):
        raise RuntimeError("no LLM configured for test")

    monkeypatch.setattr("muxi.runtime.services.scheduler.rewriter.LLM", _raise)

    result = await rewriter.rewrite_for_execution("remind me to drink coffee")

    assert result == "remind me to drink coffee"
