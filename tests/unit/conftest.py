"""Unit-suite-wide guards.

Every emitted observability event is teed into the event spool (Self-
Improving Formation), so any test that logs would otherwise write real
segment files under ``~/.muxi``. Redirect the spool singleton into the
test's tmp_path for the whole unit suite.

A handful of tests embed text with real local ONNX models downloaded
from the HuggingFace Hub (``Xenova/multilingual-e5-small`` for the
classifier, ``nomic-ai/nomic-embed-text-v1.5`` for sops search). When
the Hub is unreachable — rate limits, transient Xet CAS bridge 403s —
those downloads fail. Per project policy the model download is an
ancillary service, so we convert such failures to skips centrally rather
than red-failing CI, while genuine logic bugs still surface loudly.
"""

import pytest

from muxi.runtime.services.observability import spool as spool_module
from muxi.runtime.services.observability.spool import reset_event_spool
from muxi.runtime.services.tuning import experiments as experiments_module

# Substrings that unambiguously mark a HuggingFace / model-download
# transport failure (as opposed to a classification/logic bug).
_MODEL_DOWNLOAD_MARKERS = (
    "huggingface",
    "hf.co",
    "xethub",
    "xet-bridge",
    "accessdenied",
    "403 forbidden",
    "make sure your token",
    "too many requests",
    "rate limit",
    "connection reset",
    "temporarily unavailable",
    "name or service not known",
    "failed to establish a new connection",
)

# Network / transport modules and onellm transport-error names. A local
# ONNX model has no API auth, so these from a local model can only mean
# the Hub fetch failed — safe to treat as "model unavailable".
_NETWORK_MODULES = ("huggingface_hub", "requests", "httpx", "urllib3", "socket", "hf_xet")
_ONELLM_TRANSPORT_ERRORS = (
    "PermissionDeniedError",
    "RateLimitError",
    "RequestTimeoutError",
    "ServiceUnavailableError",
    "BadGatewayError",
    "AuthenticationError",
    "ResourceNotFoundError",
)


def _is_model_download_error(exc: BaseException) -> bool:
    """Walk the exception chain and flag failures that stem from an
    unreachable HuggingFace Hub / model download."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        module = type(current).__module__.split(".")[0]
        name = type(current).__name__
        if module in _NETWORK_MODULES:
            return True
        if module == "onellm" and name in _ONELLM_TRANSPORT_ERRORS:
            return True
        if isinstance(current, (ConnectionError, TimeoutError)):
            return True
        message = str(current).lower()
        if any(marker in message for marker in _MODEL_DOWNLOAD_MARKERS):
            return True
        current = current.__cause__ or current.__context__
    return False


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item):
    try:
        return (yield)
    except Exception as exc:
        if _is_model_download_error(exc):
            pytest.skip(f"model download unavailable (HuggingFace Hub): {exc}")
        raise


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    try:
        return (yield)
    except Exception as exc:
        if _is_model_download_error(exc):
            pytest.skip(f"model download unavailable (HuggingFace Hub): {exc}")
        raise


@pytest.fixture(autouse=True)
def _isolated_event_spool(tmp_path, monkeypatch):
    monkeypatch.setattr(spool_module, "_spool_dir", lambda: str(tmp_path / "event-spool"))
    monkeypatch.setattr(
        experiments_module, "_default_experiments_dir", lambda: str(tmp_path / "tuner")
    )
    reset_event_spool()
    yield
    reset_event_spool()
