"""
Built-in ``delegate_coding`` tool: registration + dispatch helpers.

Registered and dispatched in ``agent.py`` exactly like
``generate_file``/``run_skill``/``get_artifact*``, and ONLY when the
formation declares a ``coding:`` block (the overlord carries a
DelegationService). Formations without the block see no tool at all --
byte-identical behavior, pinned by unit test.

Always asynchronous (hard requirement): the handler returns immediately
with a job handle; completion re-enters the conversation through the
delegation pipeline. Every failure is a friendly
``{"success": False, "error": ...}`` dict, never a raised exception.

Access gating (D3): the ``coding.groups`` resource-side allowlist is
checked against the request's middleware-resolved groups (the gbac
ContextVar); empty/absent = every group may delegate.
"""

from typing import Any, Dict, List, Optional

from ...services import gbac


def coding_tools_available(overlord: Any) -> bool:
    """Whether delegate_coding should exist for this formation."""
    return getattr(overlord, "delegation_service", None) is not None


def build_coding_tools(overlord: Any = None) -> List[Dict[str, Any]]:
    """OpenAI-function definitions for the coding delegation tool."""
    workdirs: List[str] = []
    service = getattr(overlord, "delegation_service", None) if overlord else None
    if service is not None:
        workdirs = list(service.config.workdirs)
    workdir_hint = f" Declared roots: {workdirs} (default: the first)." if workdirs else ""
    return [
        {
            "type": "function",
            "function": {
                "name": "delegate_coding",
                "description": (
                    "Delegate a coding task to the formation's configured headless "
                    "coding CLI as background work. Returns IMMEDIATELY with a job "
                    "id; the run takes minutes and its result re-enters the "
                    "conversation automatically when it completes (status is "
                    "queryable via /jobs). The task runs in a fresh disposable "
                    "working directory -- durable output must be pushed to git by "
                    "the task itself. Pass the user's task verbatim; include any "
                    "repository URLs and concrete instructions in the prompt."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": (
                                "The coding task, passed verbatim to the CLI. Include "
                                "all context the task needs (repo URLs, file names, "
                                "acceptance criteria)."
                            ),
                        },
                        "workdir": {
                            "type": "string",
                            "description": (
                                "Optional: selects one of the formation's declared "
                                "workdir roots." + workdir_hint
                            ),
                        },
                        "model": {
                            "type": "string",
                            "description": (
                                "Optional model override in the coding tool's own "
                                "namespace (passed through opaquely)."
                            ),
                        },
                        "continue_job_id": {
                            "type": "string",
                            "description": (
                                "Optional: resume a previous coding task's session "
                                "with this new prompt (e.g. to answer a question the "
                                "task asked). Use the job id from the earlier "
                                "delegation."
                            ),
                        },
                    },
                    "required": ["prompt"],
                },
            },
        }
    ]


async def handle_delegate_coding(
    agent_id: str,
    parameters: Dict[str, Any],
    overlord: Any,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Dispatch one delegate_coding call (failure-isolated)."""
    service = getattr(overlord, "delegation_service", None)
    if service is None:
        return {
            "success": False,
            "error": "Coding delegation is not configured in this formation",
        }
    try:
        return await service.delegate(
            user_id=user_id if user_id is not None else "0",
            prompt=parameters.get("prompt", ""),
            workdir=parameters.get("workdir"),
            model=parameters.get("model"),
            continue_job_id=parameters.get("continue_job_id"),
            originating_session_id=session_id,
            request_groups=gbac.get_request_groups(),
        )
    except Exception as e:
        return {"success": False, "error": f"Coding delegation failed: {e}"}
