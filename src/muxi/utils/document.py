"""
Document handling utilities for MUXI Framework.

This module provides functions for loading and processing documents.
"""

import os
from typing import List

# Observability integration
from ..services import observability


def load_document(file_path: str) -> str:
    """
    Load a document from a file.

    Args:
        file_path: Path to the file

    Returns:
        The document content as a string
    """
    observability.observe(
        event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_STARTED,
        level=observability.EventLevel.DEBUG,
        description="Starting document loading",
        data={
            "file_path": file_path,
            "operation": "load_document",
            "file_exists": os.path.exists(file_path),
        },
    )

    try:
        if not os.path.exists(file_path):
            observability.observe(
                event_type=observability.ErrorEvents.RESOURCE_NOT_FOUND,
                level=observability.EventLevel.ERROR,
                description="Document loading failed - file not found",
                data={
                    "file_path": file_path,
                    "operation": "load_document",
                    "error": "FileNotFoundError",
                    "error_type": "FileNotFoundError",
                },
            )
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        observability.observe(
            event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_COMPLETED,
            level=observability.EventLevel.DEBUG,
            description="Document loading completed successfully",
            data={
                "file_path": file_path,
                "operation": "load_document",
                "content_length": len(content),
                "content_lines": content.count("\n") + 1 if content else 0,
            },
        )

        return content

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            description="Document loading failed with error",
            data={
                "file_path": file_path,
                "operation": "load_document",
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """
    Split text into overlapping chunks.

    Args:
        text: The text to split
        chunk_size: Maximum size of each chunk
        overlap: Number of characters to overlap between chunks

    Returns:
        List of text chunks
    """
    observability.observe(
        event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_STARTED,
        level=observability.EventLevel.DEBUG,
        description="Starting text chunking",
        data={
            "operation": "chunk_text",
            "text_length": len(text) if text else 0,
            "chunk_size": chunk_size,
            "overlap": overlap,
            "text_empty": not text,
        },
    )

    try:
        if not text:
            observability.observe(
                event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_COMPLETED,
                level=observability.EventLevel.DEBUG,
                description="Text chunking completed - empty text",
                data={
                    "operation": "chunk_text",
                    "text_length": 0,
                    "chunk_count": 0,
                    "chunk_size": chunk_size,
                    "overlap": overlap,
                },
            )

            return []

        chunks = []
        start = 0
        text_length = len(text)

        while start < text_length:
            end = min(start + chunk_size, text_length)

            # If this is not the last chunk, try to find a good break point
            if end < text_length:
                # Try to break at paragraph
                paragraph_break = text.rfind("\n\n", start, end)
                if paragraph_break != -1 and paragraph_break > start + chunk_size // 2:
                    end = paragraph_break + 2  # Include the newlines
                else:
                    # Try to break at sentence
                    sentence_breaks = [".", "!", "?", "\n"]
                    for sep in sentence_breaks:
                        sentence_break = text.rfind(sep, start, end)
                        if sentence_break != -1 and sentence_break > start + chunk_size // 2:
                            end = sentence_break + 1  # Include the separator
                            break

            chunks.append(text[start:end])
            start = max(start, end - overlap)  # Ensure we move forward

        observability.observe(
            event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_COMPLETED,
            level=observability.EventLevel.DEBUG,
            description="Text chunking completed successfully",
            data={
                "operation": "chunk_text",
                "text_length": text_length,
                "chunk_count": len(chunks),
                "chunk_size": chunk_size,
                "overlap": overlap,
                "avg_chunk_size": (
                    sum(len(chunk) for chunk in chunks) / len(chunks) if chunks else 0
                ),
                "min_chunk_size": min(len(chunk) for chunk in chunks) if chunks else 0,
                "max_chunk_size": max(len(chunk) for chunk in chunks) if chunks else 0,
            },
        )

        return chunks

    except Exception as e:
        observability.observe(
            event_type=observability.ErrorEvents.INTERNAL_ERROR,
            level=observability.EventLevel.ERROR,
            description="Text chunking failed with error",
            data={
                "operation": "chunk_text",
                "text_length": len(text) if text else 0,
                "chunk_size": chunk_size,
                "overlap": overlap,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise
