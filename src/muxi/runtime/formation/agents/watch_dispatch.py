"""
Built-in ``watch_job`` tool: registration + dispatch helpers.

Registered and dispatched in ``agent.py`` exactly like
``delegate_coding``/``recall_history``, and ONLY when the overlord
carries a WatchService (default ON whenever the formation declares MCP
servers; ``mcp: { watch: false }`` removes the tool entirely).
Formations without MCP servers see no tool at all.

Always asynchronous (PRD D3): the handler returns immediately with a job
handle; the poll loop runs in the background and completion re-enters
the conversation through the watch pipeline. Every failure is a friendly
``{"success": False, "error": ...}`` dict, never a raised exception.

Cadence and deadline are deliberately NOT tool parameters (owner ruling
2026-07-11): they are formation configuration (``mcp.watch``), because
numeric knobs are exactly what LLMs pick badly.

The SOP fragment: a bundled markdown fragment (dormant-template posture,
the heartbeat default-SOP convention) is appended to every agent's
system message whenever watch_job registers, teaching the recognition
behavior (job-shaped response -> watch_job -> acknowledge). A
formation-local ``sops/watch_job.md`` shadows the bundled text (empty
file = removed) -- editable/removable like any SOP.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

# Bundled default watch SOP fragment (shipped as content next to this
# module, same convention as the bundled heartbeat SOP).
BUILTIN_WATCH_SOP_PATH = Path(__file__).parent / "builtin" / "watch_sop.md"

# Last-resort minimal fragment, used only if the bundled file cannot be
# read (broken install). Recognition guidance must never silently vanish.
DEFAULT_WATCH_SOP = (
    "When a tool responds with a job identifier and a non-terminal status "
    "instead of a result, call watch_job with the service's status tool "
    "and a done_when matching its terminal states. Tell the user the work "
    "is underway and that you will report back. Do not repeatedly re-call "
    "the original tool."
)

_default_watch_sop: Optional[str] = None


def load_default_watch_sop() -> str:
    """Load the bundled watch SOP fragment (cached after the first read)."""
    global _default_watch_sop
    if _default_watch_sop is None:
        try:
            content = BUILTIN_WATCH_SOP_PATH.read_text(encoding="utf-8").strip()
        except OSError:
            content = ""
        _default_watch_sop = content or DEFAULT_WATCH_SOP
    return _default_watch_sop


def _reset_default_sop_cache() -> None:
    """Test isolation only (heartbeat precedent); production never needs it."""
    global _default_watch_sop
    _default_watch_sop = None


def watch_sop_fragment(overlord: Any) -> Optional[str]:
    """The SOP fragment to append to agent instructions, or None.

    Present whenever the formation registers watch_job (a parsed
    ``watch_config`` exists in the configured-services bundle -- the
    WatchService itself is created after agents load, so registration
    intent, not the live service, is the signal here). A formation-local
    ``sops/watch_job.md`` shadows the bundled fragment; an empty file
    removes it.
    """
    configured = getattr(overlord, "_configured_services", None) or {}
    if configured.get("watch_config") is None:
        return None

    formation_dir = configured.get("formation_path")
    if formation_dir:
        local = Path(formation_dir) / "sops" / "watch_job.md"
        if local.is_file():
            try:
                content = local.read_text(encoding="utf-8").strip()
            except OSError:
                content = None
            return content or None  # empty file = fragment removed
    return load_default_watch_sop()


def watch_tools_available(overlord: Any) -> bool:
    """Whether watch_job should exist for this formation."""
    return getattr(overlord, "watch_service", None) is not None


def build_watch_tools() -> List[Dict[str, Any]]:
    """OpenAI-function definition for the watch_job built-in."""
    return [
        {
            "type": "function",
            "function": {
                "name": "watch_job",
                "description": (
                    "Watch an asynchronous remote job until it finishes. Use this "
                    "when a tool returns a job identifier with a non-terminal "
                    "status (e.g. {'job_id': ..., 'status': 'processing'}) instead "
                    "of a result. Returns IMMEDIATELY with a watch handle; the "
                    "runtime polls the named status tool in the background and the "
                    "finished result re-enters the conversation automatically "
                    "(status is queryable via /jobs). Poll cadence and deadline "
                    "are formation configuration -- do not attempt to control "
                    "them. Do not re-call the original tool while a watch is "
                    "active."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool": {
                            "type": "string",
                            "description": (
                                "The status/poll tool to call on each poll -- any "
                                "MCP tool visible to you (e.g. 'image-gen.check_status' "
                                "or just 'check_status')."
                            ),
                        },
                        "args": {
                            "type": "object",
                            "description": (
                                "Arguments passed to the status tool on every poll "
                                "(typically the job id from the submit response)."
                            ),
                        },
                        "done_when": {
                            "type": "object",
                            "description": (
                                "Deterministic terminal condition: {'path': '$.status', "
                                "'equals': 'succeeded'} or {'path': '$.status', 'in': "
                                "['succeeded', 'failed', 'canceled']}. Include every "
                                "terminal state the service can report, not just "
                                "success -- otherwise a failed job polls until the "
                                "deadline."
                            ),
                            "properties": {
                                "path": {"type": "string"},
                                "equals": {},
                                "in": {"type": "array"},
                            },
                            "required": ["path"],
                        },
                        "result": {
                            "type": "string",
                            "description": (
                                "Optional selector extracting the result from the "
                                "final poll body (e.g. '$.output'); default: the "
                                "full final body."
                            ),
                        },
                        "label": {
                            "type": "string",
                            "description": (
                                "Optional short human-readable label shown on /jobs "
                                "(e.g. 'logo render')."
                            ),
                        },
                    },
                    "required": ["tool", "done_when"],
                },
            },
        }
    ]


async def handle_watch_job(
    agent_id: str,
    parameters: Dict[str, Any],
    overlord: Any,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Dispatch one watch_job call (failure-isolated)."""
    service = getattr(overlord, "watch_service", None)
    if service is None:
        return {
            "success": False,
            "error": "Job watching is not available in this formation",
        }
    try:
        return await service.watch(
            agent_id=agent_id,
            user_id=user_id if user_id is not None else "0",
            tool=parameters.get("tool"),
            args=parameters.get("args"),
            done_when=parameters.get("done_when"),
            result=parameters.get("result"),
            label=parameters.get("label"),
            originating_session_id=session_id,
        )
    except Exception as e:
        return {"success": False, "error": f"watch_job failed: {e}"}
