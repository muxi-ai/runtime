"""
Artifact extraction logic for MUXI Runtime.

This module provides functionality to extract artifacts from tool execution results,
specifically looking for file generation results and converting them to MuxiArtifact objects.
"""

import logging
from typing import List

from .processor import create_artifact_from_file
from ...datatypes.artifacts import MuxiArtifact
from ...datatypes.clarification import ToolExecutionResult

# Set up logger
logger = logging.getLogger(__name__)


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
        logger.debug("No tool results provided for artifact extraction")
        return artifacts

    # Process each tool result
    for result in tool_results:
        try:
            logger.info(
                f"Processing tool result: tool_name={getattr(result, 'tool_name', 'N/A')}, "
                f"success={getattr(result, 'success', 'N/A')}"
            )

            # Check if this is a successful generate_file tool call
            if (
                isinstance(result, ToolExecutionResult) and
                result.tool_name == "generate_file" and
                result.success is True
            ):
                # Extract file info from the result
                file_info = result.result

                # Debug log to see what we're getting
                logger.info(f"Tool result type: {type(file_info)}, value: {file_info}")

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
                                        import json
                                        file_info = json.loads(json_text)
                                        logger.info(f"Parsed JSON content: {file_info}")
                                    except json.JSONDecodeError:
                                        logger.warning(f"Could not parse text as JSON: {json_text}")
                                        file_info = actual_result
                                else:
                                    file_info = first_content
                            else:
                                file_info = content
                        elif isinstance(content, str):
                            # Try to parse content as JSON if it's a string
                            try:
                                import json
                                file_info = json.loads(content)
                                logger.info(f"Parsed JSON content: {file_info}")
                            except json.JSONDecodeError:
                                logger.warning(f"Could not parse content as JSON: {content}")
                                file_info = actual_result
                        else:
                            file_info = content if isinstance(content, dict) else actual_result
                    else:
                        file_info = actual_result

                # Validate that result is a dict before accessing
                if not isinstance(file_info, dict):
                    logger.warning(
                        f"Tool result for generate_file is not a dict: {type(file_info)}"
                    )
                    continue

                # Check if file_path exists in the result
                file_path = file_info.get("file_path")
                if not file_path:
                    logger.warning(
                        "generate_file result missing file_path field"
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
                        logger.info(
                            f"Successfully extracted artifact from file: {file_path}"
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to create artifact from file {file_path}: {str(e)}"
                    )
                    continue

        except Exception as e:
            # Log error but continue processing other results
            logger.error(
                f"Error processing tool result: {str(e)}"
            )
            continue

    logger.info(f"Extracted {len(artifacts)} artifacts from tool results")
    return artifacts
