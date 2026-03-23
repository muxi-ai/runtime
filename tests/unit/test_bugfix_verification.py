"""
Verification tests for bugfixes:
- Scheduler route handlers access scheduler via overlord (not formation._scheduler)
- Memobase exposes .dimension from inner LongTermMemory
- Memobase fallback path in initialization creates LongTermMemory correctly
"""

import inspect
from pathlib import Path
from unittest.mock import MagicMock

SRC_ROOT = Path(__file__).parent.parent.parent / "src"


class TestSchedulerRoutesFix:
    """Verify scheduler routes no longer reference formation._scheduler."""

    def _get_scheduler_route_source(self):
        path = (
            SRC_ROOT
            / "muxi/runtime/formation/server/routes/admin/scheduler.py"
        )
        return path.read_text()

    def test_no_formation_scheduler_references(self):
        """Route handlers must not use getattr(formation, '_scheduler')."""
        source = self._get_scheduler_route_source()
        assert 'formation, "_scheduler"' not in source
        assert "formation._scheduler" not in source

    def test_uses_overlord_scheduler_service(self):
        """Route handlers must access scheduler via overlord.scheduler_service."""
        source = self._get_scheduler_route_source()
        assert 'getattr(formation, "_overlord"' in source
        assert 'getattr(overlord, "scheduler_service"' in source

    def test_all_four_endpoints_fixed(self):
        """All 4 scheduler endpoints must use the overlord path."""
        source = self._get_scheduler_route_source()
        count = source.count('getattr(overlord, "scheduler_service"')
        assert count == 4, f"Expected 4 overlord lookups, found {count}"


class TestMemobaseDimensionFix:
    """Verify Memobase exposes .dimension from its inner LongTermMemory."""

    def test_memobase_exposes_dimension(self):
        """Memobase must have .dimension matching its LongTermMemory."""
        mock_ltm = MagicMock()
        mock_ltm.dimension = 384

        from muxi.runtime.services.memory.memobase import Memobase

        mb = Memobase(long_term_memory=mock_ltm)
        assert mb.dimension == 384

    def test_memobase_dimension_defaults_to_1536(self):
        """If LongTermMemory has no dimension, Memobase defaults to 1536."""
        mock_ltm = MagicMock(spec=[])  # no dimension attribute

        from muxi.runtime.services.memory.memobase import Memobase

        mb = Memobase(long_term_memory=mock_ltm)
        assert mb.dimension == 1536

    def test_memobase_dimension_768(self):
        """Memobase correctly propagates 768-dim."""
        mock_ltm = MagicMock()
        mock_ltm.dimension = 768

        from muxi.runtime.services.memory.memobase import Memobase

        mb = Memobase(long_term_memory=mock_ltm)
        assert mb.dimension == 768


class TestMemobaseInitializationFix:
    """Verify the Memobase fallback in initialization.py creates LongTermMemory correctly."""

    def _get_init_source(self):
        path = SRC_ROOT / "muxi/runtime/formation/initialization.py"
        return path.read_text()

    def test_no_connection_string_kwarg_to_memobase(self):
        """Memobase must not be called with connection_string= kwarg."""
        source = self._get_init_source()
        assert "Memobase(\n                connection_string=" not in source

    def test_memobase_wraps_long_term_memory(self):
        """Memobase fallback must create LongTermMemory first, then wrap it."""
        source = self._get_init_source()
        assert "Memobase(long_term_memory=" in source

    def test_memobase_init_signature_no_connection_string(self):
        """Memobase.__init__ must not accept connection_string parameter."""
        from muxi.runtime.services.memory.memobase import Memobase

        sig = inspect.signature(Memobase.__init__)
        param_names = list(sig.parameters.keys())
        assert "connection_string" not in param_names
        assert "long_term_memory" in param_names
