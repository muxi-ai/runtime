"""Standard Operating Procedures (SOP) System for MUXI Runtime.

This module provides automated workflow generation from documented procedures,
enabling consistent execution of complex multi-step operations.
"""

import hashlib
import re
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...services import observability
from ...utils.user_dirs import get_cache_dir, FORMATION_ID
from ..documents.storage.chunk_manager import DocumentChunkManager


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
        # Cache directory includes formation_id for proper isolation
        self.cache_dir = Path(get_cache_dir("sops"))

        # ===================================================================
        # INITIALIZATION
        # ===================================================================
        if self.sop_dir and self.sop_dir.exists():
            self._scan_directory()
            if self.sops:
                self.enabled = True
                # Hydrate WorkingMemory from cache on startup
                self._hydrate_from_cache()

                # Emit observability event for monitoring
                observability.observe(
                    event_type=observability.ConversationEvents.SOP_LOADED,
                    level=observability.EventLevel.INFO,
                    data={
                        "formation_id": FORMATION_ID,
                        "sop_count": len(self.sops),
                        "sop_names": list(self.sops.keys()),
                        "cached_embeddings": len(self.embeddings_cache),
                    },
                    description=f"Loaded {len(self.sops)} SOPs from {self.sop_dir}"
                )

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
                    except yaml.YAMLError:
                        # Skip files with invalid YAML front matter
                        continue
                    except Exception:
                        # Skip files with other parsing errors
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
                        'steps': self._extract_steps_from_markdown(content),
                        'content': content
                    }
                    self.file_hashes[sop_id] = file_hash

        # Build resource map for [file:] references (all files in sops/)
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

    def _extract_steps_from_markdown(self, content: str) -> List[Dict]:
        """
        Extract numbered steps with directives from Markdown content.

        Parses:
        - Numbered lists (1., 2., etc.)
        - [agent:name] directives for agent routing
        - [mcp:tool] directives for MCP tool requirements
        - [file:path] references for documentation

        Returns:
            List of step dictionaries with parsed directives
        """
        steps = []
        lines = content.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i]
            # Match lines starting with 1., 2., etc.
            if line.strip() and line.lstrip()[0].isdigit() and '. ' in line:
                # Extract the main step text
                main_text = line.split('. ', 1)[1].strip()

                # Collect full step content including sub-items
                full_content = main_text
                j = i + 1
                while (j < len(lines) and lines[j].strip() and
                       not (lines[j].lstrip()[0].isdigit() and '. ' in lines[j])):
                    if lines[j].strip().startswith('-'):
                        full_content += '\n' + lines[j]
                    j += 1

                # Parse directives from full content
                step_data = {
                    'text': main_text,
                    'agent': None,
                    'mcp_tools': [],
                    'resources': []
                }

                # Extract agent directive [agent:name]
                agent_match = re.search(r'\[agent:([^\]]+)\]', full_content)
                if agent_match:
                    step_data['agent'] = agent_match.group(1)
                    # Clean agent directive from main text
                    main_text = main_text.replace(agent_match.group(0), '').strip()

                # Extract MCP directives [mcp:tool]
                mcp_matches = re.findall(r'\[mcp:([^\]]+)\]', full_content)
                step_data['mcp_tools'] = mcp_matches

                # Extract file references [file:path]
                file_matches = re.findall(r'\[file:([^\]]+)\]', full_content)
                step_data['resources'] = file_matches

                # Clean text (remove markdown bold and directives)
                step_data['text'] = main_text.replace('**', '')

                steps.append(step_data)
                i = j - 1
            i += 1
        return steps

    # ========================================================================
    # CACHE MANAGEMENT
    # ========================================================================

    def _hydrate_from_cache(self):
        """
        Hydrate WorkingMemory with cached embeddings on startup.

        - Loads embeddings from pickle cache
        - Validates against MD5 hashes
        - Cleans up stale entries for removed SOPs
        - Immediately indexes in WorkingMemory if available
        """
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        embeddings_file = self.cache_dir / "embeddings.pkl"

        # Track which SOPs are still valid
        valid_sop_ids = set(self.sops.keys())
        cached_sop_ids = set()

        if embeddings_file.exists():
            import pickle
            try:
                with open(embeddings_file, 'rb') as f:
                    cached_data = pickle.load(f)
                    cached_sop_ids = set(cached_data.keys())

                    # Load embeddings for existing SOPs with matching hashes
                    for sop_id, data in cached_data.items():
                        if sop_id in self.file_hashes:
                            if data['hash'] == self.file_hashes[sop_id]:
                                self.embeddings_cache[sop_id] = data['embedding']
                                # Try to hydrate WorkingMemory immediately
                                self._hydrate_working_memory(sop_id, data['embedding'])
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
        """Save embeddings to cache for future use"""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        embeddings_file = self.cache_dir / "embeddings.pkl"

        import pickle
        cache_data = {}
        for sop_id, embedding in self.embeddings_cache.items():
            cache_data[sop_id] = {
                'hash': self.file_hashes.get(sop_id),
                'embedding': embedding
            }

        with open(embeddings_file, 'wb') as f:
            pickle.dump(cache_data, f)

    # ========================================================================
    # SERVICE DISCOVERY AND INITIALIZATION
    # ========================================================================

    def _get_formation_path(self) -> Optional[Path]:
        """
        Auto-detect formation path from environment.

        Tries in order:
        1. MUXI_FORMATION_DIR environment variable
        2. Current directory with formation.yaml

        Returns:
            Path to formation directory or None
        """
        import os

        # Try environment variable first
        formation_dir = os.environ.get('MUXI_FORMATION_DIR')
        if formation_dir:
            return Path(formation_dir)

        # Try current directory for formation.yaml
        current_dir = Path.cwd()
        if (current_dir / "formation.yaml").exists():
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
                from ...formation import Formation
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
                    self._embedding_model = working_memory.embedding_model
            except Exception:
                pass
        return self._embedding_model

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
        """Get DocumentChunkManager from formation or create one."""
        try:
            # Try to get from formation's configured services
            from ...formation import Formation
            formation = Formation.get_instance()
            if formation and hasattr(formation, '_configured_services'):
                chunk_manager = formation._configured_services.get('document_chunk_manager')
                if chunk_manager:
                    return chunk_manager

            # Create our own if not available
            from ...datatypes.document import DocumentProcessingConfig
            config = DocumentProcessingConfig({
                'extraction': {
                    'chunk_size': 1000,
                    'overlap': 100,
                    'strategy': 'adaptive'
                }
            })
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
                searchable_text += " ".join(sop['tags'])
                # Include step text for better matching
                for step in sop['steps']:
                    searchable_text += " " + step.get('text', '')

                # Generate embedding (assumes sync embedding model)
                embedding = embedding_model.embed(searchable_text)
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
            # Generate embedding for the task description
            if hasattr(embedding_model, 'generate_embeddings'):
                embeddings = await embedding_model.generate_embeddings([task_description])
                query_embedding = embeddings[0] if embeddings else None
            else:
                query_embedding = embedding_model.embed(task_description)

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
        self, reference: str
    ) -> Optional[str]:
        """
        Get complete content of referenced file.

        When an SOP references a file, it needs the complete content,
        not chunks. The SOP author specifically included this reference
        so we should provide the full document.

        Args:
            reference: File reference from SOP directive

        Returns:
            Complete file content or None if not found
        """
        file_path = self.resolve_resource(reference)
        if not file_path:
            return None

        # For text files, just read the complete content
        if file_path.suffix in ['.md', '.txt', '.yaml', '.yml', '.json']:
            return file_path.read_text()

        # Use MarkItDown for non-text files (PDFs, Word docs, etc.)
        document_processor = self._get_document_processor()
        if (document_processor and
                file_path.suffix.lower() in ['.pdf', '.docx', '.pptx', '.xlsx', '.png', '.jpg', '.jpeg']):
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
                        "error": str(e)
                    },
                    description=f"Failed to extract content from {file_path.name}"
                )
                # Return reference placeholder
                return f"[Unable to extract: {file_path.name}]"

        # For unsupported file types, return a reference
        return f"[Binary file: {file_path.name}]"

    # ========================================================================
    # WORKFLOW GENERATION
    # ========================================================================

    def to_workflow_template(self, sop: Dict) -> List[Dict]:
        """
        Convert SOP to workflow template for execution.

        Transforms SOP steps into workflow tasks with:
        - Agent routing preferences
        - MCP tool requirements
        - Resource file paths

        Args:
            sop: SOP dictionary with steps

        Returns:
            List of workflow task dictionaries
        """
        tasks = []
        for step_data in sop['steps']:
            task = {
                'description': step_data['text'],
                'type': 'task',
                'source': 'sop',
                'sop_id': sop['id']
            }

            # Add agent routing if specified
            if step_data.get('agent'):
                task['preferred_agent'] = step_data['agent']

            # Add MCP tool requirements
            if step_data.get('mcp_tools'):
                task['required_tools'] = step_data['mcp_tools']

            # Add file resources
            if step_data.get('resources'):
                task['resources'] = []
                for ref in step_data['resources']:
                    resource_path = self.resolve_resource(ref)
                    if resource_path:
                        task['resources'].append({
                            'reference': ref,
                            'path': str(resource_path),
                            'type': resource_path.suffix
                        })

            tasks.append(task)

        return tasks

    def format_as_guidance(self, sop: Dict) -> str:
        """
        Format SOP as guidance text for LLM interpretation.

        Used in 'guide' mode where the LLM interprets the SOP
        rather than following it as a strict template.

        Args:
            sop: SOP dictionary

        Returns:
            Formatted guidance text with all directives
        """
        guidance = f"## Standard Operating Procedure: {sop['name']}\n\n"
        guidance += f"{sop['description']}\n\n"
        guidance += "### Steps:\n"
        for i, step in enumerate(sop['steps'], 1):
            guidance += f"{i}. {step['text']}\n"
            if step.get('agent'):
                guidance += f"   (Assigned to: {step['agent']})\n"
            if step.get('mcp_tools'):
                guidance += f"   (Tools: {', '.join(step['mcp_tools'])})\n"
            if step.get('resources'):
                guidance += f"   (Resources: {', '.join(step['resources'])})\n"
        return guidance
