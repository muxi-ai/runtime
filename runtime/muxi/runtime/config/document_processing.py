"""Document processing configuration for MUXI runtime."""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class DocumentProcessingConfig:
    """Document processing configuration manager."""

    def __init__(self, document_processing_config: Dict[str, Any]):
        """Initialize document processing configuration."""
        self.config = document_processing_config or {}
        self._apply_defaults()

    def _apply_defaults(self) -> None:
        """Apply default values for missing configuration."""
        # General configuration defaults
        if "enabled" not in self.config:
            self.config["enabled"] = True

        # Chunking configuration defaults
        if "chunking" not in self.config:
            self.config["chunking"] = {}

        chunking_defaults = {
            "default_size": 1000,
            "overlap": 100,
            "strategies": ["adaptive", "semantic", "fixed", "paragraph"]
        }

        for key, default_value in chunking_defaults.items():
            if key not in self.config["chunking"]:
                self.config["chunking"][key] = default_value

        # Files configuration defaults
        if "files" not in self.config:
            self.config["files"] = {}

        files_defaults = {
            "max_size_mb": 50,
            "cache_ttl_seconds": 3600
        }

        for key, default_value in files_defaults.items():
            if key not in self.config["files"]:
                self.config["files"][key] = default_value

        # Models configuration defaults
        if "models" not in self.config:
            self.config["models"] = {}

        models_defaults = {
            "nltk_data_path": "~/nltk_data",
            "spacy_model": "en_core_web_sm",
            "sentence_transformer": "all-MiniLM-L6-v2"
        }

        for key, default_value in models_defaults.items():
            if key not in self.config["models"]:
                self.config["models"][key] = default_value

    def is_enabled(self) -> bool:
        """Check if document processing is enabled."""
        return self.config.get("enabled", True)

    def get_chunk_size(self) -> int:
        """Get default chunk size for document processing."""
        return self.config["chunking"]["default_size"]

    def get_chunk_overlap(self) -> int:
        """Get chunk overlap for document processing."""
        return self.config["chunking"]["overlap"]

    def get_chunking_strategies(self) -> List[str]:
        """Get available chunking strategies."""
        return self.config["chunking"]["strategies"]

    def get_max_file_size_mb(self) -> int:
        """Get maximum file size in MB."""
        return self.config["files"]["max_size_mb"]

    def get_cache_ttl_seconds(self) -> int:
        """Get cache TTL in seconds."""
        return self.config["files"]["cache_ttl_seconds"]

    def get_nltk_data_path(self) -> str:
        """Get NLTK data path."""
        return self.config["models"]["nltk_data_path"]

    def get_spacy_model(self) -> str:
        """Get spaCy model name."""
        return self.config["models"]["spacy_model"]

    def get_sentence_transformer_model(self) -> str:
        """Get sentence transformer model name."""
        return self.config["models"]["sentence_transformer"]

    def get_max_file_size_bytes(self) -> int:
        """Get maximum file size in bytes."""
        return self.get_max_file_size_mb() * 1024 * 1024
