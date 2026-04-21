"""
a2a-sdk 1.0.x protobuf glue.

The 1.0 SDK exposes its wire types (Part, Message, AgentCard, ...) as
protobuf generated classes rather than pydantic models. Working with them
directly sprinkles `WhichOneof`, `HasField`, `struct_pb2.Value` wrapping, and
`MessageToDict` conversions across the codebase — unpleasant and brittle.

This module centralizes that glue so the rest of the runtime can stay in
ordinary Python dict / string land. Every other a2a/* module routes through
these helpers.

Design notes
------------
* `Part.data` is `google.protobuf.Value`. We wrap python dicts via
  `Struct().update(d)` + `Value(struct_value=struct)`.
* `Message.metadata` is `google.protobuf.Struct`. We build it from a plain
  dict in `make_message`.
* Role / TaskState are protobuf EnumTypeWrapper; we expose the integer
  values via named constants and lowercase names via `role_name` /
  `task_state_name`.
* `message_to_dict` / `agent_card_to_dict` return plain python dicts; nested
  structs come back with number fields as float (a protobuf quirk).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from a2a.types import (
    AgentCard,
    Message,
    Part,
    Role,
    TaskState,
)
from google.protobuf.json_format import MessageToDict
from google.protobuf.struct_pb2 import Struct, Value

# ---------------------------------------------------------------------------
# Role / TaskState constants
# ---------------------------------------------------------------------------

ROLE_USER: int = Role.ROLE_USER
ROLE_AGENT: int = Role.ROLE_AGENT


def role_name(role: int) -> str:
    """Return a lowercase MUXI-friendly name for a protobuf Role int."""
    if role == Role.ROLE_USER:
        return "user"
    if role == Role.ROLE_AGENT:
        return "agent"
    return "unspecified"


def role_from_name(name: Optional[str]) -> int:
    """Resolve a MUXI role name to the protobuf integer value."""
    if not name:
        return Role.ROLE_USER
    lowered = name.lower()
    if lowered in ("agent", "assistant", "system"):
        return Role.ROLE_AGENT
    return Role.ROLE_USER


def task_state_name(state: int) -> str:
    """Return a lowercase MUXI-friendly name for a protobuf TaskState int."""
    return {
        TaskState.TASK_STATE_SUBMITTED: "submitted",
        TaskState.TASK_STATE_WORKING: "working",
        TaskState.TASK_STATE_COMPLETED: "completed",
        TaskState.TASK_STATE_FAILED: "failed",
        TaskState.TASK_STATE_CANCELED: "canceled",
        TaskState.TASK_STATE_INPUT_REQUIRED: "input_required",
        TaskState.TASK_STATE_REJECTED: "rejected",
        TaskState.TASK_STATE_AUTH_REQUIRED: "auth_required",
    }.get(state, "unspecified")


# ---------------------------------------------------------------------------
# Struct <-> dict conversions
# ---------------------------------------------------------------------------


def dict_to_struct(data: Optional[Dict[str, Any]]) -> Optional[Struct]:
    """Build a protobuf Struct from a plain python dict, or return None."""
    if not data:
        return None
    struct = Struct()
    struct.update(data)
    return struct


def struct_to_dict(struct: Optional[Struct]) -> Dict[str, Any]:
    """Convert a protobuf Struct to a plain python dict (empty if falsy)."""
    if not struct:
        return {}
    try:
        return MessageToDict(struct)
    except Exception:
        # Fallback: iterate keys directly.
        return {k: _value_to_python(v) for k, v in struct.fields.items()}


def _value_to_python(value: Value) -> Any:
    """Convert a google.protobuf.Value to a plain python value."""
    kind = value.WhichOneof("kind")
    if kind == "string_value":
        return value.string_value
    if kind == "number_value":
        return value.number_value
    if kind == "bool_value":
        return value.bool_value
    if kind == "null_value":
        return None
    if kind == "struct_value":
        return {k: _value_to_python(v) for k, v in value.struct_value.fields.items()}
    if kind == "list_value":
        return [_value_to_python(v) for v in value.list_value.values]
    return None


# ---------------------------------------------------------------------------
# Part construction + inspection
# ---------------------------------------------------------------------------


def make_text_part(text: str, metadata: Optional[Dict[str, Any]] = None) -> Part:
    """Construct a Part holding a text content value."""
    kwargs: Dict[str, Any] = {"text": text or ""}
    meta = dict_to_struct(metadata)
    if meta is not None:
        kwargs["metadata"] = meta
    return Part(**kwargs)


def make_data_part(data: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> Part:
    """Construct a Part holding a structured data value (Struct-wrapped)."""
    struct = Struct()
    struct.update(data or {})
    part_kwargs: Dict[str, Any] = {"data": Value(struct_value=struct)}
    meta = dict_to_struct(metadata)
    if meta is not None:
        part_kwargs["metadata"] = meta
    return Part(**part_kwargs)


def make_file_part(
    *,
    filename: Optional[str] = None,
    media_type: Optional[str] = None,
    url: Optional[str] = None,
    raw: Optional[bytes] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Part:
    """Construct a Part for a file reference, either by URL or raw bytes."""
    kwargs: Dict[str, Any] = {}
    if url is not None:
        kwargs["url"] = url
    if raw is not None:
        kwargs["raw"] = raw
    if filename is not None:
        kwargs["filename"] = filename
    if media_type is not None:
        kwargs["media_type"] = media_type
    meta = dict_to_struct(metadata)
    if meta is not None:
        kwargs["metadata"] = meta
    return Part(**kwargs)


def part_kind(part: Part) -> Optional[str]:
    """Return 'text' | 'data' | 'raw' | 'url' | None for a Part."""
    return part.WhichOneof("content")


def part_text(part: Part) -> Optional[str]:
    """Return the text payload of a Part, or None when it's not a text part."""
    if part.HasField("text"):
        return part.text
    return None


def part_data(part: Part) -> Optional[Dict[str, Any]]:
    """Return the python dict payload of a data Part, or None."""
    if not part.HasField("data"):
        return None
    return _value_to_python(part.data)


def part_metadata(part: Part) -> Dict[str, Any]:
    """Return the metadata dict attached to a Part (empty if unset)."""
    if part.HasField("metadata"):
        return struct_to_dict(part.metadata)
    return {}


# ---------------------------------------------------------------------------
# Message construction + inspection
# ---------------------------------------------------------------------------


def make_message(
    *,
    message_id: str,
    role: int,
    parts: List[Part],
    metadata: Optional[Dict[str, Any]] = None,
    context_id: Optional[str] = None,
    task_id: Optional[str] = None,
) -> Message:
    """Construct a Message with optional metadata/context/task linkage."""
    kwargs: Dict[str, Any] = {
        "message_id": message_id,
        "role": role,
        "parts": parts,
    }
    meta = dict_to_struct(metadata)
    if meta is not None:
        kwargs["metadata"] = meta
    if context_id:
        kwargs["context_id"] = context_id
    if task_id:
        kwargs["task_id"] = task_id
    return Message(**kwargs)


def message_metadata(message: Message) -> Dict[str, Any]:
    """Return the metadata dict attached to a Message (empty if unset)."""
    if message.HasField("metadata"):
        return struct_to_dict(message.metadata)
    return {}


def message_to_dict(message: Message) -> Dict[str, Any]:
    """Serialize a Message to a plain python dict."""
    try:
        return MessageToDict(message, preserving_proto_field_name=True)
    except Exception:
        # Fallback: hand-build the dict from known fields.
        return {
            "message_id": message.message_id,
            "role": role_name(message.role),
            "parts": [_part_to_dict(p) for p in message.parts],
            "metadata": message_metadata(message),
        }


def _part_to_dict(part: Part) -> Dict[str, Any]:
    """Serialize a single Part to a plain python dict in MUXI style."""
    out: Dict[str, Any] = {}
    kind = part_kind(part)
    if kind == "text":
        out["type"] = "TextPart"
        out["text"] = part.text
    elif kind == "data":
        out["type"] = "DataPart"
        out["data"] = part_data(part) or {}
    elif kind == "raw":
        out["type"] = "FilePart"
        out["raw"] = part.raw
    elif kind == "url":
        out["type"] = "FilePart"
        out["url"] = part.url
    if part.filename:
        out["filename"] = part.filename
    if part.media_type:
        out["media_type"] = part.media_type
    meta = part_metadata(part)
    if meta:
        out["metadata"] = meta
    return out


def parts_to_muxi_list(parts) -> List[Dict[str, Any]]:
    """Convert an iterable of Parts to a MUXI-style parts list."""
    return [_part_to_dict(p) for p in parts]


def muxi_part_to_sdk(part_dict: Dict[str, Any]) -> Part:
    """Convert one MUXI-style part dict back into an SDK Part."""
    part_type = (part_dict.get("type") or "").lower()
    meta = part_dict.get("metadata") or None
    if part_type in ("textpart", "text"):
        return make_text_part(part_dict.get("text", ""), metadata=meta)
    if part_type in ("datapart", "data"):
        return make_data_part(part_dict.get("data") or {}, metadata=meta)
    if part_type in ("filepart", "file"):
        return make_file_part(
            filename=part_dict.get("filename"),
            media_type=part_dict.get("media_type"),
            url=part_dict.get("url"),
            raw=part_dict.get("raw"),
            metadata=meta,
        )
    # Unknown type: fall back to text with empty content.
    return make_text_part(str(part_dict.get("text") or ""), metadata=meta)


# ---------------------------------------------------------------------------
# AgentCard helpers
# ---------------------------------------------------------------------------


def agent_card_to_dict(card: AgentCard) -> Dict[str, Any]:
    """Serialize an AgentCard to a plain python dict."""
    try:
        return MessageToDict(card, preserving_proto_field_name=True)
    except Exception:
        return {"name": card.name, "description": card.description, "version": card.version}
