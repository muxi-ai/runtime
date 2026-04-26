"""
Tests for the executable-content guard in ArtifactService._validate_code.

Regression for v0.20260426.1: Sonnet/Haiku occasionally emit comment-only
or pseudo-code values for ``generate_file.code``, expecting the runtime to
substitute ``{{PLACEHOLDER}}`` references into the multi-line Python source
on its behalf. It does not. The sandbox would then run the no-op script,
produce zero files, and the artifact extractor would surface the confusing
``"No file was generated"`` error -- masking the real cause.

The guard catches the most common shapes early with an actionable message:

    Code contains no executable statements (only comments, docstrings, or
    imports). The `code` parameter must be complete, executable Python ...
"""

import textwrap

import pytest

from muxi.runtime.formation.artifacts.artifact_service import ArtifactService


@pytest.fixture(scope="module")
def service() -> ArtifactService:
    return ArtifactService()


# ---------------------------------------------------------------------------
# Cases that MUST be rejected (the actual bug surfaces and close cousins).
# ---------------------------------------------------------------------------


def test_validate_rejects_comment_only_code_from_actual_bug(service: ArtifactService):
    """The exact shape that bit production: a placeholder pseudo-comment
    referencing an unresolved ``{{...}}`` token."""
    code = textwrap.dedent("""\
        # Generate PRD for MUXI -- populated after doc scrape
        # Content will be injected from {{MUXI_DOCS}} at runtime
        """)
    ok, msg = service._validate_code(code)
    assert ok is False
    assert msg is not None
    assert "no executable statements" in msg.lower()


def test_validate_rejects_single_line_intent_comment(service: ArtifactService):
    """Second observed shape: a one-line narrative comment."""
    code = (
        "# PDF will be generated using reportlab or fpdf2 with content "
        "derived from MUXI docs and embedded knowledge. Full code will be "
        "constructed after skill instructions are loaded and docs are scraped."
    )
    ok, msg = service._validate_code(code)
    assert ok is False
    assert "executable" in msg.lower()


def test_validate_rejects_empty_string(service: ArtifactService):
    """An empty `code` value parses to ``Module(body=[])`` -- still no-op."""
    ok, msg = service._validate_code("")
    assert ok is False
    assert msg is not None


def test_validate_rejects_whitespace_only(service: ArtifactService):
    ok, msg = service._validate_code("   \n\t\n  ")
    assert ok is False
    assert msg is not None


def test_validate_rejects_docstring_only_module(service: ArtifactService):
    """A module that's nothing but a docstring writes nothing."""
    code = '"""This module describes the PDF we intend to generate later."""\n'
    ok, msg = service._validate_code(code)
    assert ok is False
    assert msg is not None


def test_validate_rejects_imports_only(service: ArtifactService):
    """Imports alone don't write a file."""
    code = textwrap.dedent("""\
        import io
        import json
        from reportlab.lib.pagesizes import letter
        """)
    ok, msg = service._validate_code(code)
    assert ok is False
    assert "executable" in msg.lower()


def test_validate_rejects_pass_only(service: ArtifactService):
    """`pass` is syntactically valid but semantically a no-op."""
    ok, msg = service._validate_code("pass\n")
    assert ok is False


def test_validate_rejects_ellipsis_only(service: ArtifactService):
    """`...` (Ellipsis) is the conventional placeholder for "fill me in"."""
    ok, msg = service._validate_code("...\n")
    assert ok is False


def test_validate_rejects_imports_plus_docstring(service: ArtifactService):
    """Mix of skip-list nodes still has zero executable content."""
    code = textwrap.dedent('''\
        """Generate a one-page PDF."""
        import io
        from reportlab.lib.pagesizes import letter
        ''')
    ok, msg = service._validate_code(code)
    assert ok is False


# ---------------------------------------------------------------------------
# Cases that MUST pass (real, working code patterns -- regression guard so the
# new check never blocks legitimate generation).
# ---------------------------------------------------------------------------


def test_validate_accepts_minimal_file_write(service: ArtifactService):
    """The smallest legitimate code that produces a file must pass."""
    code = textwrap.dedent("""\
        with open('output.txt', 'w') as f:
            f.write('hello')
        """)
    ok, msg = service._validate_code(code)
    assert ok is True, msg


def test_validate_accepts_realistic_reportlab_pdf(service: ArtifactService):
    """A realistic reportlab PDF generation snippet (the kind the LLM
    SHOULD be emitting) must pass."""
    code = textwrap.dedent("""\
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch

        styles = getSampleStyleSheet()
        story = [
            Paragraph('MUXI Brief', styles['Heading1']),
            Spacer(1, 0.2 * inch),
            Paragraph('MUXI is open-source AI agent infrastructure.', styles['Normal']),
        ]
        doc = SimpleDocTemplate('muxi_brief.pdf', pagesize=letter)
        doc.build(story)
        """)
    ok, msg = service._validate_code(code)
    assert ok is True, msg


def test_validate_accepts_docstring_then_real_code(service: ArtifactService):
    """A module-level docstring followed by real work must pass -- the
    docstring alone is a no-op but the trailing code makes the module
    executable."""
    code = textwrap.dedent('''\
        """Generate a tiny CSV report."""
        import csv

        with open('report.csv', 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['name', 'value'])
            writer.writerow(['muxi', 1])
        ''')
    ok, msg = service._validate_code(code)
    assert ok is True, msg


def test_validate_accepts_function_def_with_call(service: ArtifactService):
    """Defining a function and then calling it is a common pattern; the
    `Call` expression statement is executable content."""
    code = textwrap.dedent("""\
        def write_report():
            with open('report.txt', 'w') as f:
                f.write('done')

        write_report()
        """)
    ok, msg = service._validate_code(code)
    assert ok is True, msg


# ---------------------------------------------------------------------------
# Existing whitelist behavior is unchanged -- the new check fires before
# the import scan, but legitimate code still has its imports validated.
# ---------------------------------------------------------------------------


def test_validate_still_rejects_disallowed_imports_after_new_check(
    service: ArtifactService,
):
    """`subprocess` is not in ALLOWED_IMPORTS. The executable-statement
    check passes (the call is real executable content) but the import
    check still fires afterwards."""
    code = textwrap.dedent("""\
        import subprocess
        subprocess.run(['ls'])
        """)
    ok, msg = service._validate_code(code)
    assert ok is False
    assert "subprocess" in msg.lower()
    # Crucially NOT the new-guard message:
    assert "no executable statements" not in (msg or "").lower()


def test_validate_still_rejects_eval(service: ArtifactService):
    """`eval` is in `dangerous_funcs`. Same as above -- new guard passes,
    dangerous-call guard fires."""
    code = "eval('1 + 1')\n"
    ok, msg = service._validate_code(code)
    assert ok is False
    assert "eval" in (msg or "").lower()
    assert "no executable statements" not in (msg or "").lower()
