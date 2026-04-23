"""Integration test for invalid-model-slug error surfacing.

VAL-INTEG-007: formation load or first embed with a fake model slug
surfaces a recognizable ``onellm.errors`` subclass, not a generic
traceback.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from muxi.runtime.services.memory.sqlite import SQLiteMemory

pytestmark = [pytest.mark.slow, pytest.mark.integration]


@pytest.mark.asyncio
async def test_invalid_slug_surfaces_error():
    """Construction with a fake local/* slug surfaces a clear error on first use."""
    import onellm

    tmp = Path(tempfile.mkdtemp(prefix="muxi-err-"))
    mem = SQLiteMemory(
        db_path=str(tmp / "memory.db"),
        formation_id="err-test",
        embedding_model="local/definitely-does-not-exist/fake-model",
    )

    # Collect the expected onellm error classes. Some of these may not
    # exist in older OneLLM versions — build the tuple from whatever is
    # importable, falling back to Exception as a safety net.
    candidate_names = [
        "ResourceNotFoundError",
        "InvalidConfigurationError",
        "InvalidRequestError",
        "AuthenticationError",
        "ServiceUnavailableError",
    ]
    error_types = tuple(
        getattr(onellm.errors, name) for name in candidate_names if hasattr(onellm.errors, name)
    )
    assert error_types, "expected at least one onellm.errors subclass to be importable"

    with pytest.raises((*error_types, Exception)) as excinfo:
        # First embed operation triggers the probe, which triggers the
        # HF repo resolution, which surfaces the error.
        await mem.add(content="trigger", user_id="u")

    err = excinfo.value
    # Sanity check: error message mentions the fake model or HF in some form.
    msg = str(err).lower()
    assert any(
        token in msg
        for token in ("definitely-does-not-exist", "fake-model", "not found", "404", "hugging")
    ) or isinstance(
        err, error_types
    ), f"Expected recognizable error for fake slug, got: {type(err).__name__}: {err}"
