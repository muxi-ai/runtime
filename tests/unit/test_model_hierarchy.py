"""Unit tests for hierarchical model selection.

Covers the override chain (formation defaults -> agent llm_models ->
SOP/trigger/skill -> step directive), alias resolution, request-time
fallback when an override cannot be resolved, and the
inert-when-unconfigured guarantee.
"""

from collections import OrderedDict
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from muxi.runtime.datatypes.workflow import SkillRef, SubTask
from muxi.runtime.formation.background.transformers import parse_trigger_frontmatter
from muxi.runtime.formation.config.validation import FormationValidator
from muxi.runtime.formation.overlord import overlord as overlord_module
from muxi.runtime.formation.overlord.overlord import Overlord
from muxi.runtime.formation.skills.parser import parse_skill_md
from muxi.runtime.formation.workflow.decomposer import TaskDecomposer


class FakeLLM:
    """Stands in for LLM so no provider client is constructed."""

    def __init__(self, model=None, api_key=None, **settings):
        self.model = model
        self.api_key = api_key
        self.settings = settings


def make_overlord(capability_models, aliases=None, global_llm_settings=None):
    """Build a minimally-initialized Overlord for model-resolution testing."""
    ov = Overlord.__new__(Overlord)
    ov._model_cache = {}
    ov._capability_models = capability_models
    ov._global_llm_settings = global_llm_settings or {}
    ov._global_api_keys = {"openai": "test-key"}
    ov._model_aliases = aliases or {}
    ov._request_model_overrides = OrderedDict()
    return ov


# ===========================================================================
# SOP parsing: [model:x] step directive and frontmatter default
# ===========================================================================


class TestSOPModelDirectiveParsing:
    @pytest.fixture
    def decomposer(self):
        return TaskDecomposer()

    def test_model_directive_numbered_format(self, decomposer):
        content = """## Steps
1. **Quick scan** [agent:researcher] [model:openai/gpt-4o-mini]
   Collect relevant information.
2. **Deep analysis** [agent:analyst]
   Analyze the data.
"""
        steps = decomposer._sop_extract_numbered_steps(content)
        assert len(steps) == 2
        assert steps[0]["model"] == "openai/gpt-4o-mini"
        assert steps[1]["model"] is None

    def test_model_directive_heading_format(self, decomposer):
        content = """## Step 1: Quick scan [model:fast]
[agent:researcher]
Collect relevant information.

## Step 2: Deep analysis
[agent:analyst]
Analyze the data.
"""
        steps = decomposer._sop_extract_heading_steps(content)
        assert len(steps) == 2
        assert steps[0]["model"] == "fast"
        assert steps[1]["model"] is None

    def test_model_directive_in_body(self, decomposer):
        content = """## Steps
1. **Scan** [agent:researcher]
   Use [model:openai/gpt-4o-mini] for this step.
2. **Analyze** [agent:analyst]
   Analyze.
"""
        steps = decomposer._sop_extract_numbered_steps(content)
        assert steps[0]["model"] == "openai/gpt-4o-mini"

    def test_model_directive_stripped_from_description(self, decomposer):
        content = """## Steps
1. **Scan** [agent:researcher] [model:fast]
   Collect data.
2. **Analyze** [agent:analyst]
   Analyze.
"""
        steps = decomposer._sop_extract_numbered_steps(content)
        assert "[model:" not in steps[0]["description"]
        assert "fast" not in steps[0]["description"]

    def test_deterministic_parser_sets_subtask_model(self, decomposer):
        sop = """## Steps
1. **Scan** [agent:researcher] [model:openai/gpt-4o-mini]
   Collect data.
2. **Analyze** [agent:analyst]
   Analyze.
"""
        workflow = decomposer._parse_template_sop_deterministic(sop, "do the thing")
        assert workflow is not None
        tasks = [workflow.tasks[tid] for tid in sorted(workflow.tasks)]
        assert tasks[0].model == "openai/gpt-4o-mini"
        assert tasks[1].model is None

    @pytest.mark.asyncio
    async def test_sop_frontmatter_default_applied_to_steps(self, decomposer):
        request = """<sop>
## Steps
1. **Scan** [agent:researcher] [model:openai/gpt-4o-mini]
   Collect data.
2. **Analyze** [agent:analyst]
   Analyze.
</sop>

<user_request>
do the thing
</user_request>
"""
        workflow = await decomposer.decompose_request(
            request=request,
            context={
                "sop_mode": "template",
                "sop_id": "test-sop",
                "sop_model": "anthropic/claude-haiku-4-5",
            },
        )
        tasks = [workflow.tasks[tid] for tid in sorted(workflow.tasks)]
        # Step directive wins over the SOP frontmatter default
        assert tasks[0].model == "openai/gpt-4o-mini"
        # Steps without a directive inherit the frontmatter default
        assert tasks[1].model == "anthropic/claude-haiku-4-5"

    @pytest.mark.asyncio
    async def test_inert_when_unconfigured(self, decomposer):
        """SOPs without model config produce tasks with model=None."""
        request = """<sop>
## Steps
1. **Scan** [agent:researcher]
   Collect data.
2. **Analyze** [agent:analyst]
   Analyze.
</sop>

<user_request>
do the thing
</user_request>
"""
        workflow = await decomposer.decompose_request(
            request=request,
            context={"sop_mode": "template", "sop_id": "test-sop"},
        )
        assert all(task.model is None for task in workflow.tasks.values())


class TestSubTaskModelField:
    def test_default_is_none(self):
        task = SubTask(id="t1", description="x", required_capabilities=["general"])
        assert task.model is None

    def test_model_field_accepts_reference(self):
        task = SubTask(
            id="t1",
            description="x",
            required_capabilities=["general"],
            model="openai/gpt-4o-mini",
        )
        assert task.model == "openai/gpt-4o-mini"


# ===========================================================================
# Overlord: resolve_model_override, aliases, request-scoped overrides
# ===========================================================================


class TestResolveModelOverride:
    @pytest.mark.asyncio
    async def test_resolves_direct_reference(self):
        ov = make_overlord({"text": {"model": "openai/gpt-4o"}})
        with patch.object(overlord_module, "LLM", FakeLLM):
            model = await ov.resolve_model_override("openai/gpt-4o-mini", source="sop_step")
        assert model is not None
        assert model.model == "openai/gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_resolves_alias(self):
        ov = make_overlord(
            {"text": {"model": "openai/gpt-4o"}},
            aliases={"fast": "openai/gpt-4o-mini"},
        )
        with patch.object(overlord_module, "LLM", FakeLLM):
            model = await ov.resolve_model_override("fast", source="sop_step")
        assert model is not None
        assert model.model == "openai/gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_alias_and_target_share_cache_entry(self):
        ov = make_overlord(
            {"text": {"model": "openai/gpt-4o"}},
            aliases={"fast": "openai/gpt-4o-mini"},
        )
        with patch.object(overlord_module, "LLM", FakeLLM):
            first = await ov.resolve_model_override("fast", source="sop_step")
            second = await ov.resolve_model_override("openai/gpt-4o-mini", source="skill")
        assert first is second
        assert len(ov._model_cache) == 1

    @pytest.mark.asyncio
    async def test_override_reuses_capability_config(self):
        """An override targeting a declared model inherits its api_key/settings."""
        ov = make_overlord(
            {
                "text": {"model": "openai/gpt-4o"},
                "vision": {
                    "model": "openai/gpt-4o-mini",
                    "api_key": "vision-key",
                    "settings": {"temperature": 0.1},
                },
            }
        )
        with patch.object(overlord_module, "LLM", FakeLLM):
            model = await ov.resolve_model_override("openai/gpt-4o-mini", source="trigger")
        assert model.api_key == "vision-key"
        assert model.settings == {"temperature": 0.1}

    @pytest.mark.asyncio
    async def test_failure_returns_none(self):
        """A model-construction failure degrades (returns None), never raises."""

        class ExplodingLLM:
            def __init__(self, *args, **kwargs):
                raise RuntimeError("provider not installed")

        ov = make_overlord({"text": {"model": "openai/gpt-4o"}})
        with patch.object(overlord_module, "LLM", ExplodingLLM):
            model = await ov.resolve_model_override("bogus/model", source="sop_step")
        assert model is None

    @pytest.mark.asyncio
    async def test_invalid_reference_returns_none(self):
        ov = make_overlord({"text": {"model": "openai/gpt-4o"}})
        with patch.object(overlord_module, "LLM", FakeLLM):
            assert await ov.resolve_model_override("", source="sop_step") is None
            assert await ov.resolve_model_override(None, source="sop_step") is None

    @pytest.mark.asyncio
    async def test_override_cache_does_not_collide_with_capability_cache(self):
        """Override entries use a distinct cache scope from capability lookups."""
        ov = make_overlord({"text": {"model": "openai/gpt-4o"}})
        with patch.object(overlord_module, "LLM", FakeLLM):
            capability_model = await ov.get_model_for_capability("text")
            override_model = await ov.resolve_model_override("openai/gpt-4o", source="sop_step")
        assert capability_model is not override_model
        keys = sorted(ov._model_cache)
        assert any(k.startswith("default:text:") for k in keys)
        assert any(k.startswith("override:") for k in keys)


class TestRequestModelOverrideRegistry:
    def test_register_and_get(self):
        ov = make_overlord({"text": {"model": "openai/gpt-4o"}})
        ov.register_request_model_override("req_1", "openai/gpt-4o-mini")
        assert ov.get_request_model_override("req_1") == "openai/gpt-4o-mini"
        assert ov.get_request_model_override("req_2") is None
        assert ov.get_request_model_override(None) is None

    def test_registry_is_bounded(self):
        ov = make_overlord({"text": {"model": "openai/gpt-4o"}})
        for i in range(300):
            ov.register_request_model_override(f"req_{i}", "openai/gpt-4o-mini")
        assert len(ov._request_model_overrides) == 256
        # Oldest entries evicted first
        assert ov.get_request_model_override("req_0") is None
        assert ov.get_request_model_override("req_299") == "openai/gpt-4o-mini"

    def test_empty_values_ignored(self):
        ov = make_overlord({"text": {"model": "openai/gpt-4o"}})
        ov.register_request_model_override("", "openai/gpt-4o-mini")
        ov.register_request_model_override("req_1", "")
        assert len(ov._request_model_overrides) == 0


class TestAgentLevelCacheScope:
    @pytest.mark.asyncio
    async def test_agent_scope_isolated_from_default(self):
        """Agent-level models cache under the agent's scope, not 'default'."""
        ov = make_overlord({"text": {"model": "openai/gpt-4o"}})
        with patch.object(overlord_module, "LLM", FakeLLM):
            default_model = await ov.get_model_for_capability("text")
            agent_model = await ov._get_or_create_model(
                {"model": "openai/gpt-4o-mini"}, cache_scope="researcher:text"
            )
        assert default_model.model == "openai/gpt-4o"
        assert agent_model.model == "openai/gpt-4o-mini"
        assert any(k.startswith("researcher:text:") for k in ov._model_cache)


# ===========================================================================
# Agent: per-call override with degradation to the agent default
# ===========================================================================


class TestAgentCallActiveModel:
    def _make_agent(self):
        from muxi.runtime.formation.agents.agent import Agent

        agent = Agent.__new__(Agent)
        agent.agent_id = "test-agent"
        return agent

    @pytest.mark.asyncio
    async def test_own_model_errors_propagate(self):
        agent = self._make_agent()

        class OwnModel:
            model = "openai/gpt-4o"

            async def chat(self, messages):
                raise RuntimeError("own model down")

        agent.model = OwnModel()
        with pytest.raises(RuntimeError, match="own model down"):
            await agent._call_active_model(agent.model, "chat", [])

    @pytest.mark.asyncio
    async def test_override_failure_degrades_to_agent_model(self):
        agent = self._make_agent()

        class OwnModel:
            model = "openai/gpt-4o"

            async def chat(self, messages):
                return "fallback response"

        class OverrideModel:
            model = "bogus/model"

            async def chat(self, messages):
                raise RuntimeError("no such provider")

        agent.model = OwnModel()
        result = await agent._call_active_model(OverrideModel(), "chat", [])
        assert result == "fallback response"

    @pytest.mark.asyncio
    async def test_override_success_uses_override(self):
        agent = self._make_agent()

        class OwnModel:
            model = "openai/gpt-4o"

            async def chat(self, messages):
                return "own response"

        class OverrideModel:
            model = "openai/gpt-4o-mini"

            async def chat(self, messages):
                return "override response"

        agent.model = OwnModel()
        result = await agent._call_active_model(OverrideModel(), "chat", [])
        assert result == "override response"


# ===========================================================================
# Executor: skill-level model lookup
# ===========================================================================


class TestSkillModelForTask:
    def _make_executor(self, skill_models):
        from muxi.runtime.formation.workflow.executor import WorkflowExecutor

        executor = WorkflowExecutor.__new__(WorkflowExecutor)
        skill_manager = MagicMock()
        skill_manager.skills = {
            name: MagicMock(model=model) for name, model in skill_models.items()
        }
        overlord = MagicMock()
        overlord.skill_manager = skill_manager
        executor.overlord = overlord
        return executor

    def test_returns_first_skill_model(self):
        executor = self._make_executor({"pdf": "openai/gpt-4o-mini", "csv": None})
        task = SubTask(
            id="t1",
            description="x",
            required_capabilities=["general"],
            required_skills=[SkillRef(name="csv"), SkillRef(name="pdf")],
        )
        assert executor._skill_model_for_task(task) == "openai/gpt-4o-mini"

    def test_returns_none_without_skills(self):
        executor = self._make_executor({})
        task = SubTask(id="t1", description="x", required_capabilities=["general"])
        assert executor._skill_model_for_task(task) is None

    def test_returns_none_when_skills_have_no_model(self):
        executor = self._make_executor({"pdf": None})
        task = SubTask(
            id="t1",
            description="x",
            required_capabilities=["general"],
            required_skills=[SkillRef(name="pdf")],
        )
        assert executor._skill_model_for_task(task) is None


# ===========================================================================
# Trigger frontmatter: model key
# ===========================================================================


class TestTriggerModelFrontmatter:
    def test_model_key_accepted(self):
        content = """---
model: openai/gpt-4o-mini
---
Respond to: ${{ data.message }}
"""
        meta, body = parse_trigger_frontmatter(content)
        assert meta["model"] == "openai/gpt-4o-mini"
        assert "Respond to" in body

    def test_invalid_model_rejected(self):
        content = """---
model: 42
---
Body.
"""
        with pytest.raises(ValueError, match="'model' must be a non-empty string"):
            parse_trigger_frontmatter(content)

    def test_triggers_without_model_unchanged(self):
        content = "Plain trigger: ${{ data.message }}\n"
        meta, body = parse_trigger_frontmatter(content)
        assert meta == {}
        assert body == content


# ===========================================================================
# Skill parser: model frontmatter
# ===========================================================================


class TestSkillModelFrontmatter:
    def _write_skill(self, tmp_path: Path, frontmatter: str) -> Path:
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(f"---\n{frontmatter}\n---\n\n# Test Skill\n")
        return skill_md

    def test_model_parsed(self, tmp_path):
        skill_md = self._write_skill(
            tmp_path, "name: test-skill\ndescription: A skill\nmodel: openai/gpt-4o-mini"
        )
        metadata, _, warnings = parse_skill_md(skill_md)
        assert metadata.model == "openai/gpt-4o-mini"

    def test_model_defaults_to_none(self, tmp_path):
        skill_md = self._write_skill(tmp_path, "name: test-skill\ndescription: A skill")
        metadata, _, _ = parse_skill_md(skill_md)
        assert metadata.model is None

    def test_invalid_model_warns_and_ignores(self, tmp_path):
        skill_md = self._write_skill(tmp_path, "name: test-skill\ndescription: A skill\nmodel: 42")
        metadata, _, warnings = parse_skill_md(skill_md)
        assert metadata.model is None
        assert any("invalid 'model'" in w for w in warnings)


# ===========================================================================
# Load-time validation: aliases and model references
# ===========================================================================


class TestModelHierarchyValidation:
    def _write_formation(self, tmp_path: Path, llm_extra: str = "") -> Path:
        formation_dir = tmp_path / "formation"
        formation_dir.mkdir()
        (formation_dir / "formation.yaml").write_text(f"""schema: "1.0.0"
id: "test-formation"
description: "Validation test formation"
llm:
  models:
    - text: "openai/gpt-4o-mini"
{llm_extra}
""")
        return formation_dir

    def test_valid_aliases_pass(self, tmp_path):
        formation_dir = self._write_formation(
            tmp_path,
            llm_extra='  aliases:\n    fast: "openai/gpt-4o-mini"\n',
        )
        result = FormationValidator().validate(formation_dir)
        assert result.is_valid, result.errors

    def test_alias_without_provider_fails(self, tmp_path):
        formation_dir = self._write_formation(
            tmp_path,
            llm_extra='  aliases:\n    fast: "gpt-4o-mini"\n',
        )
        result = FormationValidator().validate(formation_dir)
        assert not result.is_valid
        assert any("provider/model" in e for e in result.errors)

    def test_alias_colliding_with_capability_fails(self, tmp_path):
        formation_dir = self._write_formation(
            tmp_path,
            llm_extra='  aliases:\n    text: "openai/gpt-4o-mini"\n',
        )
        result = FormationValidator().validate(formation_dir)
        assert not result.is_valid
        assert any("collides" in e for e in result.errors)

    def test_aliases_must_be_dict(self, tmp_path):
        formation_dir = self._write_formation(
            tmp_path,
            llm_extra="  aliases: [fast]\n",
        )
        result = FormationValidator().validate(formation_dir)
        assert not result.is_valid
        assert any("llm.aliases must be a dictionary" in e for e in result.errors)

    def test_sop_with_unknown_model_reference_fails(self, tmp_path):
        formation_dir = self._write_formation(tmp_path)
        sops_dir = formation_dir / "sops"
        sops_dir.mkdir()
        (sops_dir / "analysis.md").write_text("""---
type: sop
name: Analysis
description: Test SOP
model: not-an-alias
---

## Steps
1. **Scan** [agent:researcher]
   Collect data.
2. **Analyze** [agent:analyst]
   Analyze.
""")
        result = FormationValidator().validate(formation_dir)
        assert not result.is_valid
        assert any("not-an-alias" in e for e in result.errors)

    def test_sop_step_directive_with_unknown_reference_fails(self, tmp_path):
        formation_dir = self._write_formation(tmp_path)
        sops_dir = formation_dir / "sops"
        sops_dir.mkdir()
        (sops_dir / "analysis.md").write_text("""---
type: sop
name: Analysis
description: Test SOP
---

## Steps
1. **Scan** [agent:researcher] [model:bogus-ref]
   Collect data.
2. **Analyze** [agent:analyst]
   Analyze.
""")
        result = FormationValidator().validate(formation_dir)
        assert not result.is_valid
        assert any("bogus-ref" in e for e in result.errors)

    def test_sop_with_alias_reference_passes(self, tmp_path):
        formation_dir = self._write_formation(
            tmp_path,
            llm_extra='  aliases:\n    fast: "openai/gpt-4o-mini"\n',
        )
        sops_dir = formation_dir / "sops"
        sops_dir.mkdir()
        (sops_dir / "analysis.md").write_text("""---
type: sop
name: Analysis
description: Test SOP
model: fast
---

## Steps
1. **Scan** [agent:researcher] [model:openai/gpt-4o]
   Collect data.
2. **Analyze** [agent:analyst]
   Analyze.
""")
        result = FormationValidator().validate(formation_dir)
        assert result.is_valid, result.errors

    def test_trigger_with_unknown_model_reference_fails(self, tmp_path):
        formation_dir = self._write_formation(tmp_path)
        triggers_dir = formation_dir / "triggers"
        triggers_dir.mkdir()
        (triggers_dir / "alert.md").write_text("""---
model: bogus-ref
---
Respond to: ${{ data.message }}
""")
        result = FormationValidator().validate(formation_dir)
        assert not result.is_valid
        assert any("bogus-ref" in e for e in result.errors)

    def test_skill_with_unknown_model_reference_fails(self, tmp_path):
        formation_dir = self._write_formation(tmp_path)
        skill_dir = formation_dir / "skills" / "pdf-gen"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("""---
name: pdf-gen
description: PDF generation
model: bogus-ref
---

# PDF Generation
""")
        result = FormationValidator().validate(formation_dir)
        assert not result.is_valid
        assert any("bogus-ref" in e for e in result.errors)

    def test_formation_without_new_fields_is_unaffected(self, tmp_path):
        """Inert-when-unconfigured: plain formations validate exactly as before."""
        formation_dir = self._write_formation(tmp_path)
        sops_dir = formation_dir / "sops"
        sops_dir.mkdir()
        (sops_dir / "plain.md").write_text("""---
type: sop
name: Plain
description: No model config
---

## Steps
1. **Scan** [agent:researcher]
   Collect data.
2. **Analyze** [agent:analyst]
   Analyze.
""")
        result = FormationValidator().validate(formation_dir)
        assert result.is_valid, result.errors
