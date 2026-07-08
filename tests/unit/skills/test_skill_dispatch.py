from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from muxi.runtime.formation.agents.skill_dispatch import (
    _normalize_compute_parameters,
    handle_run_skill,
)
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


@pytest.mark.asyncio
async def test_handle_run_skill_passes_input_files_to_rce(executable_skills_dir):
    manager = SkillManager(executable_skills_dir)
    manager.load_public_skills(["drive-helper"])

    rce_result = SimpleNamespace(
        status="success",
        exit_code=0,
        stdout="42",
        stderr="",
        duration_ms=5,
        artifacts=[],
    )
    run_skill_mock = AsyncMock(return_value=rce_result)
    overlord = SimpleNamespace(
        skill_manager=manager,
        rce_client=SimpleNamespace(
            ensure_cached=AsyncMock(),
            run_skill=run_skill_mock,
        ),
    )

    with (
        patch("muxi.runtime.formation.agents.skill_dispatch.streaming.stream"),
        patch("muxi.runtime.formation.agents.skill_dispatch.observability.observe"),
    ):
        result = await handle_run_skill(
            "agent-a",
            {
                "skill_name": "drive-helper",
                "command": "python3 scripts/run.py main.py",
                "input_files": {"main.py": "print(42)"},
            },
            overlord,
        )

    assert result["status"] == "success"
    call_kwargs = run_skill_mock.call_args.kwargs
    assert call_kwargs["input_files"] == {"main.py": "print(42)"}


@pytest.mark.asyncio
async def test_handle_run_skill_ignores_invalid_input_files(executable_skills_dir):
    manager = SkillManager(executable_skills_dir)
    manager.load_public_skills(["drive-helper"])

    rce_result = SimpleNamespace(
        status="success",
        exit_code=0,
        stdout="ok",
        stderr="",
        duration_ms=5,
        artifacts=[],
    )
    run_skill_mock = AsyncMock(return_value=rce_result)
    overlord = SimpleNamespace(
        skill_manager=manager,
        rce_client=SimpleNamespace(
            ensure_cached=AsyncMock(),
            run_skill=run_skill_mock,
        ),
    )

    with (
        patch("muxi.runtime.formation.agents.skill_dispatch.streaming.stream"),
        patch("muxi.runtime.formation.agents.skill_dispatch.observability.observe"),
    ):
        result = await handle_run_skill(
            "agent-a",
            {
                "skill_name": "drive-helper",
                "command": "python3 scripts/run.py",
                "input_files": "not-a-dict",
            },
            overlord,
        )

    assert result["status"] == "success"
    assert run_skill_mock.call_args.kwargs["input_files"] is None


def _compute_overlord(rce_result):
    manager = SkillManager()
    manager.load_builtin_skills()
    return SimpleNamespace(
        skill_manager=manager,
        rce_client=SimpleNamespace(
            ensure_cached=AsyncMock(),
            run_skill=AsyncMock(return_value=rce_result),
        ),
    )


def _observed_event_names(observe_mock):
    names = []
    for call in observe_mock.call_args_list:
        event = call.kwargs.get("event_type") or (call.args[0] if call.args else None)
        names.append(getattr(event, "name", str(event)))
    return names


@pytest.mark.asyncio
async def test_compute_skill_emits_requested_and_completed_events():
    rce_result = SimpleNamespace(
        status="success",
        exit_code=0,
        stdout="6.77",
        stderr="",
        duration_ms=31,
        artifacts=[],
    )
    overlord = _compute_overlord(rce_result)

    with (
        patch("muxi.runtime.formation.agents.skill_dispatch.streaming.stream"),
        patch("muxi.runtime.formation.agents.skill_dispatch.observability.observe") as observe,
    ):
        result = await handle_run_skill(
            "agent-a",
            {
                "skill_name": "compute",
                "command": "python3 scripts/run_python.py main.py",
                "input_files": {"main.py": "import statistics\nprint(6.77)"},
            },
            overlord,
        )

    assert result["status"] == "success"
    names = _observed_event_names(observe)
    assert "COMPUTATION_REQUESTED" in names
    assert "COMPUTATION_COMPLETED" in names
    assert "COMPUTATION_FAILED" not in names
    completed = observe.call_args_list[names.index("COMPUTATION_COMPLETED")]
    assert completed.kwargs["data"]["code"] == "import statistics\nprint(6.77)"
    assert completed.kwargs["data"]["stdout"] == "6.77"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,stderr,expected_kind",
    [
        ("error", "Traceback (most recent call last):\nZeroDivisionError", "runtime_error"),
        ("timeout", "Execution exceeded timeout", "timeout"),
        ("error", "ImportPolicyViolation: import not allowed: socket", "import_violation"),
        ("error", "PathValidationError: path traversal is not allowed", "path_violation"),
    ],
)
async def test_compute_skill_emits_failed_event_with_failure_kind(status, stderr, expected_kind):
    rce_result = SimpleNamespace(
        status=status,
        exit_code=1,
        stdout="",
        stderr=stderr,
        duration_ms=8,
        artifacts=[],
    )
    overlord = _compute_overlord(rce_result)

    with (
        patch("muxi.runtime.formation.agents.skill_dispatch.streaming.stream"),
        patch("muxi.runtime.formation.agents.skill_dispatch.observability.observe") as observe,
    ):
        await handle_run_skill(
            "agent-a",
            {
                "skill_name": "compute",
                "command": "python3 scripts/run_python.py main.py",
                "input_files": {"main.py": "print(1/0)"},
            },
            overlord,
        )

    names = _observed_event_names(observe)
    assert "COMPUTATION_FAILED" in names
    failed = observe.call_args_list[names.index("COMPUTATION_FAILED")]
    assert failed.kwargs["data"]["failure_kind"] == expected_kind
    assert failed.kwargs["data"]["code"] == "print(1/0)"


@pytest.mark.asyncio
async def test_non_compute_skill_emits_no_computation_events(executable_skills_dir):
    manager = SkillManager(executable_skills_dir)
    manager.load_public_skills(["drive-helper"])

    rce_result = SimpleNamespace(
        status="success",
        exit_code=0,
        stdout="ok",
        stderr="",
        duration_ms=5,
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
        patch("muxi.runtime.formation.agents.skill_dispatch.observability.observe") as observe,
    ):
        await handle_run_skill(
            "agent-a",
            {"skill_name": "drive-helper", "command": "python3 scripts/run.py"},
            overlord,
        )

    names = _observed_event_names(observe)
    assert not any(n.startswith("COMPUTATION_") for n in names)


class TestNormalizeComputeParameters:
    def test_well_formed_invocation_passes_through(self):
        command, files = _normalize_compute_parameters(
            "python3 scripts/run_python.py main.py", {"main.py": "print(1)"}
        )
        assert command == "python3 scripts/run_python.py main.py"
        assert files == {"main.py": "print(1)"}

    def test_raw_code_in_command_moved_to_input_files(self):
        command, files = _normalize_compute_parameters(
            "import numpy as np; print(np.std([1, 2, 3], ddof=1))", None
        )
        assert command == "python3 scripts/run_python.py main.py"
        assert files == {"main.py": "import numpy as np; print(np.std([1, 2, 3], ddof=1))"}

    def test_wrong_command_with_input_files_points_at_executor(self):
        command, files = _normalize_compute_parameters("python3 calc.py", {"calc.py": "print(2)"})
        assert command == "python3 scripts/run_python.py calc.py"
        assert files == {"calc.py": "print(2)"}

    def test_argless_executor_command_gains_input_file(self):
        command, files = _normalize_compute_parameters(
            "python3 scripts/run_python.py", {"main.py": "print(3)"}
        )
        assert command == "python3 scripts/run_python.py main.py"
        assert files == {"main.py": "print(3)"}

    @pytest.mark.asyncio
    async def test_handle_run_skill_recovers_raw_code_command(self):
        rce_result = SimpleNamespace(
            status="success",
            exit_code=0,
            stdout="1.0",
            stderr="",
            duration_ms=9,
            artifacts=[],
        )
        overlord = _compute_overlord(rce_result)
        run_skill_mock = overlord.rce_client.run_skill

        with (
            patch("muxi.runtime.formation.agents.skill_dispatch.streaming.stream"),
            patch("muxi.runtime.formation.agents.skill_dispatch.observability.observe"),
        ):
            result = await handle_run_skill(
                "agent-a",
                {
                    "skill_name": "compute",
                    "command": "import statistics; print(statistics.stdev([1, 2, 3]))",
                },
                overlord,
            )

        assert result["status"] == "success"
        call = run_skill_mock.call_args
        assert call.args[1] == "python3 scripts/run_python.py main.py"
        assert call.kwargs["input_files"] == {
            "main.py": "import statistics; print(statistics.stdev([1, 2, 3]))"
        }
