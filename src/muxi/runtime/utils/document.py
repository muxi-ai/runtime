"""
Document handling utilities for MUXI Framework.

This module provides functions for loading and processing documents.
"""

import os
from typing import List

# Observability integration
try:
    from ..observability import ObservabilityManager, ConversationEventType, SystemEventType, EventLevel
except ImportError:
    # Graceful fallback if observability is not available
    ObservabilityManager = None
    ConversationEventType = None
    EventLevel = None


def load_document(file_path: str) -> str:
    """
    Load a document from a file.

    Args:
        file_path: Path to the file

    Returns:
        The document content as a string
    """
    if ObservabilityManager and ConversationEventType:
        try:
            ObservabilityManager.get_instance().log_event(
                event_type=ConversationEventType.DOCUMENT_PROCESSING_STARTED,
                level=EventLevel.DEBUG,
                message="Starting document loading",
                data={
                    "file_path": file_path,
                    "operation": "load_document",
                    "file_exists": os.path.exists(file_path)
                }
            )
        except Exception:
            pass

    try:
        if not os.path.exists(file_path):
            if ObservabilityManager and ConversationEventType:
                try:
                    ObservabilityManager.get_instance().log_event(
                        event_type=ConversationEventType.ERROR_RETRY_ATTEMPTED,
                        level=EventLevel.ERROR,
                        message="Document loading failed - file not found",
                        data={
                            "file_path": file_path,
                            "operation": "load_document",
                            "error": "FileNotFoundError",
                            "error_type": "FileNotFoundError"
                        }
                    )
                except Exception:
                    pass
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if ObservabilityManager and ConversationEventType:
            try:
                ObservabilityManager.get_instance().log_event(
                    event_type=ConversationEventType.DOCUMENT_PROCESSING_COMPLETED,
                    level=EventLevel.DEBUG,
                    message="Document loading completed successfully",
                    data={
                        "file_path": file_path,
                        "operation": "load_document",
                        "content_length": len(content),
                        "content_lines": content.count('\n') + 1 if content else 0
                    }
                )
            except Exception:
                pass

        return content

    except Exception as e:
        if ObservabilityManager and ConversationEventType:
            try:
                ObservabilityManager.get_instance().log_event(
                    event_type=ConversationEventType.ERROR_RETRY_ATTEMPTED,
                    level=EventLevel.ERROR,
                    message="Document loading failed with error",
                    data={
                        "file_path": file_path,
                        "operation": "load_document",
                        "error": str(e),
                        "error_type": type(e).__name__
                    }
                )
            except Exception:
                pass
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
    if ObservabilityManager and ConversationEventType:
        try:
            ObservabilityManager.get_instance().log_event(
                event_type=ConversationEventType.DOCUMENT_PROCESSING_STARTED,
                level=EventLevel.DEBUG,
                message="Starting text chunking",
                data={
                    "operation": "chunk_text",
                    "text_length": len(text) if text else 0,
                    "chunk_size": chunk_size,
                    "overlap": overlap,
                    "text_empty": not text
                }
            )
        except Exception:
            pass

    try:
        if not text:
            if ObservabilityManager and ConversationEventType:
                try:
                    ObservabilityManager.get_instance().log_event(
                        event_type=ConversationEventType.DOCUMENT_PROCESSING_COMPLETED,
                        level=EventLevel.DEBUG,
                        message="Text chunking completed - empty text",
                        data={
                            "operation": "chunk_text",
                            "text_length": 0,
                            "chunk_count": 0,
                            "chunk_size": chunk_size,
                            "overlap": overlap
                        }
                    )
                except Exception:
                    pass
            return []

        chunks = []
        start = 0
        text_length = len(text)

        while start < text_length:
            end = min(start + chunk_size, text_length)

            # If this is not the last chunk, try to find a good break point
            if end < text_length:
                # Try to break at paragraph
                paragraph_break = text.rfind('\n\n', start, end)
                if paragraph_break != -1 and paragraph_break > start + chunk_size // 2:
                    end = paragraph_break + 2  # Include the newlines
                else:
                    # Try to break at sentence
                    sentence_breaks = ['.', '!', '?', '\n']
                    for sep in sentence_breaks:
                        sentence_break = text.rfind(sep, start, end)
                        if sentence_break != -1 and sentence_break > start + chunk_size // 2:
                            end = sentence_break + 1  # Include the separator
                            break

            chunks.append(text[start:end])
            start = max(start, end - overlap)  # Ensure we move forward

        if ObservabilityManager and ConversationEventType:
            try:
                ObservabilityManager.get_instance().log_event(
                    event_type=ConversationEventType.DOCUMENT_PROCESSING_COMPLETED,
                    level=EventLevel.DEBUG,
                    message="Text chunking completed successfully",
                    data={
                        "operation": "chunk_text",
                        "text_length": text_length,
                        "chunk_count": len(chunks),
                        "chunk_size": chunk_size,
                        "overlap": overlap,
                        "avg_chunk_size": (
                            sum(len(chunk) for chunk in chunks) / len(chunks)
                            if chunks else 0
                        ),
                        "min_chunk_size": min(len(chunk) for chunk in chunks) if chunks else 0,
                        "max_chunk_size": max(len(chunk) for chunk in chunks) if chunks else 0
                    }
                )
            except Exception:
                pass

        return chunks

    except Exception as e:
        if ObservabilityManager and ConversationEventType:
            try:
                ObservabilityManager.get_instance().log_event(
                    event_type=ConversationEventType.ERROR_RETRY_ATTEMPTED,
                    level=EventLevel.ERROR,
                    message="Text chunking failed with error",
                    data={
                        "operation": "chunk_text",
                        "text_length": len(text) if text else 0,
                        "chunk_size": chunk_size,
                        "overlap": overlap,
                        "error": str(e),
                        "error_type": type(e).__name__
                    }
                )
            except Exception:
                pass
        raise
