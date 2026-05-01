"""Unit coverage for the MCP tool-error translator.

Layer 2 of the MCP param funnel: when an upstream MCP server returns
an error whose surface text is misleading, the translator annotates
the result with an agent-actionable hint that surfaces in the
next-turn tool message. See ``services/mcp/tools/error_translator.py``
for the design doc and motivating case (Findings 4 and 6).

These tests cover the matcher contract end-to-end:

* Positive matches across both arg-key variants the WAC pattern
  recognizes (driveItemId, file_id).
* Negative gates: missing arg keys, non-matching content, empty
  inputs, server_id mismatch when a pattern declares one.
* Return type contract (frozen dataclass with stable category id).
* Server-agnostic patterns (the only one currently shipped) fire
  regardless of server_id.

The wiring into ``services/mcp/service.py`` is verified separately by
the live MS365 retry — keeping the translator pure and the wiring
small means the unit-level surface here is just the helper itself.
"""

from __future__ import annotations

import re
from dataclasses import is_dataclass
from typing import cast

import pytest

from muxi.runtime.services.mcp.tools import error_translator as et


class TestErrorTranslationContract:
    """The public ``ErrorTranslation`` shape must stay stable —
    callers in ``service.py`` and any downstream consumers depend on
    ``category`` being a stable identifier and ``hint`` being a
    plain string suitable for direct injection into a tool message."""

    def test_translation_is_frozen_dataclass(self):
        result = et.translate_tool_error(
            tool_name="list-excel-worksheets",
            arguments={"driveItemId": "01..."},
            error_text="Could not obtain a WAC access token.",
        )
        assert result is not None
        assert is_dataclass(result), "ErrorTranslation must be a dataclass"
        with pytest.raises((AttributeError, Exception)):
            cast(et.ErrorTranslation, result).category = "mutated"  # type: ignore[misc]

    def test_translation_returns_string_hint(self):
        result = et.translate_tool_error(
            tool_name="list-excel-worksheets",
            arguments={"driveItemId": "01..."},
            error_text="Could not obtain a WAC access token.",
        )
        assert result is not None
        assert isinstance(result.hint, str) and result.hint, "Hint must be a non-empty string"
        assert isinstance(result.category, str) and result.category, "Category must be non-empty"


class TestExcelWACPattern:
    """Positive coverage for the only pattern currently shipped:
    Microsoft Graph's WAC-access-token error returned when an Excel
    endpoint receives a folder ID where a file ID was expected."""

    WAC_TEXT = (
        "Microsoft Graph API error: 403 Forbidden - "
        '{"error":{"code":"AccessDenied","message":"Could not obtain a WAC access token."}}'
    )

    def test_wac_with_drive_item_id_returns_hint(self):
        result = et.translate_tool_error(
            tool_name="list-excel-worksheets",
            arguments={"driveItemId": "01SA7QZQ7HKJH6YEQPZNEY2JV3H7LXCTZU"},
            error_text=self.WAC_TEXT,
        )
        assert result is not None
        assert result.category == "excel_wac_token_folder_id"
        assert "folder" in result.hint.lower()
        assert ".xlsx" in result.hint  # the actionable specifier

    def test_wac_with_file_id_returns_same_hint(self):
        """``excel-write-range`` uses ``file_id`` instead of
        ``driveItemId``. Both must trigger the same hint — Finding 6
        is the same defect as Finding 4 with a different arg name."""
        result = et.translate_tool_error(
            tool_name="excel-write-range",
            arguments={"file_id": "01SA7QZQ7HKJH6YEQPZNEY2JV3H7LXCTZU", "range": "B2"},
            error_text=self.WAC_TEXT,
        )
        assert result is not None
        assert result.category == "excel_wac_token_folder_id"

    def test_wac_is_case_insensitive(self):
        """Real Graph responses sometimes title-case parts of the
        message. The matcher must use IGNORECASE so we don't get
        false negatives on cosmetic upstream changes."""
        result = et.translate_tool_error(
            tool_name="list-excel-worksheets",
            arguments={"driveItemId": "01..."},
            error_text="COULD NOT OBTAIN A WAC ACCESS TOKEN.",
        )
        assert result is not None

    def test_wac_pattern_is_server_agnostic(self):
        """The current WAC pattern doesn't gate on server_id (multiple
        MCP servers could proxy Graph). Verify it fires regardless."""
        for server in (None, "ms365-mcp", "todo-helper-mcp", "spark-enterprise-graph"):
            result = et.translate_tool_error(
                tool_name="list-excel-worksheets",
                arguments={"driveItemId": "01..."},
                error_text=self.WAC_TEXT,
                server_id=server,
            )
            assert result is not None, f"pattern should fire for server_id={server!r}"


class TestNegativeGates:
    """Each gate (content regex, required arg keys, server_id regex,
    empty inputs) must independently prevent a false positive."""

    def test_no_match_when_arg_keys_missing(self):
        """The WAC pattern requires ``driveItemId`` or ``file_id`` in
        the arguments. A WAC-text error from an unrelated tool with
        different args must not trigger the hint."""
        result = et.translate_tool_error(
            tool_name="some-other-tool",
            arguments={"unrelated_param": "value"},
            error_text="Could not obtain a WAC access token.",
        )
        assert result is None

    def test_no_match_when_content_does_not_match(self):
        """A driveItemId-bearing call that fails for a different
        reason (e.g. genuine 401 unauthorized) must pass through
        without a hint."""
        result = et.translate_tool_error(
            tool_name="list-excel-worksheets",
            arguments={"driveItemId": "01..."},
            error_text="401 Unauthorized: bearer token expired",
        )
        assert result is None

    def test_no_match_for_empty_error_text(self):
        """The guard must short-circuit on every form of effectively
        empty input — including whitespace-only strings, which are
        truthy in Python and would otherwise fall through to the
        pattern loop."""
        for empty in (None, "", "   ", "\n\n", "\t  \r\n"):
            result = et.translate_tool_error(
                tool_name="list-excel-worksheets",
                arguments={"driveItemId": "01..."},
                error_text=empty,
            )
            assert result is None, f"empty input {empty!r} should return None"

    def test_whitespace_only_short_circuits_before_pattern_loop(self, monkeypatch):
        """Regression for the early-exit guard: an injected pattern
        whose regex is permissive enough to match whitespace must NOT
        fire when ``error_text`` is whitespace-only. Without the
        ``.strip()`` check this test would pass through to the loop
        and the permissive pattern would match — exactly the silent
        future-proofing failure the reviewer flagged."""
        permissive = et._ErrorPattern(
            category="probe_permissive_match",
            content_regex=re.compile(r".*", re.IGNORECASE | re.DOTALL),
            required_arg_keys=("probe_arg",),
            hint="should not appear",
        )
        monkeypatch.setattr(et, "_PATTERNS", (permissive,))

        for whitespace in ("   ", "\n", "\t\t", " \n  "):
            result = et.translate_tool_error(
                tool_name="any",
                arguments={"probe_arg": "x"},
                error_text=whitespace,
            )
            assert result is None, (
                f"whitespace-only input {whitespace!r} reached the pattern loop "
                "and matched a permissive regex — the early-exit guard regressed."
            )

        # Sanity: the same permissive pattern DOES fire on real text,
        # so the test above is meaningful (not vacuously passing
        # because the pattern itself is broken).
        sanity = et.translate_tool_error(
            tool_name="any",
            arguments={"probe_arg": "x"},
            error_text="real content here",
        )
        assert sanity is not None and sanity.category == "probe_permissive_match"

    def test_no_match_for_empty_arguments(self):
        for empty_args in (None, {}):
            result = et.translate_tool_error(
                tool_name="list-excel-worksheets",
                arguments=empty_args,
                error_text="Could not obtain a WAC access token.",
            )
            assert (
                result is None
            ), f"empty arguments {empty_args!r} should fail the required-arg gate"

    def test_non_dict_arguments_treated_as_empty(self):
        """Defensive: a malformed callsite that passes a non-dict
        for arguments must not raise — the gate treats it as an
        empty arg set and returns None."""
        result = et.translate_tool_error(
            tool_name="list-excel-worksheets",
            arguments=cast(dict, "not-a-dict"),
            error_text="Could not obtain a WAC access token.",
        )
        assert result is None


class TestServerIdGate:
    """The current registry has no server-gated pattern, but the gate
    is part of the matcher contract. Lock the behavior so a future
    pattern that adds ``server_id_regex`` works correctly."""

    def test_server_gate_blocks_non_matching_server(self, monkeypatch):
        # Inject a probe pattern that gates on a specific server.
        probe = et._ErrorPattern(
            category="probe_server_specific",
            content_regex=re.compile(r"probe-error-text", re.IGNORECASE),
            required_arg_keys=("probe_arg",),
            hint="probe hint",
            server_id_regex=re.compile(r"^only-this-server$"),
        )
        monkeypatch.setattr(et, "_PATTERNS", (probe,))

        # Matching server: pattern fires.
        match = et.translate_tool_error(
            tool_name="probe",
            arguments={"probe_arg": "x"},
            error_text="probe-error-text in body",
            server_id="only-this-server",
        )
        assert match is not None and match.category == "probe_server_specific"

        # Non-matching server: gate blocks.
        for server in (None, "other-server", "only-this-server-suffix-extra"):
            blocked = et.translate_tool_error(
                tool_name="probe",
                arguments={"probe_arg": "x"},
                error_text="probe-error-text in body",
                server_id=server,
            )
            assert blocked is None, f"gate should block server_id={server!r}"


class TestRegistryOrdering:
    """First-match-wins is part of the contract. If two patterns
    overlap on content but differ on category, the registry's order
    decides which fires."""

    def test_first_pattern_wins_on_overlap(self, monkeypatch):
        first = et._ErrorPattern(
            category="first_wins",
            content_regex=re.compile(r"shared-text", re.IGNORECASE),
            required_arg_keys=("arg",),
            hint="first hint",
        )
        second = et._ErrorPattern(
            category="second_loses",
            content_regex=re.compile(r"shared-text", re.IGNORECASE),
            required_arg_keys=("arg",),
            hint="second hint",
        )
        monkeypatch.setattr(et, "_PATTERNS", (first, second))

        result = et.translate_tool_error(
            tool_name="any",
            arguments={"arg": "x"},
            error_text="shared-text appears here",
        )
        assert result is not None
        assert result.category == "first_wins"
        assert result.hint == "first hint"
