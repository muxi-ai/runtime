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
#   # Retrieve knowledge
#   results = await handler.retrieve(
#       query="How do I configure the API?",
#       limit_per_source=3
#   )
#
# More sophisticated implementations would include vector databases,
# API connectors, or other specialized knowledge sources.
# =============================================================================

import glob
import os
from typing import Any, Dict, List, Optional

# Import markitdown for document conversion
try:
    from markitdown import MarkItDown
    MARKITDOWN_AVAILABLE = True
except ImportError:
    MARKITDOWN_AVAILABLE = False


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

    async def retrieve(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieve relevant information based on a query.

        This is an abstract method that must be implemented by subclasses.
        Each implementation can use different strategies for finding and
        ranking relevant information.

        Args:
            query: The search query string. This should be a question or set
                of keywords that the source will use to find relevant information.
            limit: Maximum number of results to return. Sources should respect
                this limit to prevent overwhelming the caller with too much information.

        Returns:
            List of dictionaries containing relevant information. Each dictionary
            should have at least a "content" field with the relevant text, and
            optionally a "metadata" field with additional context.

        Raises:
            NotImplementedError: If not implemented by a subclass.
        """
        raise NotImplementedError("Subclasses must implement retrieve()")


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
        ".docx", ".pptx", ".xlsx", ".xls",
        # PDFs
        ".pdf",
        # Images (with OCR support)
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif",
        # Audio (with transcription support)
        ".wav", ".mp3",
        # Web content
        ".html", ".htm",
        # Data formats
        ".csv", ".json", ".xml",
        # Archives
        ".zip",
        # E-books
        ".epub"
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
        self.enable_markitdown = enable_markitdown and MARKITDOWN_AVAILABLE

        # Set default allowed extensions to include all supported formats
        if allowed_extensions is None:
            self.allowed_extensions = (
                self._TEXT_EXTENSIONS + self._MARKITDOWN_EXTENSIONS
            )
        else:
            self.allowed_extensions = allowed_extensions

        self._files: Optional[List[str]] = None

        # Initialize markitdown converter if available
        self._markitdown = None
        if self.enable_markitdown:
            try:
                self._markitdown = MarkItDown()
            except Exception as e:
                print(f"Warning: Failed to initialize MarkItDown: {e}")
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
            print(f"Error processing file {file_path}: {e}")
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
            print(f"Scanning directory: {self.path} (recursive: {self.recursive})")

            if self.recursive:
                # Recursive scan
                for ext in self.allowed_extensions:
                    pattern = os.path.join(self.path, "**", f"*{ext}")
                    ext_files = glob.glob(pattern, recursive=True)
                    files.extend(ext_files)
                    if ext_files:  # Only print if files found
                        print(f"  Found {len(ext_files)} {ext} files")
            else:
                # Only immediate directory
                for ext in self.allowed_extensions:
                    pattern = os.path.join(self.path, f"*{ext}")
                    ext_files = glob.glob(pattern)
                    files.extend(ext_files)
                    if ext_files:  # Only print if files found
                        print(f"  Found {len(ext_files)} {ext} files")
        else:
            print(f"Warning: Path {self.path} does not exist")

        # Remove duplicates, sort, and limit
        unique_files = sorted(list(set(files)))

        if len(unique_files) > self.max_files:
            print(f"Limiting to first {self.max_files} files "
                  f"(found {len(unique_files)} total)")
            unique_files = unique_files[:self.max_files]

        # Cache the discovered files
        self._files = unique_files
        print(f"Total files to process: {len(self._files)}")
        return self._files

    async def retrieve(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieve relevant information from files based on a query.

        This implementation processes files using markitdown for supported formats
        and direct reading for text files. The content is converted to markdown
        format for consistent processing downstream.

        Args:
            query: The search query. In this simple implementation, the query is not
                actually used for filtering, but is required by the interface.
            limit: Maximum number of files to return. If there are more files than
                this limit, only the first 'limit' files are processed.

        Returns:
            List of retrieved knowledge items. Each item includes:
            - source: The file path
            - content: The processed file contents (converted to markdown if applicable)
            - metadata: Additional information including file type, path, size, and
                processing method
        """
        results = []
        files = self._discover_files()

        for i, file_path in enumerate(files[:limit]):
            try:
                # Check file size before reading
                file_size = os.path.getsize(file_path)
                if file_size > self.max_file_size:
                    print(f"Skipping large file: {file_path} "
                          f"({file_size} bytes > {self.max_file_size})")
                    continue

                print(f"Processing file {i+1}/{min(len(files), limit)}: {file_path}")

                # Load file content using appropriate method
                content = self._load_file_content(file_path)

                # Determine processing method for metadata
                processing_method = "text"
                if self._is_markitdown_supported(file_path):
                    processing_method = "markitdown"
                elif self._is_text_file(file_path):
                    processing_method = "text"
                else:
                    processing_method = "fallback"

                # Create a result item with file information
                results.append(
                    {
                        "source": file_path,
                        "content": content,
                        "metadata": {
                            "type": "file",
                            "path": file_path,
                            "size": len(content),
                            "base_path": self.path,
                            "extension": os.path.splitext(file_path)[1],
                            "processing_method": processing_method,
                            "markitdown_supported": self._is_markitdown_supported(
                                file_path
                            ),
                        },
                    }
                )
            except Exception as e:
                # Log errors but continue processing other files
                print(f"Error reading file {file_path}: {str(e)}")

        return results

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> 'FileKnowledge':
        """
        Create FileKnowledge instance from configuration dictionary.

        Args:
            config: Configuration dict with path, description, and optional settings

        Returns:
            FileKnowledge instance
        """
        return cls(
            path=config['path'],
            description=config.get('description'),
            recursive=config.get('recursive', True),
            allowed_extensions=config.get('allowed_extensions'),
            name=config.get('name'),
            max_files=config.get('max_files', 50),
            max_file_size=config.get('max_file_size', 1024 * 1024),
            enable_markitdown=config.get('enable_markitdown', True),
        )


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

    async def retrieve(
        self, query: str, limit_per_source: int = 3, max_sources: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve information from all knowledge sources.

        This method queries all registered knowledge sources and aggregates
        their results into a single list. It handles errors in individual
        sources gracefully, ensuring that a failure in one source doesn't
        prevent results from other sources.

        Args:
            query: The search query to send to all knowledge sources. This should
                be a question or keyword phrase that will be used to find relevant
                information across all sources.
            limit_per_source: Maximum number of results to retrieve from each source.
                Controls the total volume of information by limiting each source's
                contribution.
            max_sources: Maximum number of sources to query. If None, all registered
                sources are queried. If specified, only the first 'max_sources'
                sources are used.

        Returns:
            List of retrieved knowledge items from all sources, each enriched with
            metadata identifying its source. The format matches the KnowledgeSource
            retrieve() method, with additional source identification metadata.
        """
        results = []

        # Limit the number of sources if specified
        sources = self.sources
        if max_sources is not None:
            sources = sources[:max_sources]

        # Query each source
        for source in sources:
            try:
                # Retrieve results from this source
                source_results = await source.retrieve(query, limit=limit_per_source)

                # Add source information to each result for attribution
                for result in source_results:
                    if "metadata" not in result:
                        result["metadata"] = {}

                    # Tag each result with its source information
                    result["metadata"]["source_name"] = source.name
                    result["metadata"]["source_description"] = source.description

                # Add this source's results to the combined results
                results.extend(source_results)
            except Exception as e:
                # Log errors but continue processing other sources
                print(f"Error retrieving from source {source.name}: {str(e)}")

        return results
