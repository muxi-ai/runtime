#!/usr/bin/env python3
"""
Shared utilities for Day 5 tests
"""

import re


def clean_empty_links(content):
    """
    Remove empty markdown links from content.
    Converts [filename.ext]() to just filename.ext
    """
    # Pattern to match markdown links with empty parentheses
    # Captures the link text and preserves any formatting
    pattern = r"\[([^\]]+)\]\(\s*\)"

    # Replace with just the link text (filename)
    cleaned = re.sub(pattern, r"\1", content)

    return cleaned


def format_response(response):
    """Format response object for JSON serialization"""
    if isinstance(response, dict):
        return response

    # Create basic result matching the expected structure
    result = {
        "role": "assistant",
        "content": str(response.content) if hasattr(response, "content") else str(response),
        "artifacts": [],
    }

    # Clean empty links from content
    result["content"] = clean_empty_links(result["content"])

    # Handle artifacts if present
    if hasattr(response, "artifacts") and response.artifacts:
        for artifact in response.artifacts:
            # Create artifact structure matching MuxiArtifact format
            artifact_dict = {
                "type": artifact.type if hasattr(artifact, "type") else "unknown",
                "format": artifact.format if hasattr(artifact, "format") else "unknown",
                "filename": artifact.filename if hasattr(artifact, "filename") else "unknown.txt",
                "preview": None,
                "metadata": {},
                "content": None,
                "data_url": None,
            }

            # Add preview if present
            if hasattr(artifact, "preview") and artifact.preview:
                artifact_dict["preview"] = {
                    "thumbnail": (
                        artifact.preview.thumbnail
                        if hasattr(artifact.preview, "thumbnail")
                        else None
                    )
                }

            # Add metadata if present
            if hasattr(artifact, "metadata") and artifact.metadata:
                metadata = artifact.metadata
                artifact_dict["metadata"] = {
                    "size_bytes": metadata.size_bytes if hasattr(metadata, "size_bytes") else 0,
                    "created_at": (
                        str(metadata.created_at) if hasattr(metadata, "created_at") else None
                    ),
                    "lines": metadata.lines if hasattr(metadata, "lines") else None,
                    "characters": metadata.characters if hasattr(metadata, "characters") else None,
                    "language": metadata.language if hasattr(metadata, "language") else None,
                    "pages": metadata.pages if hasattr(metadata, "pages") else None,
                    "width": metadata.width if hasattr(metadata, "width") else None,
                    "height": metadata.height if hasattr(metadata, "height") else None,
                }

            # Determine if this is a text or binary file
            # Check artifact type or infer from format/content
            is_text_file = False

            # First check if artifact has explicit type
            if hasattr(artifact, "type") and artifact.type == "text":
                is_text_file = True
            # Otherwise check if we have content (indicating text)
            elif hasattr(artifact, "content") and artifact.content:
                is_text_file = True
            # If we have data_url, check if it starts with text MIME type
            elif hasattr(artifact, "data_url") and artifact.data_url:
                if artifact.data_url.startswith("data:text/"):
                    is_text_file = True

            # Handle content based on file type
            if is_text_file:
                # For text files, put content directly in content field
                if hasattr(artifact, "content") and artifact.content:
                    artifact_dict["content"] = artifact.content
                    artifact_dict["data_url"] = None
                elif hasattr(artifact, "data_url") and artifact.data_url:
                    # If we have base64 data for a text file, decode it
                    try:
                        import base64

                        if artifact.data_url.startswith("data:"):
                            # Extract base64 part
                            base64_data = artifact.data_url.split(",")[1]
                        else:
                            base64_data = artifact.data_url
                        decoded_content = base64.b64decode(base64_data).decode("utf-8")
                        artifact_dict["content"] = decoded_content
                        artifact_dict["data_url"] = None
                    except Exception:
                        # If decoding fails, keep as data_url
                        artifact_dict["data_url"] = artifact.data_url
            else:
                # For binary files, use data_url with appropriate MIME type
                if hasattr(artifact, "data_url") and artifact.data_url:
                    artifact_dict["data_url"] = artifact.data_url
                    # Ensure it has proper data: prefix
                    if not artifact.data_url.startswith("data:"):
                        # Infer MIME type from format or use generic binary
                        if artifact.format:
                            artifact_dict["data_url"] = (
                                f"data:application/{artifact.format};base64,{artifact.data_url}"
                            )
                        else:
                            artifact_dict["data_url"] = (
                                f"data:application/octet-stream;base64,{artifact.data_url}"
                            )

            result["artifacts"].append(artifact_dict)

    return result
