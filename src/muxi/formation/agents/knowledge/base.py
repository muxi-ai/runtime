# =============================================================================
# FRONTMATTER
# =============================================================================
# Title:        Knowledge Base - External Knowledge Integration
# Description:  Base classes for agent knowledge source integration
# Role:         Provides knowledge retrieval capabilities to agents
# Usage:        Used to augment agent responses with external information
# Author:       Muxi Framework Team
#
# The knowledge base module provides the foundation for integrating external
# knowledge sources with agents in the Muxi framework. It includes:
#
# 1. Abstract Knowledge Source Interface
#    - Defines the contract for all knowledge source implementations
#    - Standardizes information retrieval methods
#    - Supports metadata for source tracking and attribution
#
# 2. File-Based Knowledge Implementation
#    - Simple implementation using local files as knowledge sources
#    - Demonstrates the pattern for creating knowledge source implementations
#    - Serves as a reference for more sophisticated implementations
#
# 3. Knowledge Handler
#    - Manages multiple knowledge sources
#    - Aggregates and merges results from different sources
#    - Provides unified access to all knowledge sources
#
# Knowledge sources are typically integrated with agents through the Overlord,
# which manages access and coordinates knowledge retrieval.
#
# Example usage:
#
#   # Create knowledge sources
#   product_docs = FileKnowledge(
#       name="product_docs",
#       files=["docs/api.md", "docs/usage.md"],
#       description="Product documentation files"
#   )
#
#   # Create a knowledge handler
#   handler = KnowledgeHandler([product_docs])
#
#   # Add additional sources
#   handler.add_source(VectorKnowledge("embeddings_db", "db.sqlite"))
#
#   # Process knowledge sources with hybrid architecture
#   await handler.add_knowledge_source(product_docs)
#
# More sophisticated implementations would include vector databases,
# API connectors, or other specialized knowledge sources.
# =============================================================================

import glob
import os
from typing import Any, Dict, List, Optional

# Import markitdown for document conversion
from markitdown import MarkItDown

# Import DocumentChunkManager for hybrid architecture integration
from ...documents.storage.chunk_manager import DocumentChunkManager, DocumentChunk

# Import observability
from ....services import observability


class KnowledgeSource:
    """
    Base class for knowledge sources.

    Knowledge sources provide a way to retrieve relevant information based on a query.
    This could be from files, databases, APIs, or any other source of information.
    Each source can have its own search strategy and data format.

    This class defines the interface that all knowledge sources must implement,
    ensuring consistent behavior across different source types and enabling
    the KnowledgeHandler to work with any source implementation.
    """

    def __init__(self, name: str, description: Optional[str] = None):
        """
        Initialize a knowledge source.

        Args:
            name: A unique name for this knowledge source. Used for identification
                and reference in logs and debugging.
            description: Optional description of this knowledge source. Provides
                human-readable context about the source. If not provided, a default
                description is generated from the name.
        """
        self.name = name
        self.description = description or f"Knowledge source: {name}"


class FileKnowledge(KnowledgeSource):
    """
    Knowledge source that retrieves information from files and directories.

    This implementation can handle both individual files and directories,
    with support for recursive scanning and file extension filtering.
    It supports the new configuration schema with path, description, and options.

    Enhanced with markitdown support for comprehensive file format handling:
    - Office documents: .docx, .pptx, .xlsx, .xls
    - PDFs: .pdf
    - Images: .jpg, .jpeg, .png, .gif, .bmp, .tiff
    - Audio: .wav, .mp3
    - Web content: .html, .htm
    - Data formats: .csv, .json, .xml
    - Archives: .zip
    - E-books: .epub
    - Plain text: .txt, .md
    """

    # Extended list of supported file extensions via markitdown
    _MARKITDOWN_EXTENSIONS = [
        # Office documents
        ".docx",
        ".pptx",
        ".xlsx",
        ".xls",
        # PDFs
        ".pdf",
        # Images (with OCR support)
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".tiff",
        ".tif",
        # Audio (with transcription support)
        ".wav",
        ".mp3",
        # Web content
        ".html",
        ".htm",
        # Data formats
        ".csv",
        ".json",
        ".xml",
        # Archives
        ".zip",
        # E-books
        ".epub",
    ]

    # Traditional text extensions (processed directly)
    _TEXT_EXTENSIONS = [".txt", ".md"]

    def __init__(
        self,
        path: str,
        description: Optional[str] = None,
        recursive: bool = True,
        allowed_extensions: Optional[List[str]] = None,
        name: Optional[str] = None,
        max_files: int = 50,  # Limit files processed for performance
        max_file_size: int = 1024 * 1024,  # 1MB limit per file
        enable_markitdown: bool = True,  # Enable markitdown processing
    ):
        """
        Initialize a file-based knowledge source.

        Args:
            path: File path or directory path to use as knowledge source
            description: Optional description of this knowledge source
            recursive: If path is a directory, whether to scan recursively (default: True)
            allowed_extensions: List of allowed file extensions
                (default: includes all supported formats)
            name: Optional name for the source (defaults to path basename)
            max_files: Maximum number of files to process (default: 50)
            max_file_size: Maximum file size in bytes (default: 1MB)
            enable_markitdown: Whether to use markitdown for supported file types
                (default: True)
        """
        # Generate name from path if not provided
        if name is None:
            name = os.path.basename(path) or path

        super().__init__(name, description)
        self.path = path
        self.recursive = recursive
        self.max_files = max_files
        self.max_file_size = max_file_size
        self.enable_markitdown = enable_markitdown

        # Set default allowed extensions to include all supported formats
        if allowed_extensions is None:
            self.allowed_extensions = self._TEXT_EXTENSIONS + self._MARKITDOWN_EXTENSIONS
        else:
            self.allowed_extensions = allowed_extensions

        self._files: Optional[List[str]] = None

        # Initialize markitdown converter if available
        self._markitdown = None
        if self.enable_markitdown:
            try:
                self._markitdown = MarkItDown()
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.MARKITDOWN_INITIALIZATION_FAILED,
                    level=observability.EventLevel.WARNING,
                    description="Failed to initialize MarkItDown",
                    data={"error": str(e)}
                )
                self.enable_markitdown = False

    def _is_markitdown_supported(self, file_path: str) -> bool:
        """Check if file extension is supported by markitdown."""
        if not self.enable_markitdown:
            return False
        ext = os.path.splitext(file_path)[1].lower()
        return ext in self._MARKITDOWN_EXTENSIONS

    def _is_text_file(self, file_path: str) -> bool:
        """Check if file is a plain text file."""
        ext = os.path.splitext(file_path)[1].lower()
        return ext in self._TEXT_EXTENSIONS

    def _load_file_content(self, file_path: str) -> str:
        """
        Load and process file content using appropriate method.

        Uses markitdown for supported formats, direct reading for text files.

        Args:
            file_path: Path to the file to load

        Returns:
            Processed file content as text/markdown
        """
        try:
            if self._is_markitdown_supported(file_path):
                # Use markitdown for supported file types
                result = self._markitdown.convert(file_path)
                return result.text_content

            elif self._is_text_file(file_path):
                # Direct reading for plain text files
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read()

            else:
                # Fallback: try to read as text with error handling
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        return f.read()
                except UnicodeDecodeError:
                    # If not UTF-8, try other common encodings
                    for encoding in ["latin-1", "cp1252", "iso-8859-1"]:
                        try:
                            with open(file_path, "r", encoding=encoding) as f:
                                return f.read()
                        except UnicodeDecodeError:
                            continue

                    # If all text reading fails, return empty content with note
                    return f"[Binary file: {os.path.basename(file_path)}]"

        except Exception as e:
            observability.observe(
                event_type=observability.ConversationEvents.DOCUMENT_PROCESSING_FAILED,
                level=observability.EventLevel.ERROR,
                description=f"Error processing file {os.path.basename(file_path)}",
                data={
                    "file_path": file_path,
                    "error": str(e)
                }
            )
            return f"[Error loading file: {os.path.basename(file_path)}]"

    def _discover_files(self) -> List[str]:
        """
        Discover all files based on the path and configuration.

        Returns:
            List of file paths that match the criteria
        """
        if self._files is not None:
            return self._files

        files = []

        if os.path.isfile(self.path):
            # Single file
            files = [self.path]
        elif os.path.isdir(self.path):
            # Directory - scan for files
            observability.observe(
                event_type=observability.SystemEvents.SERVICE_STARTED,
                level=observability.EventLevel.INFO,
                description="Scanning directory for knowledge files",
                data={
                    "directory": self.path,
                    "recursive": self.recursive,
                    "component": "knowledge"
                }
            )

            if self.recursive:
                # Recursive scan
                for ext in self.allowed_extensions:
                    pattern = os.path.join(self.path, "**", f"*{ext}")
                    ext_files = glob.glob(pattern, recursive=True)
                    files.extend(ext_files)
                    # Log file discovery is now done after all extensions are processed
            else:
                # Only immediate directory
                for ext in self.allowed_extensions:
                    pattern = os.path.join(self.path, f"*{ext}")
                    ext_files = glob.glob(pattern)
                    files.extend(ext_files)
                    # Log file discovery is now done after all extensions are processed
        else:
            observability.observe(
                event_type=observability.ErrorEvents.KNOWLEDGE_SOURCE_MISSING,
                level=observability.EventLevel.WARNING,
                description="Knowledge source path does not exist",
                data={
                    "path": self.path
                }
            )

        # Remove duplicates, sort, and limit
        unique_files = sorted(list(set(files)))

        if len(unique_files) > self.max_files:
            observability.observe(
                event_type=observability.ErrorEvents.RESOURCE_EXHAUSTED,
                level=observability.EventLevel.WARNING,
                description=f"Limiting knowledge files to {self.max_files} (found {len(unique_files)})",
                data={
                    "found": len(unique_files),
                    "limit": self.max_files
                }
            )
            unique_files = unique_files[: self.max_files]

        # Cache the discovered files
        self._files = unique_files

        # Emit event about discovered files
        observability.observe(
            event_type=observability.SystemEvents.SERVICE_STARTED,
            level=observability.EventLevel.INFO,
            description=f"Discovered {len(self._files)} knowledge files",
            data={
                "source_name": self.name,
                "path": self.path,
                "file_count": len(self._files),
                "files": self._files[:3] if len(self._files) > 3 else self._files,
                "component": "knowledge"
            }
        )
        return self._files

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "FileKnowledge":
        """
        Create FileKnowledge instance from configuration dictionary.

        Args:
            config: Configuration dict with path, description, and optional settings

        Returns:
            FileKnowledge instance
        """
        return cls(
            path=config["path"],
            description=config.get("description"),
            recursive=config.get("recursive", True),
            allowed_extensions=config.get("allowed_extensions"),
            name=config.get("name"),
            max_files=config.get("max_files", 50),
            max_file_size=config.get("max_file_size", 1024 * 1024),
            enable_markitdown=config.get("enable_markitdown", True),
        )

    async def process_with_chunk_manager(
        self, chunk_manager: DocumentChunkManager, file_limit: Optional[int] = None
    ) -> List[DocumentChunk]:
        """
        Process files using DocumentChunkManager for hybrid architecture integration.

        This method integrates FileKnowledge's advanced file processing capabilities
        (including markitdown support for multiple file formats) with the hybrid
        architecture's DocumentChunkManager for consistent chunking.

        Args:
            chunk_manager: DocumentChunkManager instance for chunking
            file_limit: Optional limit on number of files to process

        Returns:
            List of DocumentChunk objects from all processed files
        """
        all_chunks = []
        files = self._discover_files()

        # Apply file limit if specified
        if file_limit is not None:
            files = files[:file_limit]

        for file_path in files:
            try:
                # Check file size before processing
                file_size = os.path.getsize(file_path)
                if file_size > self.max_file_size:
                    observability.observe(
                        event_type=observability.ErrorEvents.RESOURCE_EXHAUSTED,
                        level=observability.EventLevel.WARNING,
                        description=f"Skipping large file ({file_size} bytes > {self.max_file_size})",
                        data={
                            "file_path": file_path,
                            "file_size": file_size,
                            "limit": self.max_file_size
                        }
                    )
                    continue

                # Use FileKnowledge's advanced file loading (with markitdown support)
                content = self._load_file_content(file_path)

                if not content or len(content.strip()) < 10:
                    continue

                # Use DocumentChunkManager for consistent chunking
                document_chunks = await chunk_manager.chunk_document(
                    content=content,
                    filename=os.path.basename(file_path),
                    strategy="adaptive",  # Use adaptive strategy for optimal chunking
                    document_id=file_path,
                )

                # Add FileKnowledge-specific metadata to chunks
                for chunk in document_chunks:
                    chunk.metadata.update(
                        {
                            "knowledge_source": self.name,
                            "knowledge_description": self.description,
                            "file_path": file_path,
                            "processing_method": self._get_processing_method(file_path),
                            "markitdown_supported": self._is_markitdown_supported(file_path),
                            "file_extension": os.path.splitext(file_path)[1],
                            "file_size": file_size,
                        }
                    )

                all_chunks.extend(document_chunks)
                observability.observe(
                    event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_LOADED,
                    level=observability.EventLevel.INFO,
                    description=f"Processed knowledge file into {len(document_chunks)} chunks",
                    data={
                        "file_path": file_path,
                        "chunk_count": len(document_chunks),
                        "processing_method": self._get_processing_method(file_path)
                    }
                )

            except Exception as e:
                observability.observe(
                    event_type=observability.SystemEvents.KNOWLEDGE_SOURCE_FAILED,
                    level=observability.EventLevel.ERROR,
                    description="Error processing knowledge file",
                    data={
                        "file_path": file_path,
                        "error": str(e)
                    }
                )
                continue

        return all_chunks

    def _get_processing_method(self, file_path: str) -> str:
        """Get the processing method used for a file."""
        if self._is_markitdown_supported(file_path):
            return "markitdown"
        elif self._is_text_file(file_path):
            return "text"
        else:
            return "fallback"

    def get_files(self) -> List[str]:
        """Get list of files from this knowledge source."""
        return self._discover_files()


class KnowledgeHandler:
    """
    Manager for multiple knowledge sources.

    This class aggregates results from multiple knowledge sources, providing
    a unified interface for retrieving information from all available sources.
    It handles error isolation, ensuring that failures in one source don't
    affect others, and manages source identification and attribution.
    """

    def __init__(self, sources: Optional[List[KnowledgeSource]] = None):
        """
        Initialize a knowledge handler.

        Args:
            sources: Optional list of knowledge sources to manage. If None,
                an empty list is created, and sources can be added later with
                add_source().
        """
        self.sources = sources or []

    def add_source(self, source: KnowledgeSource) -> None:
        """
        Add a knowledge source to this handler.

        This method allows dynamically adding new knowledge sources after
        the handler has been initialized.

        Args:
            source: The knowledge source to add. Must be an instance of
                KnowledgeSource or a subclass.
        """
        self.sources.append(source)
