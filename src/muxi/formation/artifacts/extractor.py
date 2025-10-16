"""
Artifact extraction logic for MUXI Runtime.

This module provides functionality to extract artifacts from tool execution results,
specifically looking for file generation results and converting them to MuxiArtifact objects.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List

from .processor import create_artifact_from_file
from ...datatypes.artifacts import ArtifactMetadata, ArtifactPreview, MuxiArtifact
from ...datatypes.clarification import ToolExecutionResult
from ...services import observability


async def extract_artifacts_from_tool_results(
    tool_results: List[ToolExecutionResult]
) -> List[MuxiArtifact]:
    """
    Extract artifacts from tool execution results.

    This function processes a list of tool execution results and extracts any
    artifacts that were generated, specifically looking for results from the
    "generate_file" tool that completed successfully.

    Args:
        tool_results: List of tool execution results to process

    Returns:
        List of MuxiArtifact objects extracted from the tool results.
        Returns empty list if no artifacts found.
    """
    artifacts = []

    # Return empty list if no tool results provided
    if not tool_results:
        # REMOVE - line 41 (DEBUG runtime trace: not initialization)
        return artifacts

    # Process each tool result
    for result in tool_results:
        try:
            tool_name = getattr(result, 'tool_name', 'N/A')
            success = getattr(result, 'success', 'N/A')
            observability.observe(
                event_type=observability.ConversationEvents.MCP_TOOL_CALL_STARTED,
                level=observability.EventLevel.DEBUG,
                data={
                    "service": "artifact",
                    "action": "process_tool_result",
                    "tool_name": tool_name,
                    "success": success,
                },
                description=f"Processing tool result: {tool_name} (success: {success})"
            )

            # Check if this is a successful generate_file tool call
            if (
                isinstance(result, ToolExecutionResult) and
                result.tool_name == "generate_file" and
                result.success is True
            ):
                # Extract file info from the result
                file_info = result.result

                # Check if we have a direct artifact (from new artifact service)
                if isinstance(file_info, dict) and "_artifact" in file_info:
                    artifact = file_info["_artifact"]
                    observability.observe(
                        event_type=observability.ConversationEvents.CONTENT_PROCESSED,
                        level=observability.EventLevel.INFO,
                        data={"service": "artifact", "action": "found_direct_artifact", "filename": artifact.filename},
                        description=f"Found direct artifact: {artifact.filename}"
                    )
                    artifacts.append(artifact)
                    continue

                # Debug log to see what we're getting
                observability.observe(
                    event_type=observability.ConversationEvents.CONTENT_EXTRACTION_STARTED,
                    level=observability.EventLevel.DEBUG,
                    data={"service": "artifact", "action": "parse_tool_result", "result_type": str(type(file_info))},
                    description=f"Tool result type: {type(file_info)}"
                )

                # Handle nested result structure from MCP service
                if isinstance(file_info, dict) and "result" in file_info and "status" in file_info:
                    # This is the MCP service wrapper format
                    actual_result = file_info.get("result", {})
                    if isinstance(actual_result, dict) and "content" in actual_result:
                        # Extract content from modern protocol format
                        content = actual_result.get("content")

                        # Handle the nested content structure
                        if isinstance(content, dict) and "content" in content:
                            # This is the double-nested content structure
                            content_list = content.get("content", [])
                            if isinstance(content_list, list) and len(content_list) > 0:
                                first_content = content_list[0]
                                if isinstance(first_content, dict) and "text" in first_content:
                                    # Extract the JSON string from the text field
                                    json_text = first_content.get("text", "")
                                    try:
                                        file_info = json.loads(json_text)
                                        observability.observe(
                                            event_type=observability.ConversationEvents.CONTENT_EXTRACTION_COMPLETED,
                                            level=observability.EventLevel.DEBUG,
                                            data={
                                                "service": "artifact",
                                                "action": "parse_json",
                                                "source": "text_field",
                                            },
                                            description="Successfully parsed JSON content from text field"
                                        )
                                    except json.JSONDecodeError:
                                        observability.observe(
                                            event_type=observability.ErrorEvents.JSON_PARSE_FAILED,
                                            level=observability.EventLevel.WARNING,
                                            data={
                                                "service": "artifact",
                                                "action": "parse_json",
                                                "error": "json_decode_error",
                                            },
                                            description="Could not parse text as JSON"
                                        )
                                        file_info = actual_result
                                else:
                                    file_info = first_content
                            else:
                                file_info = content
                        elif isinstance(content, str):
                            # Try to parse content as JSON if it's a string
                            try:
                                file_info = json.loads(content)
                                observability.observe(
                                    event_type=observability.ConversationEvents.CONTENT_EXTRACTION_COMPLETED,
                                    level=observability.EventLevel.DEBUG,
                                    data={"service": "artifact", "action": "parse_json", "source": "string_content"},
                                    description="Successfully parsed JSON content from string"
                                )
                            except json.JSONDecodeError:
                                observability.observe(
                                    event_type=observability.ErrorEvents.JSON_PARSE_FAILED,
                                    level=observability.EventLevel.WARNING,
                                    data={"service": "artifact", "action": "parse_json", "error": "json_decode_error"},
                                    description="Could not parse content as JSON"
                                )
                                file_info = actual_result
                        else:
                            file_info = content if isinstance(content, dict) else actual_result
                    else:
                        file_info = actual_result

                # Validate that result is a dict before accessing
                if not isinstance(file_info, dict):
                    observability.observe(
                        event_type=observability.ErrorEvents.VALIDATION_FAILED,
                        level=observability.EventLevel.WARNING,
                        data={"service": "artifact", "action": "validate_result", "result_type": str(type(file_info))},
                        description=f"Tool result for generate_file is not a dict: {type(file_info)}"
                    )
                    continue

                # Check if this is the new format with complete artifact
                if "artifact" in file_info and file_info.get("success") is True:
                    # New format: artifact is already processed
                    artifact_data = file_info["artifact"]

                    # Convert artifact dict back to MuxiArtifact

                    # Create metadata
                    metadata = None
                    if artifact_data.get("metadata"):
                        meta_dict = artifact_data["metadata"]
                        metadata = ArtifactMetadata(
                            created_at=(
                                datetime.fromisoformat(meta_dict["created_at"])
                                if meta_dict.get("created_at")
                                else datetime.now()
                            ),
                            size_bytes=meta_dict.get("size_bytes", 0),
                            lines=meta_dict.get("lines"),
                            characters=meta_dict.get("characters"),
                            language=meta_dict.get("language"),
                            pages=meta_dict.get("pages"),
                            width=meta_dict.get("width"),
                            height=meta_dict.get("height")
                        )

                    # Create preview
                    preview = None
                    if artifact_data.get("preview") and artifact_data["preview"].get("thumbnail"):
                        preview = ArtifactPreview(
                            thumbnail=artifact_data["preview"]["thumbnail"]
                        )

                    # Create artifact
                    artifact = MuxiArtifact(
                        type=artifact_data["type"],
                        format=artifact_data["format"],
                        filename=artifact_data["filename"],
                        content=artifact_data.get("content"),
                        data_url=artifact_data.get("data_url"),
                        metadata=metadata,
                        preview=preview
                    )

                    artifacts.append(artifact)
                    observability.observe(
                        event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_COMPLETED,
                        level=observability.EventLevel.INFO,
                        data={"service": "artifact", "action": "extract_preprocessed", "filename": artifact.filename},
                        description=f"Successfully extracted pre-processed artifact: {artifact.filename}"
                    )
                    continue

                # Old format: check if file_path exists in the result
                file_path = file_info.get("file_path")
                if not file_path:
                    observability.observe(
                        event_type=observability.ErrorEvents.ARTIFACT_FIELD_MISSING,
                        level=observability.EventLevel.WARNING,
                        data={"service": "artifact", "action": "validate_result", "error": "missing_file_path"},
                        description="generate_file result missing both artifact and file_path fields"
                    )
                    continue

                # Create artifact from the file
                try:
                    # Extract additional metadata from the result
                    metadata = {
                        "message": file_info.get("message", ""),
                        "tool_name": "generate_file",
                        # Pass mime_type separately since processor will handle it
                        "mime_type": file_info.get("mime_type", "application/octet-stream"),
                        # Note: size_bytes is handled by processor from actual file
                    }

                    artifact = create_artifact_from_file(file_path, metadata)
                    if artifact:
                        artifacts.append(artifact)
                        observability.observe(
                            event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_COMPLETED,
                            level=observability.EventLevel.INFO,
                            data={"service": "artifact", "action": "extract_from_file", "file": str(file_path)},
                            description=f"Successfully extracted artifact from file: {file_path}"
                        )

                        # Clean up the temporary file now that it's been processed
                        try:
                            file_to_delete = Path(file_path)
                            if file_to_delete.exists() and "muxi_artifacts" in str(file_to_delete):
                                file_to_delete.unlink()
                                observability.observe(
                                    event_type=observability.SystemEvents.CLEANUP,
                                    level=observability.EventLevel.DEBUG,
                                    data={"service": "artifact", "action": "cleanup_temp_file", "file": str(file_path)},
                                    description=f"Cleaned up temporary file: {file_path}"
                                )
                        except Exception as e:
                            observability.observe(
                                event_type=observability.SystemEvents.CLEANUP,
                                level=observability.EventLevel.DEBUG,
                                data={
                                    "service": "artifact",
                                    "action": "cleanup_temp_file",
                                    "file": str(file_path),
                                    "error": str(e),
                                },
                                description=f"Could not clean up temporary file {file_path}: {e}"
                            )
                except Exception as e:
                    observability.observe(
                        event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                        level=observability.EventLevel.ERROR,
                        data={
                            "service": "artifact",
                            "action": "create_from_file",
                            "file": str(file_path),
                            "error": str(e),
                        },
                        description=f"Failed to create artifact from file {file_path}: {str(e)}"
                    )
                    continue

        except Exception as e:
            # Log error but continue processing other results
            observability.observe(
                event_type=observability.ConversationEvents.MCP_TOOL_CALL_FAILED,
                level=observability.EventLevel.ERROR,
                data={"service": "artifact", "action": "process_tool_result", "error": str(e)},
                description=f"Error processing tool result: {str(e)}"
            )
            continue

    # Only log if artifacts were actually extracted
    if artifacts:
        observability.observe(
            event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_COMPLETED,
            level=observability.EventLevel.INFO,
            data={"service": "artifact", "action": "extract_from_tools", "artifacts_count": len(artifacts)},
            description=f"Extracted {len(artifacts)} artifacts from tool results"
        )

    # Optional: Clean up the entire muxi_artifacts directory if it's empty
    try:
        muxi_artifacts_dir = Path(tempfile.gettempdir()) / "muxi_artifacts"
        if muxi_artifacts_dir.exists() and not any(muxi_artifacts_dir.iterdir()):
            muxi_artifacts_dir.rmdir()
            observability.observe(
                event_type=observability.SystemEvents.CLEANUP,
                level=observability.EventLevel.DEBUG,
                data={"service": "artifact", "action": "cleanup_artifacts_dir"},
                description="Cleaned up empty muxi_artifacts directory"
            )
    except Exception:
        pass  # Ignore any cleanup errors

    return artifacts
