"""Unit tests for [skill:...] directive parsing in SOPs."""

import pytest

from muxi.runtime.datatypes.workflow import SkillRef
from muxi.runtime.formation.workflow.decomposer import TaskDecomposer


class TestSOPSkillDirectiveParsing:
    """Test that [skill:name] and [skill:name/script] are parsed from SOP steps."""

    @pytest.fixture
    def decomposer(self):
        return TaskDecomposer()

    def test_skill_directive_numbered_format(self, decomposer):
        content = """## Steps
1. **Render report** [agent:writer] [skill:pdf-generation]
   Draft from template.
   Convert with [skill:pdf-generation/render].
2. **Notify team** [agent:comms]
   Send Slack message.
"""
        steps = decomposer._sop_extract_numbered_steps(content)
        assert len(steps) == 2

        step1 = steps[0]
        assert step1["assigned_agent"] == "writer"
        assert len(step1["skills"]) == 2
        assert step1["skills"][0] == {"name": "pdf-generation", "script": None}
        assert step1["skills"][1] == {"name": "pdf-generation", "script": "render"}

        step2 = steps[1]
        assert step2["assigned_agent"] == "comms"
        assert step2["skills"] == []

    def test_skill_directive_heading_format(self, decomposer):
        content = """## Step 1: Render report [agent:writer] [skill:pdf-generation]
Draft from template.
Convert with [skill:pdf-generation/render].

## Step 2: Notify team
Send Slack message.
"""
        steps = decomposer._sop_extract_heading_steps(content)
        assert len(steps) == 2

        step1 = steps[0]
        assert step1["assigned_agent"] == "writer"
        assert len(step1["skills"]) == 2
        assert step1["skills"][0] == {"name": "pdf-generation", "script": None}
        assert step1["skills"][1] == {"name": "pdf-generation", "script": "render"}

        step2 = steps[1]
        assert step2["skills"] == []

    def test_skill_directive_deduplication(self, decomposer):
        content = """## Steps
1. **Do it** [skill:pdf-generation] [skill:pdf-generation]
   Body.
2. **Next** [agent:x]
   More.
"""
        steps = decomposer._sop_extract_numbered_steps(content)
        assert len(steps[0]["skills"]) == 1

    def test_skill_directive_stripped_from_description(self, decomposer):
        content = """## Steps
1. **Render** [agent:writer] [skill:pdf-generation]
   Use [skill:pdf-generation/render] to convert.
2. **Next** [agent:x]
   More.
"""
        steps = decomposer._sop_extract_numbered_steps(content)
        desc = steps[0]["description"]
        assert "[skill:" not in desc
        assert "pdf-generation" not in desc

    def test_skill_directive_coexists_with_mcp_and_parallel(self, decomposer):
        content = """## Steps
1. **Analyze** [agent:analyst] [skill:data-analysis] [parallel]
   Pull metrics via [mcp:datadog] and analyze.
2. **Report** [agent:writer]
   Write summary.
"""
        steps = decomposer._sop_extract_numbered_steps(content)
        assert len(steps) == 2
        s = steps[0]
        assert s["assigned_agent"] == "analyst"
        assert s["mcp_tools"] == ["datadog"]
        assert s["skills"] == [{"name": "data-analysis", "script": None}]
        assert s["is_parallel"] is True


class TestSkillRefModel:
    """Test the SkillRef data model."""

    def test_skill_ref_defaults(self):
        ref = SkillRef(name="pdf-generation")
        assert ref.name == "pdf-generation"
        assert ref.script is None

    def test_skill_ref_with_script(self):
        ref = SkillRef(name="pdf-generation", script="render")
        assert ref.name == "pdf-generation"
        assert ref.script == "render"

    def test_skill_ref_extra_forbidden(self):
        with pytest.raises(ValueError):
            SkillRef(name="x", extra_field="bad")


class TestSkillManagerGrants:
    """Test request-scoped skill grants."""

    def test_grant_and_revoke(self):
        import tempfile

        from muxi.runtime.formation.skills.skill_manager import SkillManager

        mgr = SkillManager()
        # Seed a fake skill so grant filters unknown names
        from pathlib import Path

        from muxi.runtime.formation.skills.parser import SkillMetadata
        base = tempfile.mkdtemp()
        mgr.skills["pdf-generation"] = SkillMetadata(
            name="pdf-generation",
            description="PDF gen",
            path=Path(base) / "SKILL.md",
            base_dir=Path(base),
            license="MIT",
        )
        # Leave skill NOT public so the grant is the only way agent-b sees it
        # Before grant
        assert "pdf-generation" not in mgr.get_available_skills("agent-b")

        # Grant for request
        mgr.grant_request_skills("req-1", "agent-b", ["pdf-generation"])
        assert "pdf-generation" in mgr.get_available_skills("agent-b", request_id="req-1")

        # After revoke
        mgr.revoke_request_skills("req-1")
        assert "pdf-generation" not in mgr.get_available_skills("agent-b", request_id="req-1")

    def test_grant_does_not_mutate_declared_skills(self):
        import tempfile
        from pathlib import Path

        from muxi.runtime.formation.skills.skill_manager import SkillManager

        mgr = SkillManager()
        from muxi.runtime.formation.skills.parser import SkillMetadata
        base = tempfile.mkdtemp()
        mgr.skills["pdf-generation"] = SkillMetadata(
            name="pdf-generation",
            description="PDF gen",
            path=Path(base) / "SKILL.md",
            base_dir=Path(base),
            license="MIT",
        )
        mgr.public_skills = ["pdf-generation"]

        mgr.grant_request_skills("req-1", "agent-b", ["pdf-generation"])
        assert mgr.public_skills == ["pdf-generation"]
        assert mgr.agent_skills == {}


class TestResolveSkillCommand:
    """Test script-to-command resolution in executor."""

    def test_resolve_python_script(self):
        from unittest.mock import MagicMock

        from muxi.runtime.formation.workflow.executor import _resolve_skill_command

        mgr = MagicMock()
        mgr._get_resources.return_value = ["scripts/render.py", "references/spec.md"]
        cmd = _resolve_skill_command(mgr, "pdf-generation", "render.py")
        assert cmd == "python3 scripts/render.py"

    def test_resolve_by_stem(self):
        from unittest.mock import MagicMock

        from muxi.runtime.formation.workflow.executor import _resolve_skill_command

        mgr = MagicMock()
        mgr._get_resources.return_value = ["scripts/run.sh"]
        cmd = _resolve_skill_command(mgr, "x", "run")
        assert cmd == "bash scripts/run.sh"

    def test_resolve_missing_script(self):
        from unittest.mock import MagicMock

        from muxi.runtime.formation.workflow.executor import _resolve_skill_command

        mgr = MagicMock()
        mgr._get_resources.return_value = []
        assert _resolve_skill_command(mgr, "x", "nope") is None
