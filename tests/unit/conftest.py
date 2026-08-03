"""Unit-suite-wide guards.

Every emitted observability event is teed into the event spool (Self-
Improving Formation), so any test that logs would otherwise write real
segment files under ``~/.muxi``. Redirect the spool singleton into the
test's tmp_path for the whole unit suite.
"""

import pytest

from muxi.runtime.services import db as db_module
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


@pytest.fixture(autouse=True)
async def _dispose_async_db_engines(monkeypatch):
    """Dispose every async engine a DatabaseManager creates during a test.

    DatabaseManager builds its async engine lazily, and each pooled
    aiosqlite connection owns a dedicated worker thread. Test fixtures
    dispose the sync engine on teardown but historically leaked the async
    one, so those worker threads outlived their event loop -- spamming
    "Event loop is closed" at GC time and accumulating threads across the
    suite. Track engine creation here and dispose on teardown, while the
    test's event loop is still open so connections close on the loop that
    created them. Disposing an engine the test already closed is a no-op.
    """
    engines = []
    original_create = db_module.DatabaseManager._create_async_engine

    def _tracking_create(self):
        engine = original_create(self)
        engines.append(engine)
        return engine

    monkeypatch.setattr(db_module.DatabaseManager, "_create_async_engine", _tracking_create)
    yield
    for engine in engines:
        await engine.dispose()
