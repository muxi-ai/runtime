from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from muxi.runtime.formation.agents.skill_dispatch import handle_run_skill
from muxi.runtime.formation.skills.skill_manager import SkillManager


@pytest.fixture
def executable_skills_dir(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    skill_dir = skills_dir / "drive-helper"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: drive-helper\n"
        "description: Drive helper\n"
        "---\n\n"
        "# Drive Helper\n\nUse this skill for drive workflows.\n"
    )
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "run.py").write_text("print('ok')\n")

    return skills_dir


@pytest.mark.asyncio
async def test_handle_run_skill_parses_json_stdout_to_structured_content(executable_skills_dir):
    manager = SkillManager(executable_skills_dir)
    manager.load_public_skills(["drive-helper"])

    rce_result = SimpleNamespace(
        status="success",
        exit_code=0,
        stdout='{"driveId":"drive-123","driveItemId":"book-item-123"}',
        stderr="",
        duration_ms=12,
        artifacts=[],
    )
    overlord = SimpleNamespace(
        skill_manager=manager,
        rce_client=SimpleNamespace(
            ensure_cached=AsyncMock(),
            run_skill=AsyncMock(return_value=rce_result),
        ),
    )

    with (
        patch("muxi.runtime.formation.agents.skill_dispatch.streaming.stream"),
        patch("muxi.runtime.formation.agents.skill_dispatch.observability.observe"),
    ):
        result = await handle_run_skill(
            "agent-a",
            {"skill_name": "drive-helper", "command": "python3 scripts/run.py"},
            overlord,
        )

    assert result["status"] == "success"
    assert result["output"] == rce_result.stdout
    assert result["structuredContent"] == {
        "driveId": "drive-123",
        "driveItemId": "book-item-123",
    }


@pytest.mark.asyncio
async def test_handle_run_skill_leaves_plain_stdout_unstructured(executable_skills_dir):
    manager = SkillManager(executable_skills_dir)
    manager.load_public_skills(["drive-helper"])

    rce_result = SimpleNamespace(
        status="success",
        exit_code=0,
        stdout="worksheet names: Summary, Data",
        stderr="",
        duration_ms=12,
        artifacts=[],
    )
    overlord = SimpleNamespace(
        skill_manager=manager,
        rce_client=SimpleNamespace(
            ensure_cached=AsyncMock(),
            run_skill=AsyncMock(return_value=rce_result),
        ),
    )

    with (
        patch("muxi.runtime.formation.agents.skill_dispatch.streaming.stream"),
        patch("muxi.runtime.formation.agents.skill_dispatch.observability.observe"),
    ):
        result = await handle_run_skill(
            "agent-a",
            {"skill_name": "drive-helper", "command": "python3 scripts/run.py"},
            overlord,
        )

    assert result["status"] == "success"
    assert result["output"] == "worksheet names: Summary, Data"
    assert "structuredContent" not in result
