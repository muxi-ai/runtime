"""Unit-suite-wide guards.

Every emitted observability event is teed into the event spool (Self-
Improving Formation), so any test that logs would otherwise write real
segment files under ``~/.muxi``. Redirect the spool singleton into the
test's tmp_path for the whole unit suite.
"""

import pytest

from muxi.runtime.services.observability import spool as spool_module
from muxi.runtime.services.observability.spool import reset_event_spool
from muxi.runtime.services.tuning import experiments as experiments_module


@pytest.fixture(autouse=True)
def _isolated_event_spool(tmp_path, monkeypatch):
    monkeypatch.setattr(spool_module, "_spool_dir", lambda: str(tmp_path / "event-spool"))
    monkeypatch.setattr(
        experiments_module, "_default_experiments_dir", lambda: str(tmp_path / "tuner")
    )
    reset_event_spool()
    yield
    reset_event_spool()
