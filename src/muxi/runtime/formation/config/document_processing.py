"""Document processing configuration for MUXI runtime."""

from typing import Any, Dict, List, Tuple

from ...services import observability


class DocumentProcessingConfig:
    """Document processing configuration manager for unified LLM model schema."""

    def __init__(self, llm_config: Dict[str, Any]):
        """Initialize document processing configuration from LLM models.

        Args:
            llm_config: Full LLM configuration dictionary containing models
        """
        self.config, self._documents_model_found = self._extract_document_config(llm_config)
        self._apply_defaults()

    def _extract_document_config(self, llm_config: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """Extract document processing config from LLM models configuration.

        Returns:
            Tuple of (config_dict, documents_model_found)
        """
        models = llm_config.get("models", [])

        # Find the documents model configuration
        for model in models:
            if "documents" in model:
                settings = model.get("settings", {})
                observability.observe(
                    event_type=observability.SystemEvents.CONFIG_FORMATION_LOADED,
                    level=observability.EventLevel.INFO,
                    data={"document_model": "documents", "source": "formation_config"},
                    description="Using document model from formation config",
                )
                return settings, True

        observability.observe(
            event_type=observability.SystemEvents.CONFIG_FORMATION_LOADED,
            level=observability.EventLevel.INFO,
            data={"document_model": "default", "source": "defaults"},
            description="Using default document model configuration",
        )
        return {}, False

    def _apply_defaults(self) -> None:
        """Apply default values for missing configuration."""
        # Extraction configuration defaults
        if "extraction" not in self.config:
            self.config["extraction"] = {}

        extraction = self.config["extraction"]

        # Core extraction settings
        extraction.setdefault("chunk_size", 1000)
        extraction.setdefault("overlap", 100)
        extraction.setdefault("strategy", "adaptive")

        # NLP configuration defaults
        if "nlp" not in extraction:
            extraction["nlp"] = {}

        nlp = extraction["nlp"]
        nlp.setdefault("data_path", "~/nlp_data")
        # These are intentionally commented in the schema - only set if explicitly provided
        # nlp.setdefault("spacy_model", "en_core_web_sm")
        # nlp.setdefault("sentence_transformer", "all-MiniLM-L6-v2")

        # File processing defaults
        self.config.setdefault("max_size_mb", 20)
        self.config.setdefault("cache_ttl_seconds", 3600)

    def is_enabled(self) -> bool:
        """Check if document processing is enabled."""
        # Document processing is enabled if documents model is configured
        return self._documents_model_found

    def get_chunk_size(self) -> int:
        """Get default chunk size for document processing."""
        return self.config["extraction"]["chunk_size"]

    def get_chunk_overlap(self) -> int:
        """Get chunk overlap for document processing."""
        return self.config["extraction"]["overlap"]

    def get_extraction_strategy(self) -> str:
        """Get the extraction strategy."""
        return self.config["extraction"]["strategy"]

    def get_chunking_strategies(self) -> List[str]:
        """Get available chunking strategies."""
        # Return common strategies since this is typically used for validation
        return ["adaptive", "semantic", "fixed", "paragraph"]

    def get_max_file_size_mb(self) -> int:
        """Get maximum file size in MB."""
        return self.config["max_size_mb"]

    def get_cache_ttl_seconds(self) -> int:
        """Get cache TTL in seconds."""
        return self.config["cache_ttl_seconds"]

    def get_nlp_data_path(self) -> str:
        """Get NLP data path."""
        return self.config["extraction"]["nlp"]["data_path"]

    def get_spacy_model(self) -> str:
        """Get spaCy model name if explicitly configured."""
        return self.config["extraction"]["nlp"].get("spacy_model", "en_core_web_sm")

    def get_sentence_transformer_model(self) -> str:
        """Get sentence transformer model name if explicitly configured."""
        return self.config["extraction"]["nlp"].get("sentence_transformer", "all-MiniLM-L6-v2")

    def get_max_file_size_bytes(self) -> int:
        """
        Return the maximum allowed file size for document processing in bytes.
        """
        return self.get_max_file_size_mb() * 1024 * 1024

    def get_settings(self) -> Dict[str, Any]:
        """
        Return a dictionary summarizing the current document processing configuration.

        Returns:
            A dictionary containing:
                - enabled (bool): Whether document processing is enabled.
                - extraction (dict): Extraction-related configuration settings.
                - max_size_mb (int): Maximum allowed file size in megabytes.
                - cache_ttl_seconds (int): Cache time-to-live in seconds.
        """
        return {
            "enabled": self.is_enabled(),
            "extraction": self.config.get("extraction", {}),
            "max_size_mb": self.get_max_file_size_mb(),
            "cache_ttl_seconds": self.get_cache_ttl_seconds(),
        }
