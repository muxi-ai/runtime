"""Integration tests for the formation-init model probe.

End-to-end behavior tests for ``probe_declared_models()`` using real
OneLLM calls per the project's "no mocks" standard
(``AGENTS.md``: "Use real services... mocks are disallowed").

What is covered here:

- The dev's exact failure (``local/all-MiniLM-L6-v2``) hitting real
  HuggingFace, surfacing a real 404 / repository-not-found, and
  producing the bare-name owner/repo correction hint. This case
  needs **no API key** - HF rejects bare repo ids without auth.
- A typo'd cloud slug (``openai/gpt-4o-min``) hitting real OpenAI
  and surfacing a real 404 with the cloud-typo hint.
- A valid cloud slug (``openai/gpt-4o-mini``) succeeding through to
  the next probe.
- Authentication errors (set a deliberately bogus key) being
  classified as warn-and-continue rather than fatal.
- Serial fail-fast: when probe #1 fails fatally, probe #2 is
  observably never invoked (witnessed via the error message
  referencing slug-1 only).

What lives elsewhere:

- Pure-function tests (classification, level mapping, message
  formatting, probe-builder dedup) live in
  ``tests/unit/test_model_init_probe.py`` and run without network.

Skip semantics:

- Tests that need OpenAI auth skip via ``pytest.mark.skipif`` when
  ``OPENAI_API_KEY`` is not set in the environment.
- The bare-name local case has no skip - HF refuses the lookup
  immediately without any credential.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from muxi.runtime.datatypes.exceptions import ConfigurationValidationError
from muxi.runtime.formation import initialization as init_mod

pytestmark = [pytest.mark.slow, pytest.mark.integration]


_NEEDS_OPENAI = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY required for real OpenAI probes",
)


def _make_formation(capability_models: dict) -> SimpleNamespace:
    """Build a minimal formation stand-in with just the field the probe reads.

    The probe only touches ``formation._capability_models``; nothing
    else from the Formation surface is needed. Using a SimpleNamespace
    keeps these tests independent of the full Formation lifecycle
    (load, observability bootstrap, secrets manager, etc.) so a
    failure here always points at probe behavior rather than a
    formation-load orthogonal regression.
    """
    return SimpleNamespace(_capability_models=capability_models)


# ---------------------------------------------------------------------------
# Local-provider path: needs no API key. HuggingFace rejects bare repo ids.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bare_name_local_slug_aborts_with_owner_hint_real_hf():
    """The dev's exact failure path: bare-name slug -> real HF 404 ->
    fatal abort with the canonical-form correction in the message.

    No API key required: HuggingFace does not need credentials to
    answer "this repo doesn't exist" for ``all-MiniLM-L6-v2`` (which
    OneLLM passes verbatim because its dispatcher splits on the first
    ``/`` only).
    """
    formation = _make_formation({"embedding": {"model": "local/all-MiniLM-L6-v2"}})

    with pytest.raises(ConfigurationValidationError) as excinfo:
        await init_mod.probe_declared_models(formation)

    msg = str(excinfo.value)
    # The offending slug appears verbatim in the error.
    assert "local/all-MiniLM-L6-v2" in msg
    # The fatal-message formatter detected the bare-name shape and
    # surfaced the canonical correction.
    assert "local/sentence-transformers/all-MiniLM-L6-v2" in msg
    assert "owner/organization" in msg


@pytest.mark.asyncio
async def test_local_owner_repo_slug_404_uses_typo_hint_real_hf():
    """A well-shaped local slug whose repo simply doesn't exist
    surfaces the typo / gated-repo hint, NOT the bare-name hint.

    Distinguishes "shape error" (no slash) from "404 on a real
    HF lookup", which produce different operator-actionable hints.
    """
    formation = _make_formation(
        {"embedding": {"model": "local/muxi-probe-tests-doesnotexist/some-fake-model"}}
    )

    with pytest.raises(ConfigurationValidationError) as excinfo:
        await init_mod.probe_declared_models(formation)

    msg = str(excinfo.value)
    assert "muxi-probe-tests-doesnotexist/some-fake-model" in msg
    # Not the bare-name hint.
    assert "owner/organization" not in msg
    # The local-but-shaped-OK hint set instead.
    assert "Common causes for local/* slugs" in msg


@pytest.mark.asyncio
async def test_first_fatal_aborts_before_second_probe_runs_real_hf():
    """Witness for serial fail-fast without mocking the call layer.

    Two distinct bad local slugs; the probe runs serially in
    insertion order, so when ``embedding`` fatals first, the ``text``
    probe (which would also have surfaced its own 404) must never
    execute. The witness is the error message: it names the FIRST
    slug only. If the second probe ever ran, its slug would also
    appear somewhere in the error chain.
    """
    formation = _make_formation(
        {
            # Bare-name -> guaranteed fatal on real HF lookup.
            "embedding": {"model": "local/all-MiniLM-L6-v2"},
            # Different bad slug; would also fatal if reached.
            "text": {"model": "local/muxi-probe-tests-second/should-never-run"},
        }
    )

    with pytest.raises(ConfigurationValidationError) as excinfo:
        await init_mod.probe_declared_models(formation)

    msg = str(excinfo.value)
    assert "local/all-MiniLM-L6-v2" in msg
    # The second probe never ran, so its slug must not surface in
    # the error chain.
    assert "muxi-probe-tests-second" not in msg
    assert "should-never-run" not in msg


@pytest.mark.asyncio
async def test_empty_capability_models_is_a_noop():
    """No declared models -> no probes -> no exception.

    Trivially safe: validates that the probe handles an empty
    registry without surprising the caller.
    """
    formation = _make_formation({})
    # Must not raise.
    await init_mod.probe_declared_models(formation)


# ---------------------------------------------------------------------------
# Cloud-provider path: needs a real OPENAI_API_KEY to reach OpenAI 404 / 200.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_NEEDS_OPENAI
async def test_cloud_typo_aborts_with_404_real_openai():
    """A typo'd cloud slug hitting real OpenAI surfaces ResourceNotFoundError
    with the cloud-typo hint, not a local-specific hint.
    """
    formation = _make_formation({"text": {"model": "openai/gpt-4o-min"}})  # missing trailing 'i'

    with pytest.raises(ConfigurationValidationError) as excinfo:
        await init_mod.probe_declared_models(formation)

    msg = str(excinfo.value)
    assert "openai/gpt-4o-min" in msg
    assert "Common causes for cloud slugs" in msg
    # Cloud-only error: no local hints leak in.
    assert "local/<owner>/<repo>" not in msg
    assert "HuggingFace" not in msg


@pytest.mark.asyncio
@_NEEDS_OPENAI
async def test_valid_cloud_slug_succeeds_real_openai():
    """A valid cloud slug must NOT raise.

    Sanity for the happy path: probe makes a real 1-token chat call,
    returns successfully, formation init proceeds. Fractions of a
    cent per run.
    """
    formation = _make_formation({"text": {"model": "openai/gpt-4o-mini"}})
    # Must not raise.
    await init_mod.probe_declared_models(formation)


@pytest.mark.asyncio
async def test_authentication_error_warns_and_continues_real_openai():
    """A bad API key surfaces ``AuthenticationError`` from real
    OpenAI - which is classified ``"warn"`` and must NOT abort
    formation init.

    Saves and restores any existing key so this test plays nicely
    with subsequent integration tests in the same session.
    """
    from onellm.config import set_api_key

    original = os.environ.get("OPENAI_API_KEY")
    set_api_key(
        "sk-deliberately-invalid-test-key-for-probe-warning-suppression",
        "openai",
    )
    try:
        formation = _make_formation({"text": {"model": "openai/gpt-4o-mini"}})
        # Must not raise: AuthenticationError is in the warn-and-continue
        # bucket (we cannot reliably distinguish missing vs invalid key
        # from the error class alone).
        await init_mod.probe_declared_models(formation)
    finally:
        if original:
            set_api_key(original, "openai")
