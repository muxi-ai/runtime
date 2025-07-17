"""File processing utilities for MUXI artifacts."""

from pathlib import Path
import base64
import mimetypes
import io
from typing import Optional, Dict, Any, Tuple
from datetime import datetime

# Import PIL/Pillow with graceful error handling
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Import pdf2image with graceful error handling
try:
    from pdf2image import convert_from_path
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False

from ...datatypes.artifacts import MuxiArtifact, ArtifactMetadata, ArtifactPreview

# Define file type extensions
TEXT_EXTENSIONS = {'.txt', '.md', '.html', '.css', '.js', '.py', '.json', '.yaml', '.yml', '.xml', '.csv', '.log'}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'}
DOCUMENT_EXTENSIONS = {'.pdf', '.docx', '.xlsx', '.pptx'}


def generate_image_thumbnail(file_path: Path, max_size: Tuple[int, int] = (200, 200)) -> Optional[str]:
    """
    Generate a thumbnail for an image file.

    Args:
        file_path: Path to the image file
        max_size: Maximum size for the thumbnail (width, height)

    Returns:
        Base64 encoded PNG thumbnail string, or None if error or not an image
    """
    if not PIL_AVAILABLE:
        return None

    if not file_path.exists():
        return None

    try:
        # Open the image
        with Image.open(file_path) as img:
            # Convert to RGB if necessary (for PNG with transparency, etc.)
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGB')

            # Create thumbnail
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

            # Save to bytes buffer as PNG
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)

            # Convert to base64
            thumbnail_base64 = base64.b64encode(buffer.read()).decode('utf-8')
            return thumbnail_base64

    except Exception:
        # Return None for any error (corrupted image, unsupported format, etc.)
        return None


def generate_pdf_thumbnail(file_path: Path, max_size: Tuple[int, int] = (200, 200)) -> Optional[str]:
    """
    Generate a thumbnail for the first page of a PDF file.

    Args:
        file_path: Path to the PDF file
        max_size: Maximum size for the thumbnail (width, height)

    Returns:
        Base64 encoded PNG thumbnail string, or None if error or not a PDF
    """
    if not PDF2IMAGE_AVAILABLE or not PIL_AVAILABLE:
        return None

    if not file_path.exists() or file_path.suffix.lower() != '.pdf':
        return None

    try:
        # Convert first page of PDF to image
        images = convert_from_path(file_path, first_page=1, last_page=1, dpi=150)

        if not images:
            return None

        # Get the first page
        first_page = images[0]

        # Create thumbnail
        first_page.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Save to bytes buffer as PNG
        buffer = io.BytesIO()
        first_page.save(buffer, format='PNG')
        buffer.seek(0)

        # Convert to base64
        thumbnail_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        return thumbnail_base64

    except Exception:
        # Return None for any error
        return None


def read_file_as_base64(file_path: Path) -> str:
    """
    Read a file and convert it to a base64 data URL.

    Args:
        file_path: Path to the file

    Returns:
        Data URL string with proper MIME type
    """
    # Read file as binary
    with open(file_path, 'rb') as f:
        file_data = f.read()

    # Detect MIME type
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if mime_type is None:
        # Default to application/octet-stream for unknown types
        mime_type = 'application/octet-stream'

    # Convert to base64
    base64_data = base64.b64encode(file_data).decode('utf-8')

    # Create data URL
    data_url = f"data:{mime_type};base64,{base64_data}"

    return data_url


def create_artifact_from_file(file_path: str, metadata: Dict[str, Any]) -> Optional[MuxiArtifact]:
    """
    Create a MuxiArtifact from a file.

    Args:
        file_path: Path to the file (as string)
        metadata: Additional metadata for the artifact

    Returns:
        MuxiArtifact object or None if error
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        path = Path(file_path)
        logger.info(f"Creating artifact from file: {file_path}")

        if not path.exists():
            logger.warning(f"File does not exist: {file_path}")
            return None

        # Get file extension
        extension = path.suffix.lower()

        # Determine artifact type based on extension
        if extension in TEXT_EXTENSIONS:
            artifact_type = "text"
        elif extension in IMAGE_EXTENSIONS:
            artifact_type = "image"
        elif extension in DOCUMENT_EXTENSIONS:
            artifact_type = "document"
        else:
            artifact_type = "data"

        # Prepare artifact content
        content = None
        data_url = None

        if artifact_type == "text":
            # For text files, read content directly
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                # If text read fails, treat as binary
                artifact_type = "data"
                data_url = read_file_as_base64(path)
        else:
            # For binary files, use base64 encoding
            data_url = read_file_as_base64(path)

        # Generate preview if applicable
        preview = None
        preview_data = None

        if artifact_type == "image":
            preview_data = generate_image_thumbnail(path)
            if preview_data:
                preview = ArtifactPreview(
                    thumbnail=preview_data
                )
        elif extension == '.pdf':
            preview_data = generate_pdf_thumbnail(path)
            if preview_data:
                preview = ArtifactPreview(
                    thumbnail=preview_data
                )

        # Get file stats
        file_stats = path.stat()

        # Create artifact metadata
        # Remove mime_type from metadata if it exists to avoid duplicate
        metadata_copy = metadata.copy()
        mime_type = metadata_copy.pop('mime_type', None)
        if not mime_type:
            mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            
        # Also remove file_size if it exists in metadata
        metadata_copy.pop('file_size', None)
        metadata_copy.pop('size_bytes', None)  # Remove if passed as size_bytes
        
        artifact_metadata = ArtifactMetadata(
            created_at=datetime.now(),
            updated_at=datetime.now(),
            file_path=str(path.absolute()),
            size_bytes=file_stats.st_size,
            mime_type=mime_type,
            **metadata_copy  # Include any additional metadata provided
        )

        # Create and return artifact
        artifact = MuxiArtifact(
            type=artifact_type,
            format=extension[1:] if extension else "bin",  # Remove the dot from extension
            filename=path.name,
            content=content,
            data_url=data_url,
            metadata=artifact_metadata,
            preview=preview
        )

        logger.info(f"Successfully created artifact: {artifact.filename}")
        return artifact

    except Exception as e:
        # Return None for any error
        logger.error(f"Error creating artifact from {file_path}: {str(e)}")
        import traceback
        traceback.print_exc()
        return None
