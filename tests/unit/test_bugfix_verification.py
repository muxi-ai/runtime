"""
Verification tests for bugfixes:
- Scheduler route handlers access scheduler via overlord (not formation._scheduler)
- Memobase exposes .dimension from inner LongTermMemory
- Memobase fallback path in initialization creates LongTermMemory correctly
"""

import inspect
import re
from pathlib import Path
from unittest.mock import MagicMock

SRC_ROOT = Path(__file__).parent.parent.parent / "src"


def _strip_comments_and_docstrings(source: str) -> str:
    """Drop docstring blocks and comment-only / trailing-comment text so
    regression *documentation* mentioning an old form does not trip
    code-shape assertions.

    Tracks multi-line docstring state via a triple-quote toggle: any
    line whose stripped form starts with ``\"\"\"`` or ``'''`` flips
    the toggle, and interior lines of an open docstring are dropped
    entirely. This catches the case where a multi-line docstring
    mentions the historical typo for context — a ``startswith('\"\"\"')``
    check alone would miss the interior lines and treat them as live
    code.

    Module-level so every test class can share the same toggle logic
    rather than each re-implementing it (the ad-hoc reimplementations
    have historically been fragile)."""
    out: list[str] = []
    in_doc = False
    for line in source.splitlines():
        stripped = line.strip()
        # Toggle on a triple-quote at the start of the stripped line.
        # ``""" ... """`` on a single line flips and re-flips, ending
        # in the same state — handled implicitly because we ``continue``
        # without appending.
        if stripped.startswith('"""') or stripped.startswith("'''"):
            # A line that opens AND closes on the same line (``""" foo """``)
            # is a one-line docstring; the toggle still ends balanced
            # because we don't increment, we flip — flip-flip = no-op.
            triple = '"""' if stripped.startswith('"""') else "'''"
            opens_and_closes = (
                len(stripped) >= 6 and stripped.endswith(triple) and stripped.count(triple) >= 2
            )
            if not opens_and_closes:
                in_doc = not in_doc
            continue
        if in_doc:
            continue
        if stripped.startswith("#"):
            continue
        if "#" in line:
            line = line.split("#", 1)[0]
        out.append(line)
    return "\n".join(out)


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


class TestSchedulerOverlordCompletionAttribute:
    """Verify the overlord references the scheduler via the correct
    attribute name (``scheduler_service``) when completing scheduled
    jobs from the async webhook path. Regression for the typo where
    ``self._scheduler`` (which never existed) was used in
    ``_execute_async_request``, causing every scheduled job's
    completion handler to be silently skipped — ``mark_job_execution_success``
    never ran, ``total_runs`` stayed 0, and ``last_run_at`` stayed NULL
    even after confirmed successful executions."""

    def _get_overlord_source(self):
        path = SRC_ROOT / "muxi/runtime/formation/overlord/overlord.py"
        return path.read_text()

    def test_no_underscore_scheduler_attribute_lookup(self):
        """Overlord must not reference ``self._scheduler`` — the
        attribute is ``self.scheduler_service``. Historical mentions
        inside docstrings or comments are allowed (the typo is
        documented in regression notes), so we strip those before the
        check via the module-level helper."""
        source = self._get_overlord_source()
        # The previous inline strip only matched lines whose stripped
        # form *starts* with ``\"\"\"``, which fails the moment a
        # multi-line docstring contains the historical attribute on
        # an interior line. ``_strip_comments_and_docstrings`` tracks
        # docstring state via a triple-quote toggle and drops interior
        # lines correctly.
        live_code = _strip_comments_and_docstrings(source)
        for line in live_code.splitlines():
            assert "self._scheduler" not in line, (
                "Live code references ``self._scheduler`` (missing). "
                "Use ``self.scheduler_service`` instead. Line: " + line.strip()
            )

    def test_async_request_completion_uses_scheduler_service(self):
        """``_execute_async_request`` must call
        ``scheduler_service.complete_job_from_webhook`` on both the
        success and failure branches."""
        source = self._get_overlord_source()
        method_start = source.index("async def _execute_async_request")
        # Slice generously — there are two completion call sites.
        method_body = source[method_start : method_start + 30000]
        assert method_body.count("self.scheduler_service.complete_job_from_webhook") >= 2, (
            "Expected at least two ``scheduler_service.complete_job_from_webhook`` "
            "calls in _execute_async_request (success + failure branches)."
        )


class TestSchedulerSessionIdNotDoubled:
    """Verify the scheduler does not double-prefix ``job_`` when
    constructing ``session_id`` for job execution. Regression for the
    cosmetic bug where ``session_id = f\"job_{job_id}\"`` produced
    ``job_job_<id>`` because job IDs already begin with ``job_``."""

    def _get_service_source(self):
        path = SRC_ROOT / "muxi/runtime/services/scheduler/service.py"
        return path.read_text()

    @staticmethod
    def _strip_comments_and_docstrings(method_body: str) -> str:
        """Delegate to the module-level helper so all test classes
        share a single toggle-based stripping implementation."""
        return _strip_comments_and_docstrings(method_body)

    def test_no_double_prefix_in_execute_single_job(self):
        """``_execute_single_job`` must not construct
        ``f\"job_{job_id}\"`` — that produces ``job_job_<id>``."""
        source = self._get_service_source()
        method_start = source.index("async def _execute_single_job")
        method_end = source.index("async def complete_job_from_webhook")
        live_code = self._strip_comments_and_docstrings(source[method_start:method_end])
        assert 'f"job_{job_id}"' not in live_code, (
            "Found live-code double-prefix construction ``f'job_{job_id}'`` — "
            "use ``session_id = job_id`` instead since job IDs are "
            "already prefixed."
        )
        assert "session_id = job_id" in live_code

    def test_complete_job_from_webhook_does_not_strip_prefix(self):
        """``complete_job_from_webhook`` must not slice the session_id
        with ``[4:]`` — that strip was only correct for the doubled
        prefix and would now strip the legitimate ``job_`` prefix."""
        source = self._get_service_source()
        method_start = source.index("async def complete_job_from_webhook")
        method_end = source.index("async def", method_start + 1)
        method_body = source[method_start:method_end]
        assert "session_id[4:]" not in method_body, (
            "Found ``session_id[4:]`` strip — session_id IS the job_id "
            "now that the doubled prefix is gone, so just use it directly."
        )


class TestSchedulerPromptRewriterPreservesFraming:
    """Verify the scheduler prompt rewriter prompt explicitly preserves
    delivery framing words (``remind me``, ``notify me``, ``send me``,
    etc). Regression for the bug where ``"remind me to drink water
    every 3 minutes"`` was rewritten to bare ``"drink water"`` —
    stripping the entire reminder semantics — and the agent
    interpreted it as a confirmation rather than a delivery
    instruction."""

    def _get_rewriter_prompt(self):
        path = SRC_ROOT / "muxi/runtime/formation/prompts/scheduler_prompt_rewriter.md"
        return path.read_text()

    def test_prompt_preserves_remind_me_framing(self):
        """The prompt must explicitly call out preserving ``remind
        me`` (and similar delivery framing)."""
        prompt = self._get_rewriter_prompt()
        assert "remind me" in prompt.lower()
        assert "notify me" in prompt.lower() or "notify" in prompt.lower()

    def test_prompt_has_drink_water_guard_example(self):
        """The exact failure mode (``remind me to drink water`` →
        bare ``drink water``) must appear as a guard example so future
        prompt edits don't silently regress this."""
        prompt = self._get_rewriter_prompt()
        assert "drink water" in prompt.lower()

    def test_prompt_warns_against_stripping_framing(self):
        """The prompt must warn against stripping the framing."""
        prompt = self._get_rewriter_prompt().lower()
        # Either an explicit "do not strip" instruction or a
        # "wrong: strips framing" example column.
        signals = ("delivery framing", "strips framing", "do not strip")
        assert any(s in prompt for s in signals), (
            "Prompt must explicitly warn against stripping delivery "
            "framing — otherwise the LLM treats ``remind me`` as "
            "schedule words and drops them."
        )


class TestScheduledExecutionMarker:
    """Verify the scheduler injects a ``[SCHEDULED]`` marker into the
    agent's view of the message (only) when ``session_id`` is in the
    scheduler namespace. Without this marker, an LLM receiving
    ``remind me to drink water`` cold reads it as a chat request to
    *configure* a reminder, then politely declines (\"I can't set
    reminders, use your phone\") — the rewriter fix alone wasn't
    enough to disambiguate intent for all model classes.

    Memory and observability stay clean: only the agent's view at
    inference time gets the marker. The original message is preserved
    via PR #165's ``EnhancedMessage(original, enhanced)`` threading."""

    def _get_orchestrator_source(self):
        path = SRC_ROOT / "muxi/runtime/formation/overlord/chat_orchestrator.py"
        return path.read_text()

    def test_marker_helper_exists(self):
        """A single-source-of-truth helper must exist so both
        rendering paths apply identical rules."""
        from muxi.runtime.formation.overlord.chat_orchestrator import (
            SCHEDULED_EXECUTION_MARKER,
            _apply_scheduled_marker,
        )

        assert SCHEDULED_EXECUTION_MARKER == "[SCHEDULED] "
        assert callable(_apply_scheduled_marker)

    def test_marker_applied_for_job_session(self):
        """Session IDs starting with ``job_`` get the marker."""
        from muxi.runtime.formation.overlord.chat_orchestrator import (
            _apply_scheduled_marker,
        )

        assert (
            _apply_scheduled_marker("remind me to drink water", "job_abc123")
            == "[SCHEDULED] remind me to drink water"
        )

    def test_marker_not_applied_for_normal_session(self):
        """Non-scheduler sessions stay unchanged — must not regress
        normal chat."""
        from muxi.runtime.formation.overlord.chat_orchestrator import (
            _apply_scheduled_marker,
        )

        for session_id in (None, "", "user-typed-bracket", "session_123", "abc"):
            assert (
                _apply_scheduled_marker("remind me to drink water", session_id)
                == "remind me to drink water"
            ), f"Marker leaked into non-scheduler session: {session_id!r}"

    def test_marker_application_is_idempotent(self):
        """If a message already carries the marker (e.g. a user
        copy-pasted a prior scheduled-firing transcript into a new
        scheduled job, or both render paths chain through the same
        string), the helper must not double-stamp it."""
        from muxi.runtime.formation.overlord.chat_orchestrator import (
            SCHEDULED_EXECUTION_MARKER,
            _apply_scheduled_marker,
        )

        already_marked = f"{SCHEDULED_EXECUTION_MARKER}remind me to drink water"

        # Single application on a marked message: unchanged.
        assert _apply_scheduled_marker(already_marked, "job_abc123") == already_marked

        # Two applications in series: still single-marked (chained-call
        # safety).
        once = _apply_scheduled_marker("remind me to drink water", "job_abc123")
        twice = _apply_scheduled_marker(once, "job_abc123")
        assert once == twice == already_marked

        # Idempotence does not unmark non-scheduler sessions: a marked
        # message in a normal session is left alone (no implicit strip).
        assert _apply_scheduled_marker(already_marked, "normal-session") == already_marked

    def test_enhance_message_uses_helper(self):
        """``_enhance_message_with_context`` must apply the marker via
        the centralized helper at the ``=== CURRENT REQUEST ===``
        rendering site (not by re-implementing the rule inline)."""
        source = self._get_orchestrator_source()
        method_start = source.index("async def _enhance_message_with_context")
        method_end = source.index("async def _build_clean_chat_context")
        method_body = source[method_start:method_end]
        assert (
            "_apply_scheduled_marker" in method_body
        ), "_enhance_message_with_context must call _apply_scheduled_marker."
        # The marker should be applied to the rendered ``User: ...``
        # line, not to the raw ``message`` (which feeds the
        # EnhancedMessage.original field — must stay clean).
        assert (
            "EnhancedMessage(original=message, enhanced=enhanced_message)" in method_body
            or "original=message" in method_body
        ), "EnhancedMessage.original must remain the unprefixed input."

    def test_clean_chat_context_uses_helper(self):
        """``_build_clean_chat_context`` must apply the marker to
        ``current_user_message`` before returning the bundle the agent
        consumes."""
        source = self._get_orchestrator_source()
        # Bound the slice to the next outer method so the assertion is
        # scoped to ``_build_clean_chat_context`` only — without this,
        # any later method that happens to call the helper would
        # satisfy the substring check and the policy guard could
        # silently rotate away under a refactor. Named-boundary
        # (matching ``test_enhance_message_uses_helper``) is preferred
        # over the generic ``async def `` lookup, which would land on
        # an inner closure (``_fetch_user_synopsis``) rather than the
        # next outer method and exclude the actual call site.
        method_start = source.index("async def _build_clean_chat_context")
        method_end = source.index("async def _extract_user_information_async")
        method_body = source[method_start:method_end]
        assert (
            "_apply_scheduled_marker" in method_body
        ), "_build_clean_chat_context must call _apply_scheduled_marker."

    def test_marker_not_applied_inside_buffer_turns(self):
        """Buffer turns (history) come from buffer memory which stores
        original user text, so they must NOT be re-marked. Lock the
        comment that documents this so the policy is visible."""
        source = self._get_orchestrator_source()
        # Same boundary discipline as ``test_clean_chat_context_uses_helper``.
        method_start = source.index("async def _build_clean_chat_context")
        method_end = source.index("async def _extract_user_information_async")
        method_body = source[method_start:method_end]

        # Normalize comment-marker noise + whitespace so phrases that
        # straddle line breaks become continuous substrings. Required
        # because Python's source layout splits e.g. ``is left\n
        # # untouched`` across two lines, and a literal substring
        # check on the raw body would never see ``"left untouched"`` —
        # which is exactly the precedence/empty-substring bug this
        # rewrite replaces.
        flat = re.sub(r"\s*#\s*", " ", method_body)
        flat = re.sub(r"\s+", " ", flat)

        # Each clause is asserted independently — no boolean glue, so
        # operator precedence cannot make any single check vacuous.
        # All three phrases must appear in the documenting comment for
        # the invariant to be considered locked in.
        for phrase in ("buffer_turns", "left untouched", "without the marker"):
            assert phrase in flat, (
                "The buffer-turns-not-marked invariant must be documented "
                "in the rendering function so a future edit can't quietly "
                f"start double-marking history. Missing phrase: {phrase!r}."
            )
