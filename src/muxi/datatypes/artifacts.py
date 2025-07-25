"""Artifact data models for MUXI runtime."""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel


class ArtifactMetadata(BaseModel):
    """Metadata for an artifact."""

    size_bytes: int
    created_at: datetime
    lines: Optional[int] = None
    characters: Optional[int] = None
    language: Optional[str] = None
    pages: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None


class ArtifactPreview(BaseModel):
    """Preview data for an artifact."""

    thumbnail: Optional[str] = None  # Base64 encoded image data


class MuxiArtifact(BaseModel):
    """Represents an artifact in the MUXI system."""

    type: Literal["text", "document", "image", "data"]
    format: str  # e.g., "txt", "pdf", "png", "json"
    filename: str
    preview: Optional[ArtifactPreview] = None
    metadata: ArtifactMetadata
    content: Optional[str] = None  # For text files
    data_url: Optional[str] = None  # For binary files
