import pytest
from pathlib import Path
from muxi.runtime.formation.skills.parser import (
    SkillMetadata,
    parse_skill_md,
    load_skill_content,
    _enumerate_resources,
    _fix_unquoted_colons,
)
from muxi.runtime.formation.skills.skill_manager import SkillManager


@pytest.fixture
def tmp_skills_dir(tmp_path):
    """Create a temporary skills directory with test skills."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    # Create pdf-processing skill
    pdf_dir = skills_dir / "pdf-processing"
    pdf_dir.mkdir()
    (pdf_dir / "SKILL.md").write_text(
        '---\nname: pdf-processing\ndescription: "Extract text and tables from PDF files"\n---\n\n'
        "# PDF Processing\n\nUse this skill for PDF work.\n"
    )
    (pdf_dir / "scripts").mkdir()
    (pdf_dir / "scripts" / "extract.py").write_text("print('extract')\n")
    (pdf_dir / "references").mkdir()
    (pdf_dir / "references" / "spec.md").write_text("# PDF spec\n")

    # Create data-analysis skill
    data_dir = skills_dir / "data-analysis"
    data_dir.mkdir()
    (data_dir / "SKILL.md").write_text(
        "---\nname: data-analysis\ndescription: Analyze datasets and generate charts\n---\n\n"
        "# Data Analysis\n\nUse pandas and matplotlib.\n"
    )

    # Create ticket-handling skill (private)
    ticket_dir = skills_dir / "ticket-handling"
    ticket_dir.mkdir()
    (ticket_dir / "SKILL.md").write_text(
        "---\nname: ticket-handling\ndescription: Handle support tickets and escalations\n---\n\n"
        "# Ticket Handling\n\nFollow the escalation matrix.\n"
    )

    return skills_dir


class TestParser:
    def test_parse_valid_skill(self, tmp_skills_dir):
        path = tmp_skills_dir / "pdf-processing" / "SKILL.md"
        metadata, body, warnings = parse_skill_md(path)
        assert metadata.name == "pdf-processing"
        assert metadata.description == "Extract text and tables from PDF files"
        assert "PDF Processing" in body
        assert len(warnings) == 0

    def test_parse_missing_frontmatter(self, tmp_path):
        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# No frontmatter here\n")
        with pytest.raises(ValueError, match="missing frontmatter"):
            parse_skill_md(skill_dir / "SKILL.md")

    def test_parse_missing_description(self, tmp_path):
        skill_dir = tmp_path / "no-desc"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: no-desc\n---\n\nBody.\n")
        with pytest.raises(ValueError, match="missing required 'description'"):
            parse_skill_md(skill_dir / "SKILL.md")

    def test_parse_name_fallback_to_directory(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\ndescription: A skill\n---\n\nBody.\n"
        )
        metadata, body, warnings = parse_skill_md(skill_dir / "SKILL.md")
        assert metadata.name == "my-skill"

    def test_parse_name_mismatch_warning(self, tmp_path):
        skill_dir = tmp_path / "actual-dir"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: different-name\ndescription: A skill\n---\n\nBody.\n"
        )
        metadata, body, warnings = parse_skill_md(skill_dir / "SKILL.md")
        assert metadata.name == "different-name"
        assert any("does not match directory" in w for w in warnings)

    def test_parse_unquoted_colons(self, tmp_path):
        skill_dir = tmp_path / "colon-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: colon-skill\ndescription: Use this: it handles colons\n---\n\nBody.\n"
        )
        metadata, body, warnings = parse_skill_md(skill_dir / "SKILL.md")
        assert "colons" in metadata.description

    def test_parse_allowed_tools(self, tmp_path):
        skill_dir = tmp_path / "tools-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: tools-skill\ndescription: A skill\nallowed-tools: read_file write_file\n---\n\nBody.\n"
        )
        metadata, body, warnings = parse_skill_md(skill_dir / "SKILL.md")
        assert metadata.allowed_tools == ["read_file", "write_file"]

    def test_enumerate_resources(self, tmp_skills_dir):
        resources = _enumerate_resources(tmp_skills_dir / "pdf-processing")
        assert "scripts/extract.py" in resources
        assert "references/spec.md" in resources

    def test_enumerate_resources_empty(self, tmp_skills_dir):
        resources = _enumerate_resources(tmp_skills_dir / "data-analysis")
        assert resources == []

    def test_load_skill_content(self, tmp_skills_dir):
        metadata, body, _ = parse_skill_md(
            tmp_skills_dir / "pdf-processing" / "SKILL.md"
        )
        content = load_skill_content(metadata)
        assert content.metadata == metadata
        assert "PDF Processing" in content.body
        assert len(content.resources) == 2

    def test_fix_unquoted_colons(self):
        text = "description: Use this: it handles colons"
        fixed = _fix_unquoted_colons(text)
        assert '"Use this: it handles colons"' in fixed


class TestSkillManager:
    def test_load_public_skills(self, tmp_skills_dir):
        manager = SkillManager(tmp_skills_dir)
        manager.load_public_skills(["pdf-processing", "data-analysis"])
        assert len(manager.skills) == 2
        assert "pdf-processing" in manager.skills
        assert "data-analysis" in manager.skills

    def test_load_missing_skill_raises(self, tmp_skills_dir):
        manager = SkillManager(tmp_skills_dir)
        with pytest.raises(ValueError, match="directory not found"):
            manager.load_public_skills(["nonexistent-skill"])

    def test_load_agent_skills(self, tmp_skills_dir):
        manager = SkillManager(tmp_skills_dir)
        manager.load_public_skills(["pdf-processing"])
        manager.load_agent_skills("support-agent", ["ticket-handling"])
        assert "ticket-handling" in manager.skills
        assert manager.agent_skills["support-agent"] == ["ticket-handling"]

    def test_get_available_skills_deduplication(self, tmp_skills_dir):
        manager = SkillManager(tmp_skills_dir)
        manager.load_public_skills(["pdf-processing"])
        manager.load_agent_skills("support-agent", ["pdf-processing", "ticket-handling"])
        available = manager.get_available_skills("support-agent")
        # pdf-processing should appear only once
        assert available.count("pdf-processing") == 1
        assert "ticket-handling" in available

    def test_get_available_skills_no_agent_skills(self, tmp_skills_dir):
        manager = SkillManager(tmp_skills_dir)
        manager.load_public_skills(["pdf-processing"])
        available = manager.get_available_skills("some-agent")
        assert available == ["pdf-processing"]

    def test_build_catalog_xml(self, tmp_skills_dir):
        manager = SkillManager(tmp_skills_dir)
        manager.load_public_skills(["pdf-processing", "data-analysis"])
        catalog = manager.build_catalog_xml("agent-1")
        assert "## Available Skills" in catalog
        assert "**pdf-processing**" in catalog
        assert "**data-analysis**" in catalog
        assert "activate_skill" in catalog

    def test_build_catalog_xml_no_skills(self, tmp_skills_dir):
        manager = SkillManager(tmp_skills_dir)
        catalog = manager.build_catalog_xml("agent-1")
        assert catalog is None

    def test_build_activate_skill_tool(self, tmp_skills_dir):
        manager = SkillManager(tmp_skills_dir)
        manager.load_public_skills(["pdf-processing"])
        tool = manager.build_activate_skill_tool("agent-1")
        assert tool["function"]["name"] == "activate_skill"
        assert tool["function"]["parameters"]["properties"]["skill_name"]["enum"] == [
            "pdf-processing"
        ]

    def test_build_activate_skill_tool_no_skills(self, tmp_skills_dir):
        manager = SkillManager(tmp_skills_dir)
        tool = manager.build_activate_skill_tool("agent-1")
        assert tool is None

    def test_activate_skill(self, tmp_skills_dir):
        manager = SkillManager(tmp_skills_dir)
        manager.load_public_skills(["pdf-processing"])
        result = manager.activate("pdf-processing", "session-1")
        assert '<skill_content name="pdf-processing">' in result
        assert "PDF Processing" in result
        assert "<skill_resources>" in result
        assert "scripts/extract.py" in result

    def test_activate_deduplication(self, tmp_skills_dir):
        manager = SkillManager(tmp_skills_dir)
        manager.load_public_skills(["pdf-processing"])
        manager.activate("pdf-processing", "session-1")
        result = manager.activate("pdf-processing", "session-1")
        assert "already active" in result

    def test_activate_different_sessions(self, tmp_skills_dir):
        manager = SkillManager(tmp_skills_dir)
        manager.load_public_skills(["pdf-processing"])
        manager.activate("pdf-processing", "session-1")
        result = manager.activate("pdf-processing", "session-2")
        assert '<skill_content name="pdf-processing">' in result

    def test_activate_nonexistent_skill(self, tmp_skills_dir):
        manager = SkillManager(tmp_skills_dir)
        result = manager.activate("nonexistent", "session-1")
        assert "not found" in result

    def test_get_skill_descriptions(self, tmp_skills_dir):
        manager = SkillManager(tmp_skills_dir)
        manager.load_public_skills(["pdf-processing", "data-analysis"])
        descriptions = manager.get_skill_descriptions("agent-1")
        assert len(descriptions) == 2
        assert "Extract text and tables from PDF files" in descriptions
        assert "Analyze datasets and generate charts" in descriptions

    def test_get_skill_hash(self, tmp_skills_dir):
        manager = SkillManager(tmp_skills_dir)
        manager.load_public_skills(["pdf-processing"])
        h = manager.get_skill_hash("pdf-processing")
        assert h.startswith("sha256:")
        assert len(h) == 71  # sha256: + 64 hex chars

    def test_get_skill_hash_nonexistent(self, tmp_skills_dir):
        manager = SkillManager(tmp_skills_dir)
        assert manager.get_skill_hash("nonexistent") is None

    def test_get_all_skills_info(self, tmp_skills_dir):
        manager = SkillManager(tmp_skills_dir)
        manager.load_public_skills(["pdf-processing"])
        manager.load_agent_skills("agent-1", ["ticket-handling"])
        info = manager.get_all_skills_info()
        assert len(info) == 2
        pdf_info = next(i for i in info if i["name"] == "pdf-processing")
        assert pdf_info["scope"] == "public"
        assert pdf_info["has_scripts"] is True
        ticket_info = next(i for i in info if i["name"] == "ticket-handling")
        assert ticket_info["scope"] == "private"

    def test_is_activated(self, tmp_skills_dir):
        manager = SkillManager(tmp_skills_dir)
        manager.load_public_skills(["pdf-processing"])
        assert not manager.is_activated("pdf-processing", "session-1")
        manager.activate("pdf-processing", "session-1")
        assert manager.is_activated("pdf-processing", "session-1")
        assert not manager.is_activated("pdf-processing", "session-2")
