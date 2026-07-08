"""Dispatch handlers for skill-related tools (activate_skill, run_skill, generate_file).

Extracted from agent.py invoke_tool() to keep the main agent module focused
on core message processing.
"""

import datetime
from typing import Any, Dict, Literal, Optional, cast

from ...datatypes.artifacts import ArtifactMetadata, MuxiArtifact
from ...services import observability, streaming
from ...utils.fastjson import json


def _parse_structured_stdout(stdout: str) -> Optional[Any]:
    """Parse skill stdout when it is a standalone JSON object or array."""
    if not isinstance(stdout, str):
        return None

    cleaned = stdout.strip()
    if not cleaned or cleaned[0] not in "[{":
        return None

    try:
        return json.loads(cleaned)
    except Exception:
        return None


async def handle_activate_skill(
    agent_id: str,
    parameters: Dict[str, Any],
    overlord: Any,
    messages: list,
    session_id: str = "default",
) -> Dict[str, Any]:
    """Handle the activate_skill tool call."""
    skill_name = parameters.get("skill_name", "")
    manager = overlord.skill_manager

    if manager.is_activated(skill_name, session_id):
        await manager.activate_execution_context(skill_name, agent_id, session_id)
        observability.observe(
            event_type=observability.ConversationEvents.AGENT_MESSAGE_PROCESSING,
            level=observability.EventLevel.DEBUG,
            data={
                "agent_id": agent_id,
                "skill_name": skill_name,
                "session_id": session_id,
                "deduplicated": True,
            },
            description=f"Skill '{skill_name}' already active (deduped)",
        )
        return {
            "status": "already_active",
            "message": (
                f"Skill '{skill_name}' is already active. "
                "Refer to the instructions already in your context."
            ),
        }

    content = await manager.activate_async(skill_name, session_id, agent_id=agent_id)

    if messages and messages[0]["role"] == "system":
        messages[0]["content"] += f"\n\n{content}"

    observability.observe(
        event_type=observability.ConversationEvents.AGENT_MESSAGE_PROCESSING,
        level=observability.EventLevel.INFO,
        data={
            "agent_id": agent_id,
            "skill_name": skill_name,
            "session_id": session_id,
        },
        description=f"Skill '{skill_name}' activated by agent '{agent_id}'",
    )

    return {
        "status": "activated",
        "message": (
            f"Skill '{skill_name}' activated. " "Instructions are now available in your context."
        ),
    }


async def run_skill_command(
    skill_manager: Any,
    rce: Any,
    skill_name: str,
    command: str,
    input_files: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Execute a skill command via RCE without streaming/observability coupling.

    Returns a dict shaped for both handle_run_skill and the workflow executor.
    """
    if skill_name not in skill_manager.skills:
        return {"status": "error", "error": f"Skill '{skill_name}' not found."}

    metadata = skill_manager.skills[skill_name]
    content_hash = skill_manager.get_skill_hash(skill_name)

    await rce.ensure_cached(skill_name, metadata.base_dir, content_hash)

    skill_env = await skill_manager.resolve_skill_env(skill_name)
    result = await rce.run_skill(
        skill_name,
        command,
        input_files=input_files or None,
        timeout=60,
        env=skill_env or None,
    )

    response: Dict[str, Any] = {
        "status": result.status,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "output": result.stdout,
        "duration_ms": result.duration_ms,
    }
    structured_stdout = (
        _parse_structured_stdout(result.stdout) if result.status == "success" else None
    )
    if structured_stdout not in (None, "", [], {}):
        response["structuredContent"] = structured_stdout
    if result.stderr:
        response["stderr"] = result.stderr
    if result.artifacts:
        response["artifacts"] = [
            {"name": a["name"], "mime": a["mime"], "size": a["size"]} for a in result.artifacts
        ]
        response["_artifacts_full"] = result.artifacts
    return response


def _coerce_input_files(raw: Any) -> Optional[Dict[str, str]]:
    """Normalise the run_skill input_files parameter to a str->str map."""
    if not isinstance(raw, dict) or not raw:
        return None
    return {
        str(name): content if isinstance(content, str) else str(content)
        for name, content in raw.items()
    }


_COMPUTE_SKILL_NAME = "compute"
_COMPUTE_EVENT_OUTPUT_LIMIT = 16384
_COMPUTE_EXECUTOR = "scripts/run_python.py"


def _normalize_compute_parameters(
    command: str,
    input_files: Optional[Dict[str, str]],
) -> tuple:
    """Recover malformed compute invocations instead of failing them opaquely.

    LLM planners sometimes put raw Python in ``command`` (the only sanctioned
    compute command is the bundled executor). Move such code into input_files
    and invoke the executor; likewise, point an argument-less executor command
    at the first provided Python input file.
    """
    stripped = command.strip()
    if _COMPUTE_EXECUTOR in stripped:
        if stripped.endswith(_COMPUTE_EXECUTOR) and input_files:
            main = next((n for n in input_files if n.endswith(".py")), None)
            if main:
                return f"{stripped} {main}", input_files
        return command, input_files
    if input_files:
        main = next((n for n in input_files if n.endswith(".py")), None)
        if main:
            return f"python3 {_COMPUTE_EXECUTOR} {main}", input_files
        return command, input_files
    return f"python3 {_COMPUTE_EXECUTOR} main.py", {"main.py": command}


def _compute_failure_kind(response: Dict[str, Any]) -> str:
    """Classify a failed compute execution for COMPUTATION_FAILED events."""
    if response.get("status") == "timeout":
        return "timeout"
    stderr = response.get("stderr", "") or ""
    if "ImportPolicyViolation:" in stderr:
        return "import_violation"
    if "SyntaxValidationError:" in stderr:
        return "syntax_error"
    if "PathValidationError:" in stderr:
        return "path_violation"
    return "runtime_error"


def _observe_compute_result(
    agent_id: str,
    response: Dict[str, Any],
    input_files: Optional[Dict[str, str]],
) -> None:
    """Emit COMPUTATION_COMPLETED/COMPUTATION_FAILED for a compute skill run."""
    code = "\n".join((input_files or {}).values())
    if response.get("status") == "success":
        observability.observe(
            event_type=observability.ConversationEvents.COMPUTATION_COMPLETED,
            level=observability.EventLevel.INFO,
            data={
                "agent_id": agent_id,
                "code": code,
                "stdout": (response.get("stdout", "") or "")[:_COMPUTE_EVENT_OUTPUT_LIMIT],
                "execution_time_ms": response.get("duration_ms"),
                "artifact_count": len(response.get("artifacts", [])),
            },
            description=f"Computation completed for agent '{agent_id}'",
        )
    else:
        failure_kind = _compute_failure_kind(response)
        observability.observe(
            event_type=observability.ConversationEvents.COMPUTATION_FAILED,
            level=observability.EventLevel.WARNING,
            data={
                "agent_id": agent_id,
                "code": code,
                "stderr": (response.get("stderr", "") or "")[:_COMPUTE_EVENT_OUTPUT_LIMIT],
                "failure_kind": failure_kind,
                "exit_code": response.get("exit_code"),
            },
            description=f"Computation failed for agent '{agent_id}' ({failure_kind})",
        )


async def handle_run_skill(
    agent_id: str,
    parameters: Dict[str, Any],
    overlord: Any,
) -> Dict[str, Any]:
    """Handle the run_skill tool call via RCE."""
    skill_name = parameters.get("skill_name", "")
    command = parameters.get("command", "")
    input_files = _coerce_input_files(parameters.get("input_files"))
    manager = overlord.skill_manager
    rce = overlord.rce_client
    is_compute = skill_name == _COMPUTE_SKILL_NAME
    if is_compute:
        command, input_files = _normalize_compute_parameters(command, input_files)

    try:
        streaming.stream(
            "progress",
            f"Running skill '{skill_name}'...",
            stage="skill_executing",
            skill_name=skill_name,
            command=command,
            agent_name=agent_id,
            skip_rephrase=True,
        )

        if is_compute:
            observability.observe(
                event_type=observability.ConversationEvents.COMPUTATION_REQUESTED,
                level=observability.EventLevel.INFO,
                data={
                    "agent_id": agent_id,
                    "file_names": sorted(input_files) if input_files else [],
                    "code_size_bytes": sum(len(c.encode()) for c in (input_files or {}).values()),
                },
                description=f"Computation requested by agent '{agent_id}'",
            )

        response = await run_skill_command(
            manager, rce, skill_name, command, input_files=input_files
        )

        if is_compute:
            _observe_compute_result(agent_id, response, input_files)

        observability.observe(
            event_type=observability.ConversationEvents.AGENT_MESSAGE_PROCESSING,
            level=observability.EventLevel.INFO,
            data={
                "agent_id": agent_id,
                "skill_name": skill_name,
                "command": command,
                "status": response.get("status"),
                "exit_code": response.get("exit_code"),
                "duration_ms": response.get("duration_ms"),
                "artifact_count": len(response.get("artifacts", [])),
            },
            description=f"Skill '{skill_name}' executed: {response.get('status')}",
        )

        return response

    except Exception as e:
        if is_compute:
            observability.observe(
                event_type=observability.ConversationEvents.COMPUTATION_FAILED,
                level=observability.EventLevel.WARNING,
                data={
                    "agent_id": agent_id,
                    "code": "\n".join((input_files or {}).values()),
                    "stderr": str(e),
                    "failure_kind": "service_error",
                },
                description=f"Computation failed for agent '{agent_id}' (service_error)",
            )
        observability.observe(
            event_type=observability.ErrorEvents.SERVICE_UNAVAILABLE,
            level=observability.EventLevel.ERROR,
            data={
                "agent_id": agent_id,
                "skill_name": skill_name,
                "error": str(e),
            },
            description=f"Skill execution failed: {e}",
        )
        return {"status": "error", "error": str(e)}


def _rce_artifact_to_muxi(
    rce_artifact: Dict[str, Any],
    filename: Optional[str] = None,
) -> MuxiArtifact:
    """Convert an RCE artifact dict to a MuxiArtifact."""
    artifact_name = rce_artifact.get("name", filename or "output")
    artifact_mime = rce_artifact.get("mime", "application/octet-stream")
    artifact_content = rce_artifact.get("content", "")
    artifact_size = rce_artifact.get("size", 0)

    ext = artifact_name.rsplit(".", 1)[-1] if "." in artifact_name else ""
    artifact_type: Literal["text", "document", "image", "data"]
    if artifact_mime.startswith("image/"):
        artifact_type = "image"
    elif artifact_mime.startswith("text/"):
        artifact_type = "text"
    elif ext in ("json", "csv", "xml", "xlsx", "xls"):
        artifact_type = "data"
    else:
        artifact_type = "document"

    return MuxiArtifact(
        type=cast(Literal["text", "document", "image", "data"], artifact_type),
        format=ext,
        filename=artifact_name,
        data_url=f"data:{artifact_mime};base64,{artifact_content}",
        metadata=ArtifactMetadata(
            size_bytes=artifact_size,
            created_at=datetime.datetime.now(),
        ),
    )


async def handle_generate_file_rce(
    agent_id: str,
    code: str,
    filename: Optional[str],
    overlord: Any,
) -> Dict[str, Any]:
    """Handle generate_file via the RCE execution path."""
    rce_client = overlord.rce_client
    skill_manager = overlord.skill_manager

    observability.observe(
        event_type=observability.ConversationEvents.AGENT_RESPONSE_GENERATED,
        level=observability.EventLevel.INFO,
        data={
            "agent_id": agent_id,
            "tool_name": "generate_file",
            "using_rce": True,
        },
        description=f"Agent {agent_id} using RCE for file generation",
    )

    streaming.stream(
        "progress",
        f"Creating {filename or 'file'}...",
        stage="artifact_generating",
        tool_name="generate_file",
        filename=filename,
        agent_name=agent_id,
        skip_rephrase=True,
    )

    try:
        metadata = skill_manager.skills["file-generation"]
        content_hash = skill_manager.get_skill_hash("file-generation")
        await rce_client.ensure_cached("file-generation", metadata.base_dir, content_hash)

        result = await rce_client.run_skill(
            "file-generation",
            "python3 scripts/generate.py code.py",
            input_files={"code.py": code},
            timeout=60,
        )

        if result.status != "success":
            error_msg = result.stderr or f"RCE execution failed (exit {result.exit_code})"
            return {"error": error_msg, "status": "error"}

        if result.artifacts:
            artifact = _rce_artifact_to_muxi(result.artifacts[0], filename)
            response: Dict[str, Any] = {
                "success": True,
                "message": (
                    f"Successfully created {artifact.filename}. "
                    "The file has been automatically attached to this response."
                ),
                "filename": artifact.filename,
                "type": artifact.type,
                "format": artifact.format,
                "size_bytes": artifact.metadata.size_bytes,
                "_artifact": artifact,
            }
        else:
            response = {
                "success": True,
                "message": "Code executed successfully but no output files were generated.",
                "status": result.status,
                "stdout": result.stdout,
            }

        streaming.stream(
            "progress",
            "File created via RCE",
            stage="artifact_created",
            filename=filename,
            skip_rephrase=True,
        )

        return response

    except Exception as e:
        return {"error": str(e), "status": "error"}


async def handle_generate_file_local(
    agent_id: str,
    code: str,
    filename: Optional[str],
    overlord: Any,
) -> Dict[str, Any]:
    """Handle generate_file via the local ArtifactService path."""
    observability.observe(
        event_type=observability.ConversationEvents.AGENT_RESPONSE_GENERATED,
        level=observability.EventLevel.INFO,
        data={
            "agent_id": agent_id,
            "tool_name": "generate_file",
            "parameters": {"code": code[:100], "filename": filename},
            "using_artifact_service": True,
        },
        description=f"Agent {agent_id} using artifact service for file generation",
    )

    streaming.stream(
        "progress",
        f"Creating {filename or 'file'}...",
        stage="artifact_generating",
        tool_name="generate_file",
        filename=filename,
        agent_name=agent_id,
        skip_rephrase=True,
    )

    try:
        artifact = await overlord.artifact_service.generate_file(code, filename)

        result: Dict[str, Any] = {
            "success": True,
            "message": (
                f"Successfully created {artifact.filename}. "
                "The file has been automatically attached to this response."
            ),
            "filename": artifact.filename,
            "type": artifact.type,
            "format": artifact.format,
            "size_bytes": artifact.metadata.size_bytes if artifact.metadata else None,
            "_artifact": artifact,
        }

        streaming.stream(
            "progress",
            f"Created {artifact.filename}",
            stage="artifact_created",
            filename=artifact.filename,
            artifact_type=artifact.type,
            artifact_format=artifact.format,
            skip_rephrase=True,
        )

        observability.observe(
            event_type=observability.ConversationEvents.AGENT_RESPONSE_GENERATED,
            level=observability.EventLevel.INFO,
            data={
                "agent_id": agent_id,
                "tool_name": "generate_file",
                "success": True,
                "artifact_type": artifact.type,
                "artifact_format": artifact.format,
            },
            description=f"Agent {agent_id} successfully generated file using artifact service",
        )

        return result

    except Exception as e:
        return {"error": str(e), "status": "error"}
