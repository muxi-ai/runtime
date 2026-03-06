"""Tests for overlord soul loading (SOUL.md auto-detect and precedence chain)."""

import os
import sys
import tempfile
from unittest.mock import patch

import pytest

from muxi.runtime.formation.overlord.overlord import Overlord

MULTILINGUAL_SUFFIX = (
    "\n\nIMPORTANT: Always reply in the same language as the user's original request."
)

# macOS uses a case-insensitive filesystem, so SOUL.md and soul.md are the same file.
IS_CASE_INSENSITIVE_FS = sys.platform == "darwin"


def make_overlord_stub(formation_config=None, configured_services=None):
    """Create a minimal Overlord-like object with just the attributes _load_soul needs."""
    stub = object.__new__(Overlord)
    stub.formation_config = formation_config or {}
    stub._configured_services = configured_services or {}
    stub._default_persona = None
    return stub


class TestSoulLoading:
    """Test the _load_soul() precedence chain:
    SOUL.md > soul.md > overlord.soul (inline) > built-in default
    """

    @pytest.mark.skipif(
        IS_CASE_INSENSITIVE_FS,
        reason="macOS case-insensitive filesystem cannot have both SOUL.md and soul.md",
    )
    def test_soul_md_uppercase_takes_precedence(self):
        """SOUL.md in formation dir should be used over soul.md."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "SOUL.md"), "w") as f:
                f.write("I am from SOUL.md")
            with open(os.path.join(tmpdir, "soul.md"), "w") as f:
                f.write("I am from soul.md")

            stub = make_overlord_stub(
                formation_config={"overlord": {"soul": "I am inline"}},
                configured_services={"formation_path": tmpdir},
            )
            stub._load_soul()

            assert stub._default_persona == "I am from SOUL.md" + MULTILINGUAL_SUFFIX

    def test_soul_file_detected_over_inline(self):
        """A soul file (SOUL.md) should take precedence over inline config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "SOUL.md"), "w") as f:
                f.write("I am from file")

            stub = make_overlord_stub(
                formation_config={"overlord": {"soul": "I am inline"}},
                configured_services={"formation_path": tmpdir},
            )
            stub._load_soul()

            assert stub._default_persona == "I am from file" + MULTILINGUAL_SUFFIX

    def test_soul_md_lowercase_used_when_no_uppercase(self):
        """soul.md should be used when SOUL.md doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "soul.md"), "w") as f:
                f.write("I am from soul.md")

            stub = make_overlord_stub(
                formation_config={"overlord": {"soul": "I am inline"}},
                configured_services={"formation_path": tmpdir},
            )
            stub._load_soul()

            assert stub._default_persona == "I am from soul.md" + MULTILINGUAL_SUFFIX

    def test_inline_soul_used_when_no_file(self):
        """overlord.soul inline config should be used when no soul file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stub = make_overlord_stub(
                formation_config={"overlord": {"soul": "I am inline soul"}},
                configured_services={"formation_path": tmpdir},
            )
            stub._load_soul()

            assert stub._default_persona == "I am inline soul" + MULTILINGUAL_SUFFIX

    def test_builtin_default_when_nothing_configured(self):
        """Built-in soul.md from PromptLoader should be used as last resort."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stub = make_overlord_stub(
                formation_config={},
                configured_services={"formation_path": tmpdir},
            )

            with patch(
                "muxi.runtime.formation.prompts.loader.PromptLoader.get",
                return_value="Built-in default soul",
            ):
                stub._load_soul()

            assert stub._default_persona == "Built-in default soul" + MULTILINGUAL_SUFFIX

    def test_fallback_when_promptloader_missing(self):
        """Hardcoded fallback should be used when PromptLoader also fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            stub = make_overlord_stub(
                formation_config={},
                configured_services={"formation_path": tmpdir},
            )

            with patch(
                "muxi.runtime.formation.prompts.loader.PromptLoader.get",
                side_effect=KeyError("soul.md not found"),
            ):
                stub._load_soul()

            assert stub._default_persona == (
                "You are a friendly and helpful assistant." + MULTILINGUAL_SUFFIX
            )

    def test_no_formation_path_falls_through_to_inline(self):
        """When formation_path is not in configured_services, skip file detection."""
        stub = make_overlord_stub(
            formation_config={"overlord": {"soul": "Inline without path"}},
            configured_services={},
        )
        stub._load_soul()

        assert stub._default_persona == "Inline without path" + MULTILINGUAL_SUFFIX

    def test_soul_file_whitespace_stripped(self):
        """Soul file content should be stripped of leading/trailing whitespace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "SOUL.md"), "w") as f:
                f.write("\n\n  I have whitespace  \n\n")

            stub = make_overlord_stub(
                formation_config={},
                configured_services={"formation_path": tmpdir},
            )
            stub._load_soul()

            assert stub._default_persona == "I have whitespace" + MULTILINGUAL_SUFFIX

    def test_multilingual_suffix_always_appended(self):
        """The multilingual instruction should always be appended."""
        stub = make_overlord_stub(
            formation_config={"overlord": {"soul": "Test"}},
            configured_services={},
        )
        stub._load_soul()

        assert stub._default_persona.endswith(
            "Always reply in the same language as the user's original request."
        )
