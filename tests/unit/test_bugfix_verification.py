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
        path = SRC_ROOT / "muxi/runtime/formation/server/routes/admin/scheduler.py"
        return path.read_text()

    def test_no_formation_scheduler_references(self):
        """Route handlers must not use getattr(formation, '_scheduler')."""
        source = self._get_scheduler_route_source()
        assert 'formation, "_scheduler"' not in source
        assert "formation._scheduler" not in source

    def test_uses_overlord_scheduler_service(self):
        """Route handlers must access scheduler via overlord.scheduler_service."""
        source = self._get_scheduler_route_source()
        # The helper _get_scheduler_service centralizes access
        assert "scheduler_service" in source
        assert "_overlord" in source

    def test_all_endpoints_use_service_layer(self):
        """All scheduler job endpoints must call the service/manager, not in-memory dicts."""
        source = self._get_scheduler_route_source()
        # Must NOT have in-memory dict fallback patterns
        assert "scheduler.jobs[" not in source, "Routes must not use in-memory dicts"
        assert "scheduler.jobs =" not in source, "Routes must not use in-memory dicts"
        # Must use async service methods (job_manager or scheduler service)
        assert "scheduler.job_manager" in source or "scheduler.pause_job" in source


class TestSchedulerMainLoopDispatch:
    """Verify scheduler dispatches job execution to the main event loop."""

    def _get_service_source(self):
        path = SRC_ROOT / "muxi/runtime/services/scheduler/service.py"
        return path.read_text()

    def test_start_captures_main_loop(self):
        """start() must store the running loop as _main_loop."""
        source = self._get_service_source()
        assert "self._main_loop = asyncio.get_running_loop()" in source

    def test_execute_due_jobs_uses_run_coroutine_threadsafe(self):
        """_execute_due_jobs must dispatch via run_coroutine_threadsafe."""
        source = self._get_service_source()
        assert "run_coroutine_threadsafe" in source

    def test_no_create_task_for_job_execution(self):
        """_execute_due_jobs must not use create_task as the primary dispatch path."""
        source = self._get_service_source()
        # The create_task call should only exist in the fallback branch
        method_start = source.index("async def _execute_due_jobs")
        method_end = source.index("async def _execute_single_job")
        method_body = source[method_start:method_end]
        # run_coroutine_threadsafe must appear before any create_task fallback
        rcts_pos = method_body.index("run_coroutine_threadsafe")
        ct_pos = method_body.index("create_task")
        assert rcts_pos < ct_pos, "run_coroutine_threadsafe must be the primary path"


class TestSchedulerMarksSuccessWhenNoWebhook:
    """Verify scheduler marks job success synchronously when no webhook is
    configured.  Regression for v0.20260416.2 Dev #1 scheduler bug where
    total_runs stayed 0 after a confirmed successful execution."""

    def _get_service_source(self):
        path = SRC_ROOT / "muxi/runtime/services/scheduler/service.py"
        return path.read_text()

    def test_execute_single_job_uses_use_async_equals_has_webhook(self):
        """use_async must follow has_webhook so no-webhook formations run
        synchronously and can be marked complete in-line."""
        source = self._get_service_source()
        method_start = source.index("async def _execute_single_job")
        method_end = source.index("async def complete_job_from_webhook")
        method_body = source[method_start:method_end]
        assert "has_webhook = bool(webhook_url)" in method_body
        assert "use_async=has_webhook" in method_body

    def test_execute_single_job_calls_mark_success_for_no_webhook_path(self):
        """The no-webhook branch must call mark_job_execution_success directly."""
        source = self._get_service_source()
        method_start = source.index("async def _execute_single_job")
        method_end = source.index("async def complete_job_from_webhook")
        method_body = source[method_start:method_end]
        assert "mark_job_execution_success" in method_body

    def test_execute_single_job_completes_one_time_job_without_webhook(self):
        """One-time jobs must also be completed synchronously when no webhook."""
        source = self._get_service_source()
        method_start = source.index("async def _execute_single_job")
        method_end = source.index("async def complete_job_from_webhook")
        method_body = source[method_start:method_end]
        assert "complete_onetime_job" in method_body


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
