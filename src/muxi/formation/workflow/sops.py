"""Standard Operating Procedures (SOP) System for MUXI Runtime.

This module provides automated workflow generation from documented procedures,
enabling consistent execution of complex multi-step operations.
"""

import asyncio
import hashlib
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...services import observability
from ...utils.user_dirs import get_cache_dir
# Lazy import DocumentChunkManager to avoid initialization issues
# from ..documents.storage.chunk_manager import DocumentChunkManager


class SOPSystem:
    """
    Standard Operating Procedures system for automated workflow generation.

    Provides:
    - Semantic search for SOP discovery using WorkingMemory/FAISS
    - Template-based workflow generation with agent routing
    - File reference resolution for documentation and templates
    - Intelligent caching with MD5 hash validation
    - Support for both template and guide execution modes

    Note: This implementation shares some patterns with KnowledgeHandler
    for consistency. Future versions may unify the document processing pipeline.
    """

    def __init__(self, formation_path: Optional[Path] = None):
        """
        Initialize the SOP system.

        Args:
            formation_path: Optional path to formation directory.
                          If not provided, auto-detects from environment.
        """
        # ===================================================================
        # PATH CONFIGURATION
        # ===================================================================
        # Get formation path - use provided or auto-detect
        self.formation_path = formation_path or self._get_formation_path()
        self.sop_dir = self.formation_path / "sops" if self.formation_path else None

        # ===================================================================
        # DATA STRUCTURES
        # ===================================================================
        self.sops = {}  # Only files with type: sop in frontmatter
        self.resource_map = {}  # All files for [file:path] reference resolution
        self.file_hashes = {}  # MD5 hashes for change detection
        self.embeddings_cache = {}  # Cached embeddings to avoid recomputation
        self.enabled = False  # Whether SOP system is active
        self._indexed = False  # Whether SOPs are indexed in WorkingMemory

        # ===================================================================
        # LAZY-LOADED SERVICES
        # ===================================================================
        # These will be initialized on first use
        self._document_processor = None
        self._faiss_service = None
        self._embedding_model = None

        # ===================================================================
        # CACHE CONFIGURATION
        # ===================================================================
        # Cache directory will be initialized lazily when needed
        self._cache_dir = None

        # ===================================================================
        # INITIALIZATION
        # ===================================================================
        if self.sop_dir and self.sop_dir.exists():
            try:
                self._scan_directory()
                if self.sops:
                    self.enabled = True
                    # Hydrate WorkingMemory from cache on startup
                    self._hydrate_from_cache()

                    # Init event - visible during startup (Linux init-style)
                    from ...datatypes.observability import InitEventFormatter
                    sop_names = ", ".join(list(self.sops.keys())[:3])
                    if len(self.sops) > 3:
                        sop_names += f" +{len(self.sops) - 3} more"
                    print(InitEventFormatter.format_ok(
                        f"SOPs: {len(self.sops)} procedure(s) loaded",
                        sop_names
                    ))
            except Exception as e:
                # Fail fast with clear error (Linux init-style)
                from ...datatypes.observability import InitEventFormatter
                print(InitEventFormatter.format_fail(
                    f"Failed to load SOPs from {self.sop_dir}",
                    str(e)
                ))
                raise RuntimeError(f"SOP initialization failed: {e}") from e

    @property
    def cache_dir(self) -> Path:
        """Get cache directory, creating it lazily when needed."""
        if self._cache_dir is None:
            self._cache_dir = Path(get_cache_dir("sops"))
        return self._cache_dir

    # ========================================================================
    # DIRECTORY SCANNING AND FILE PROCESSING
    # ========================================================================

    def _scan_directory(self):
        """
        Scan SOP directory and build resource map.

        Processes:
        - Markdown files with 'type: sop' in frontmatter become SOPs
        - All files are added to resource_map for [file:] references
        """
        # First, find all SOPs (markdown files with type: sop)
        for md_file in self.sop_dir.rglob("*.md"):
            # Check hash for change detection
            with open(md_file, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()

            sop_id = md_file.stem
            if self.file_hashes.get(sop_id) != file_hash:
                content = md_file.read_text()
                metadata = {}

                # Parse YAML front matter if present
                if content.startswith('---'):
                    try:
                        parts = content.split('---', 2)
                        if len(parts) >= 3:
                            metadata = yaml.safe_load(parts[1]) or {}
                            content = parts[2].strip()
                    except yaml.YAMLError as e:
                        # Log and skip files with invalid YAML front matter
                        try:
                            observability.observe(
                                event_type=observability.ErrorEvents.SERIALIZATION_ERROR,
                                level=observability.EventLevel.ERROR,
                                data={
                                    "error": str(e),
                                    "file": str(md_file),
                                    "error_type": "yaml_parsing",
                                },
                                description=f"Failed to parse YAML front matter in {md_file.name}"
                            )
                        except Exception:
                            pass
                        continue
                    except Exception as e:
                        # Log and skip files with other parsing errors
                        try:
                            observability.observe(
                                event_type=observability.ErrorEvents.SERIALIZATION_ERROR,
                                level=observability.EventLevel.ERROR,
                                data={
                                    "error": str(e),
                                    "file": str(md_file),
                                    "error_type": "general_parsing",
                                    "exception_type": type(e).__name__,
                                },
                                description=f"Unexpected error parsing {md_file.name}"
                            )
                        except Exception:
                            pass
                        continue

                # Only process if type: sop
                if metadata.get('type') == 'sop':
                    self.sops[sop_id] = {
                        'id': sop_id,
                        'path': md_file,
                        'name': metadata.get('name', sop_id),
                        'description': metadata.get('description', ''),
                        'mode': metadata.get('mode', 'template'),  # Default to template
                        'tags': self._parse_tags(metadata.get('tags', '')),
                        'bypass_approval': metadata.get('bypass_approval', True),  # Default to bypass
                        'content': content,  # Full markdown content for decomposer
                        'raw_content': md_file.read_text(),  # Original content with frontmatter
                        'steps': metadata.get('steps', [])  # Always include steps, default to empty list
                    }
                    self.file_hashes[sop_id] = file_hash

        # Build resource map for [file:] references (all files in sops/)
        # Even though decomposer handles execution, we still need to resolve paths
        for file_path in self.sop_dir.rglob("*"):
            if file_path.is_file():
                # Store with relative path from sops/ dir
                relative_path = file_path.relative_to(self.sop_dir)
                self.resource_map[str(relative_path)] = file_path
                # Also store just filename for convenience
                self.resource_map[file_path.name] = file_path

    def _parse_tags(self, tags: Any) -> List[str]:
        """
        Parse tags from various formats.

        Args:
            tags: Tags as list, comma-separated string, or None

        Returns:
            List of tag strings
        """
        if isinstance(tags, list):
            return tags
        elif isinstance(tags, str):
            return [t.strip() for t in tags.split(',')]
        return []

    # Step extraction removed - decomposer handles this now

    # ========================================================================
    # CACHE MANAGEMENT
    # ========================================================================

    def _hydrate_from_cache(self):
        """
        Hydrate WorkingMemory with cached embeddings on startup.

        - Loads embeddings from JSON cache (safer than pickle)
        - Validates against MD5 hashes
        - Cleans up stale entries for removed SOPs
        - Immediately indexes in WorkingMemory if available
        """
        # Skip cache hydration if formation ID is not set yet
        try:
            cache_dir = self.cache_dir
            cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            # Can't get cache dir yet (formation ID not set), skip hydration
            return
        embeddings_file = cache_dir / "embeddings.json"

        # Also check for old pickle file to migrate
        old_pickle_file = cache_dir / "embeddings.pkl"

        # Track which SOPs are still valid
        valid_sop_ids = set(self.sops.keys())
        cached_sop_ids = set()

        if embeddings_file.exists():
            import json
            import numpy as np
            try:
                with open(embeddings_file, 'r') as f:
                    cached_data = json.load(f)
                    cached_sop_ids = set(cached_data.keys())

                    # Load embeddings for existing SOPs with matching hashes
                    for sop_id, data in cached_data.items():
                        if sop_id in self.file_hashes:
                            if data['hash'] == self.file_hashes[sop_id]:
                                # Convert list back to numpy array if needed
                                if isinstance(data['embedding'], list):
                                    embedding = np.array(data['embedding'])
                                else:
                                    embedding = data['embedding']
                                self.embeddings_cache[sop_id] = embedding
                                # Try to hydrate WorkingMemory immediately
                                self._hydrate_working_memory(sop_id, embedding)
            except Exception as e:
                # Log cache loading error but continue
                observability.observe(
                    event_type=observability.ErrorEvents.WARNING,
                    level=observability.EventLevel.WARNING,
                    data={
                        "error": str(e),
                        "cache_file": str(embeddings_file),
                    },
                    description="Failed to load SOP embeddings cache - will regenerate"
                )
        elif old_pickle_file.exists():
            # Migrate from old pickle format to JSON
            import pickle
            try:
                with open(old_pickle_file, 'rb') as f:
                    cached_data = pickle.load(f)
                    # Save in new JSON format
                    self.embeddings_cache = cached_data
                    self._save_cached_embeddings()
                    # Remove old pickle file
                    old_pickle_file.unlink()
                    observability.observe(
                        event_type=observability.SystemEvents.SERVICE_STARTED,
                        level=observability.EventLevel.INFO,
                        data={
                            "old_format": "pickle",
                            "new_format": "json",
                            "sop_count": len(cached_data),
                        },
                        description="Migrated SOP embeddings cache from pickle to JSON format"
                    )
                    # Now process the migrated data
                    cached_sop_ids = set(cached_data.keys())
                    for sop_id, data in cached_data.items():
                        if sop_id in self.file_hashes:
                            if data['hash'] == self.file_hashes[sop_id]:
                                self.embeddings_cache[sop_id] = data['embedding']
                                self._hydrate_working_memory(sop_id, data['embedding'])
            except Exception as e:
                # Log migration error but continue
                observability.observe(
                    event_type=observability.ErrorEvents.WARNING,
                    level=observability.EventLevel.WARNING,
                    data={
                        "error": str(e),
                        "cache_file": str(old_pickle_file),
                    },
                    description="Failed to migrate old pickle cache - will regenerate"
                )

        # Clean up stale cache entries (SOPs that were removed)
        stale_sops = cached_sop_ids - valid_sop_ids
        if stale_sops and self.embeddings_cache:
            # Remove stale entries and save updated cache
            for sop_id in stale_sops:
                self.embeddings_cache.pop(sop_id, None)
            self._save_cached_embeddings()

    def _hydrate_working_memory(self, sop_id: str, embedding: Any):
        """Add cached embedding to WorkingMemory if available."""
        working_memory = self._get_working_memory()
        if working_memory:
            # Add to FAISS synchronously during startup
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule as a task
                    loop.create_task(self._add_to_faiss(sop_id, embedding))
                else:
                    # Run synchronously
                    loop.run_until_complete(self._add_to_faiss(sop_id, embedding))
            except Exception:
                # If we can't hydrate now, it will be done later
                pass

    async def _add_to_faiss(self, sop_id: str, embedding: Any):
        """Add a single SOP to FAISS."""
        working_memory = self._get_working_memory()
        if working_memory and sop_id in self.sops:
            sop = self.sops[sop_id]
            await working_memory.add(
                namespace="sops",
                id=sop_id,
                embedding=embedding,
                metadata={
                    'name': sop['name'],
                    'tags': sop['tags'],
                    'mode': sop.get('mode', 'template')
                }
            )

    def _save_cached_embeddings(self):
        """Save embeddings to cache for future use using JSON (safer than pickle)"""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        embeddings_file = self.cache_dir / "embeddings.json"

        import json
        import numpy as np

        cache_data = {}
        for sop_id, embedding in self.embeddings_cache.items():
            # Convert numpy arrays to lists for JSON serialization
            if isinstance(embedding, np.ndarray):
                embedding_list = embedding.tolist()
            elif hasattr(embedding, 'tolist'):
                embedding_list = embedding.tolist()
            else:
                embedding_list = list(embedding) if not isinstance(embedding, list) else embedding

            cache_data[sop_id] = {
                'hash': self.file_hashes.get(sop_id),
                'embedding': embedding_list,
                'version': '1.0'  # Add version for future compatibility
            }

        try:
            with open(embeddings_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
        except Exception as e:
            # Log save error but continue operation
            observability.observe(
                event_type=observability.ErrorEvents.WARNING,
                level=observability.EventLevel.WARNING,
                data={
                    "error": str(e),
                    "cache_file": str(embeddings_file),
                },
                description="Failed to save SOP embeddings cache"
            )

    # ========================================================================
    # SERVICE DISCOVERY AND INITIALIZATION
    # ========================================================================

    def _get_formation_path(self) -> Optional[Path]:
        """
        Auto-detect formation path from environment.

        Tries in order:
        1. MUXI_FORMATION_DIR environment variable
        2. Current directory with formation config (formation.afs/yaml/yml)

        Returns:
            Path to formation directory or None
        """
        import os

        # Try environment variable first
        formation_dir = os.environ.get('MUXI_FORMATION_DIR')
        if formation_dir:
            return Path(formation_dir)

        # Try current directory for formation config (priority: .afs > .yaml > .yml)
        current_dir = Path.cwd()
        if (current_dir / "formation.afs").exists():
            return current_dir
        if (current_dir / "formation.yaml").exists():
            return current_dir
        if (current_dir / "formation.yml").exists():
            return current_dir

        # No formation path found
        return None

    def _get_working_memory(self):
        """Lazily get WorkingMemory/BufferMemory with FAISS service."""
        if self._faiss_service is None:
            try:
                # Try WorkingMemory first
                from ...memory import WorkingMemory
                working_memory = WorkingMemory.get_instance()
                if working_memory and hasattr(working_memory, 'faiss_service'):
                    self._faiss_service = working_memory.faiss_service
                    return self._faiss_service

                # Try BufferMemory as fallback
                from ...formation import Formation  # noqa: E402
                formation = Formation.get_instance()
                if formation and hasattr(formation, '_configured_services'):
                    buffer_memory = formation._configured_services.get('buffer_memory')
                    if buffer_memory and hasattr(buffer_memory, 'faiss_service'):
                        self._faiss_service = buffer_memory.faiss_service
            except Exception:
                pass
        return self._faiss_service

    def _get_embedding_model(self):
        """Lazily get embedding model from working memory."""
        if self._embedding_model is None:
            try:
                from ...memory import WorkingMemory
                working_memory = WorkingMemory.get_instance()
                if working_memory and hasattr(working_memory, 'embedding_model'):
                    # Wrap the model in our adapter for consistent interface
                    self._embedding_model = self._create_embedding_adapter(working_memory.embedding_model)
            except Exception:
                pass
        return self._embedding_model

    def _create_embedding_adapter(self, model):
        """
        Create an adapter that provides a consistent embedding interface.

        This adapter normalizes different embedding model implementations to provide
        both sync and async methods with consistent behavior.

        Args:
            model: The underlying embedding model

        Returns:
            An adapter object with consistent embed() and generate_embeddings() methods
        """
        class EmbeddingAdapter:
            """Adapter to provide consistent embedding interface."""

            def __init__(self, wrapped_model):
                self.model = wrapped_model

            def embed(self, text: str):
                """
                Synchronous single text embedding.

                This method handles both sync and async embedding models transparently.
                When called from within a running event loop with an async-only model,
                it will execute the async operation in a thread pool executor to avoid
                blocking the event loop.

                Args:
                    text: Text to generate embedding for

                Returns:
                    Embedding vector

                Note: For better performance in async contexts, prefer using
                      embed_async() or generate_embeddings() directly.
                """
                # Check if model has sync embed method
                if hasattr(self.model, 'embed') and not asyncio.iscoroutinefunction(self.model.embed):
                    return self.model.embed(text)
                else:
                    # If only async is available, handle it properly
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # We're in a running loop - callers should use embed_async directly
                            raise RuntimeError(
                                "Cannot call synchronous embed() from within an async context. "
                                "Please use await embed_async() instead, or call this from a different thread."
                            )
                        else:
                            # No running loop, we can run it directly
                            return asyncio.run(self.embed_async(text))
                    except RuntimeError as e:
                        # Check if it's our specific error about async context
                        if "Cannot call synchronous embed()" in str(e):
                            raise
                        # No event loop exists, create one and run (for older Python contexts)
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            return loop.run_until_complete(self.embed_async(text))
                        finally:
                            loop.close()
                            asyncio.set_event_loop(None)

            async def embed_async(self, text: str):
                """Asynchronous single text embedding with fallback to batch method."""
                # Try direct embed method first
                if hasattr(self.model, 'embed'):
                    if asyncio.iscoroutinefunction(self.model.embed):
                        return await self.model.embed(text)
                    else:
                        return self.model.embed(text)

                # Fall back to generate_embeddings for single text
                elif hasattr(self.model, 'generate_embeddings'):
                    embeddings = await self.generate_embeddings([text])
                    return embeddings[0] if embeddings else None

                return None

            async def generate_embeddings(self, texts: List[str]) -> List[Any]:
                """Asynchronous batch embedding with proper sync/async handling."""
                # Prefer batch method if available
                if hasattr(self.model, 'generate_embeddings'):
                    # Check if it's async or sync
                    if asyncio.iscoroutinefunction(self.model.generate_embeddings):
                        return await self.model.generate_embeddings(texts)
                    else:
                        # Sync method - call directly
                        return self.model.generate_embeddings(texts)

                # Fall back to individual embeddings using embed_async
                # (which already handles sync/async properly)
                embeddings = []
                for text in texts:
                    embedding = await self.embed_async(text)
                    if embedding is not None:
                        embeddings.append(embedding)
                return embeddings if embeddings else []

        return EmbeddingAdapter(model)

    def _get_document_processor(self):
        """Lazily get document processor and chunk manager."""
        if self._document_processor is None:
            try:
                # Use both MarkItDown for extraction and DocumentChunkManager for chunking
                from markitdown import MarkItDown
                self._document_processor = {
                    'markitdown': MarkItDown(),
                    'chunk_manager': self._get_chunk_manager()
                }
            except Exception:
                pass
        return self._document_processor

    def _get_chunk_manager(self):
        """Get DocumentChunkManager from formation or create one using formation's config."""
        try:
            # Lazy import DocumentChunkManager to avoid initialization issues
            from ..documents.storage.chunk_manager import DocumentChunkManager

            # Try to get from formation's configured services
            from ...formation import Formation  # noqa: E402
            formation = Formation.get_instance()

            # First try to get existing chunk manager
            if formation and hasattr(formation, '_configured_services'):
                chunk_manager = formation._configured_services.get('document_chunk_manager')
                if chunk_manager:
                    return chunk_manager

            # If not available, try to get the document processing config from formation
            if formation:
                # Try to get document processing config from formation
                if hasattr(formation, '_document_processing_config'):
                    # Use the formation's document processing configuration
                    return DocumentChunkManager(document_config=formation._document_processing_config)

                # Try to get from _configured_services as well
                if hasattr(formation, '_configured_services'):
                    doc_config = formation._configured_services.get('document_processing_config')
                    if doc_config:
                        return DocumentChunkManager(document_config=doc_config)

            # Last resort: Create using the formation's LLM config if available
            if formation and hasattr(formation, '_llm_config'):
                from ...formation.config.document_processing import DocumentProcessingConfig
                # This will extract document settings from llm.models.documents
                config = DocumentProcessingConfig(formation._llm_config)
                return DocumentChunkManager(document_config=config)

            # Final fallback: Create with defaults (will use formation defaults internally)
            from ...formation.config.document_processing import DocumentProcessingConfig
            config = DocumentProcessingConfig({})
            return DocumentChunkManager(document_config=config)
        except Exception:
            return None

    # ========================================================================
    # INDEXING AND SEARCH
    # ========================================================================

    async def initialize_index(self):
        """
        Initialize WorkingMemory index with SOPs.

        Called during overlord's async startup to pre-index SOPs
        for fast semantic search.
        """
        if self._indexed:
            return

        working_memory = self._get_working_memory()
        embedding_model = self._get_embedding_model()

        if working_memory and embedding_model:
            # Index any SOPs that weren't cached
            await self._index_missing_sops()
            self._indexed = True

    async def _ensure_indexed(self):
        """Ensure SOPs are indexed in FAISS if available."""
        if self._indexed:
            return

        # If not indexed, try to index now (fallback for when startup indexing failed)
        await self.initialize_index()

    async def _index_missing_sops(self):
        """Index SOPs that aren't already in cache/FAISS."""
        working_memory = self._get_working_memory()
        embedding_model = self._get_embedding_model()

        if not working_memory or not embedding_model:
            return

        updated = False
        # Generate embeddings for SOPs not in cache
        for sop_id, sop in self.sops.items():
            if sop_id not in self.embeddings_cache:
                # Create searchable text from SOP
                searchable_text = f"{sop['name']} {sop['description']} "
                searchable_text += " ".join(str(tag) for tag in sop['tags'])
                # Include step text for better matching (check if steps exist)
                steps = sop.get('steps', [])
                for step in steps:
                    searchable_text += " " + step.get('text', '')

                # Generate embedding using adapter's async interface since we're in async context
                try:
                    # Use batch method for single text (it handles both single and batch)
                    embeddings = await embedding_model.generate_embeddings([searchable_text])
                    if not embeddings or len(embeddings) == 0:
                        # Skip if no embedding generated
                        continue
                    embedding = embeddings[0]
                except Exception as e:
                    # Log error and skip this SOP
                    observability.observe(
                        event_type=observability.ErrorEvents.EMBEDDINGS_GENERATION_FAILED,
                        level=observability.EventLevel.ERROR,
                        data={
                            "error": str(e),
                            "sop_id": sop_id,
                            "sop_name": sop.get('name', sop_id),
                        },
                        description=f"Failed to generate embedding for SOP: {sop_id}"
                    )
                    continue

                self.embeddings_cache[sop_id] = embedding

                # Store in FAISS
                await self._add_to_faiss(sop_id, embedding)
                updated = True

        # Save updated cache if we added new embeddings
        if updated:
            self._save_cached_embeddings()

    async def find_relevant_sops(self, task_description: str, top_k: int = 3) -> List[Dict]:
        """
        Find relevant SOPs using semantic search.

        Args:
            task_description: Natural language description of task
            top_k: Maximum number of SOPs to return

        Returns:
            List of SOPs with relevance scores, sorted by relevance
        """
        if not self.enabled:
            return []

        # Ensure SOPs are indexed
        await self._ensure_indexed()

        working_memory = self._get_working_memory()
        embedding_model = self._get_embedding_model()

        # Use WorkingMemory if available
        if working_memory and embedding_model:
            # Generate embedding for the task description using adapter's consistent interface
            embeddings = await embedding_model.generate_embeddings([task_description])
            query_embedding = embeddings[0] if embeddings else None

            # Search using WorkingMemory
            results = await working_memory.search(
                namespace="sops",
                query_embedding=query_embedding,
                top_k=top_k
            )

            # Return SOPs with relevance scores
            relevant_sops = []
            for result in results:
                sop_id = result['id']
                if sop_id in self.sops:
                    sop = self.sops[sop_id].copy()
                    sop['relevance_score'] = result['score']
                    relevant_sops.append(sop)

            return relevant_sops
        else:
            # Fallback to tag-based matching
            return self._find_by_tags(task_description, top_k)

    def _find_by_tags(self, task_description: str, top_k: int) -> List[Dict]:
        """Fallback tag-based matching when FAISS not available"""
        task_lower = task_description.lower()
        scored_sops = []

        for sop_id, sop in self.sops.items():
            score = 0
            # Check tags
            for tag in sop['tags']:
                if tag.lower() in task_lower:
                    score += 1
            # Check name
            if sop['name'].lower() in task_lower:
                score += 2

            if score > 0:
                sop_copy = sop.copy()
                sop_copy['relevance_score'] = score
                scored_sops.append(sop_copy)

        # Sort by score and return top k
        scored_sops.sort(key=lambda x: x['relevance_score'], reverse=True)
        return scored_sops[:top_k]

    # ========================================================================
    # RESOURCE RESOLUTION AND DOCUMENT PROCESSING
    # ========================================================================

    def resolve_resource(self, reference: str) -> Optional[Path]:
        """
        Resolve [file:] reference to actual file path.

        Args:
            reference: File reference from SOP (e.g., 'templates/report.md')

        Returns:
            Path to file or None if not found
        """
        # Reference comes clean from regex extraction
        return self.resource_map.get(reference)

    async def get_resource_content(
        self, reference: str,
        max_file_size_mb: int = 10
    ) -> Optional[str]:
        """
        Get complete content of referenced file with size limits.

        When an SOP references a file, it needs the complete content,
        not chunks. The SOP author specifically included this reference
        so we should provide the full document.

        Args:
            reference: File reference from SOP directive
            max_file_size_mb: Maximum file size in MB to process (default: 10MB)

        Returns:
            Complete file content or None if not found
        """
        file_path = self.resolve_resource(reference)
        if not file_path:
            return None

        # Check file size before processing
        try:
            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            if file_size_mb > max_file_size_mb:
                observability.observe(
                    event_type=observability.ErrorEvents.RESOURCE_EXHAUSTED,
                    level=observability.EventLevel.ERROR,
                    data={
                        "file": str(file_path),
                        "file_size_mb": round(file_size_mb, 2),
                        "max_size_mb": max_file_size_mb,
                    },
                    description=(
                        f"File {file_path.name} exceeds size limit "
                        f"({file_size_mb:.2f}MB > {max_file_size_mb}MB)"
                    ),
                )
                return f"[File too large: {file_path.name} ({file_size_mb:.2f}MB)]"
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.WARNING,
                level=observability.EventLevel.WARNING,
                data={
                    "file": str(file_path),
                    "error": str(e),
                },
                description=f"Failed to check file size for {file_path.name}"
            )
            # Continue processing if we can't check size

        # For text files, just read the complete content
        if file_path.suffix.lower() in ['.md', '.txt', '.yaml', '.yml', '.json', '.csv', '.tsv']:
            try:
                return file_path.read_text()
            except Exception as e:
                observability.observe(
                    event_type=observability.ErrorEvents.WARNING,
                    level=observability.EventLevel.WARNING,
                    data={
                        "file": str(file_path),
                        "error": str(e),
                    },
                    description=f"Failed to read text file {file_path.name}"
                )
                return f"[Unable to read: {file_path.name}]"

        # Handle image files separately - just return a reference
        if file_path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp']:
            # For images, return a descriptive reference
            # In the future, we could use vision models to describe the image
            return f"[Image file: {file_path.name}]"

        # Use MarkItDown for document files (PDFs, Word docs, spreadsheets, presentations)
        document_processor = self._get_document_processor()
        if (document_processor and
                file_path.suffix.lower() in ['.pdf', '.docx', '.doc', '.pptx', '.ppt', '.xlsx', '.xls']):
            try:
                markitdown = document_processor.get('markitdown')
                if markitdown:
                    # Extract complete content with MarkItDown
                    result = markitdown.convert(str(file_path))
                    content = (result.text_content
                               if hasattr(result, 'text_content')
                               else str(result))
                    return content
            except Exception as e:
                # Log extraction failure but continue
                observability.observe(
                    event_type=observability.ErrorEvents.WARNING,
                    level=observability.EventLevel.WARNING,
                    data={
                        "file": str(file_path),
                        "error": str(e),
                        "file_type": file_path.suffix,
                    },
                    description=f"Failed to extract content from {file_path.name}"
                )
                # Return reference placeholder
                return f"[Unable to extract: {file_path.name}]"

        # For unsupported file types, return a reference
        return f"[Unsupported file type: {file_path.name}]"
