"""Dispatch handlers for skill-related tools (activate_skill, run_skill, generate_file).

Extracted from agent.py invoke_tool() to keep the main agent module focused
on core message processing.
"""

import datetime
from typing import Any, Dict, Optional

from ...datatypes.artifacts import ArtifactMetadata, MuxiArtifact
from ...services import observability, streaming


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

    content = await manager.activate_async(skill_name, session_id)

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


async def handle_run_skill(
    agent_id: str,
    parameters: Dict[str, Any],
    overlord: Any,
) -> Dict[str, Any]:
    """Handle the run_skill tool call via RCE."""
    skill_name = parameters.get("skill_name", "")
    command = parameters.get("command", "")
    manager = overlord.skill_manager
    rce = overlord.rce_client

    if skill_name not in manager.skills:
        return {"status": "error", "error": f"Skill '{skill_name}' not found."}

    metadata = manager.skills[skill_name]
    content_hash = manager.get_skill_hash(skill_name)

    streaming.stream(
        "progress",
        f"Running skill '{skill_name}'...",
        stage="skill_executing",
        skill_name=skill_name,
        command=command,
        agent_name=agent_id,
        skip_rephrase=True,
    )

    try:
        await rce.ensure_cached(skill_name, metadata.base_dir, content_hash)

        skill_env = await manager.resolve_skill_env(skill_name)
        result = await rce.run_skill(skill_name, command, timeout=60, env=skill_env or None)

        observability.observe(
            event_type=observability.ConversationEvents.AGENT_MESSAGE_PROCESSING,
            level=observability.EventLevel.INFO,
            data={
                "agent_id": agent_id,
                "skill_name": skill_name,
                "command": command,
                "status": result.status,
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
                "artifact_count": len(result.artifacts),
            },
            description=f"Skill '{skill_name}' executed: {result.status}",
        )

        response: Dict[str, Any] = {
            "status": result.status,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "duration_ms": result.duration_ms,
        }
        if result.stderr:
            response["stderr"] = result.stderr
        if result.artifacts:
            response["artifacts"] = [
                {"name": a["name"], "mime": a["mime"], "size": a["size"]} for a in result.artifacts
            ]
            response["_artifacts_full"] = result.artifacts
        return response

    except Exception as e:
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
    if artifact_mime.startswith("image/"):
        artifact_type = "image"
    elif artifact_mime.startswith("text/"):
        artifact_type = "text"
    elif ext in ("json", "csv", "xml", "xlsx", "xls"):
        artifact_type = "data"
    else:
        artifact_type = "document"

    return MuxiArtifact(
        type=artifact_type,
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
