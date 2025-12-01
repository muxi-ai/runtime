"""
Multi-Modal Integration Engine

This module provides sophisticated multi-modal content handling with intelligent
context fusion, cross-modal attention mechanisms, and unified task processing.
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum
import re

from .. import observability

if TYPE_CHECKING:
    from ...services.llm import LLM


class ModalityType(Enum):
    """Supported modality types"""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"


class ProcessingMode(Enum):
    """Multi-modal processing modes"""

    SEQUENTIAL = "sequential"  # Process modalities one by one
    PARALLEL = "parallel"  # Process modalities simultaneously
    FUSION = "fusion"  # Integrated cross-modal processing
    ADAPTIVE = "adaptive"  # Adaptive processing based on content


@dataclass
class MultiModalContent:
    """Multi-modal content representation"""

    modality: ModalityType
    content: Any  # Content data (text, bytes, file path, etc.)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Content attributes
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    duration_seconds: Optional[float] = None
    dimensions: Optional[Tuple[int, int]] = None

    # Processing metadata
    extracted_features: Dict[str, Any] = field(default_factory=dict)
    processing_time_ms: float = 0.0
    confidence_score: float = 1.0


@dataclass
class CrossModalAttention:
    """Cross-modal attention weights and relationships"""

    source_modality: ModalityType
    target_modality: ModalityType
    attention_weight: float  # 0-1

    # Relationship metadata
    semantic_similarity: float = 0.0
    temporal_alignment: float = 0.0
    spatial_alignment: float = 0.0

    # Attention details
    attention_regions: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 1.0


@dataclass
class MultiModalProcessingResult:
    """Result of multi-modal processing"""

    unified_representation: Dict[str, Any]
    modality_results: Dict[ModalityType, Dict[str, Any]]
    cross_modal_attention: List[CrossModalAttention] = field(default_factory=list)

    # Processing metadata
    processing_mode: ProcessingMode = ProcessingMode.ADAPTIVE
    total_processing_time_ms: float = 0.0
    fusion_quality_score: float = 0.0

    # Content analysis
    dominant_modality: Optional[ModalityType] = None
    information_density: Dict[ModalityType, float] = field(default_factory=dict)
    redundancy_score: float = 0.0


class ModalityProcessor:
    """Base class for modality-specific processors"""

    def __init__(self, llm: "LLM", modality: ModalityType):
        self.llm = llm
        self.modality = modality
        self.processing_cache: Dict[str, Any] = {}

    async def process(self, content: MultiModalContent) -> Dict[str, Any]:
        """Process content for this modality"""
        raise NotImplementedError

    async def extract_features(self, content: MultiModalContent) -> Dict[str, Any]:
        """Extract features from content"""
        raise NotImplementedError

    async def generate_description(self, content: MultiModalContent) -> str:
        """Generate natural language description of content"""
        raise NotImplementedError


class TextProcessor(ModalityProcessor):
    """Advanced text processing with semantic analysis"""

    def __init__(self, llm: "LLM"):
        super().__init__(llm, ModalityType.TEXT)

    async def process(self, content: MultiModalContent) -> Dict[str, Any]:
        """Process text content with advanced NLP"""
        start_time = time.time()

        try:
            text = content.content
            if not isinstance(text, str):
                text = str(text)

            # Extract features
            features = await self.extract_features(content)

            # Semantic analysis
            semantic_analysis = await self._perform_semantic_analysis(text)

            # Generate embedding
            embedding = await self._generate_embedding(text)

            result = {
                "processed_text": text,
                "features": features,
                "semantic_analysis": semantic_analysis,
                "embedding": embedding,
                "word_count": len(text.split()),
                "character_count": len(text),
                "language": features.get("language", "unknown"),
            }

            content.processing_time_ms = (time.time() - start_time) * 1000
            return result

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"operation": "process_text_content", "error_type": type(e).__name__, "error": str(e)},
                description="Text content processing failed in multimodal fusion",
            )
            return {"error": str(e), "processed_text": content.content}

    async def extract_features(self, content: MultiModalContent) -> Dict[str, Any]:
        """Extract linguistic and semantic features from text"""
        text = content.content

        try:
            analysis_prompt = f"""
Analyze this text and extract key linguistic features:

Text: "{text}"

Extract features as JSON:
{{
    "language": "...",
    "tone": "...",
    "sentiment": "...",
    "complexity_level": "...",
    "key_topics": ["...", "..."],
    "named_entities": ["...", "..."],
    "intent": "...",
    "formality_level": "...",
    "emotional_indicators": ["...", "..."]
}}
"""

            response = await self.llm.generate(analysis_prompt, max_tokens=500, temperature=0.2)

            return self._parse_json_response(response)

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"operation": "extract_features", "error_type": type(e).__name__, "error": str(e)},
                description="Feature extraction failed in multimodal fusion",
            )
            return {
                "language": "unknown",
                "tone": "neutral",
                "sentiment": "neutral",
                "complexity_level": "medium",
            }

    async def _perform_semantic_analysis(self, text: str) -> Dict[str, Any]:
        """Perform deep semantic analysis of text"""
        try:
            semantic_prompt = f"""
Perform semantic analysis of this text:

Text: "{text}"

Analyze and provide as JSON:
{{
    "main_concepts": ["...", "..."],
    "semantic_roles": [{{"entity": "...", "role": "..."}},],
    "discourse_structure": "...",
    "coherence_score": 0.0,
    "informativeness": 0.0,
    "abstraction_level": "...",
    "domain": "..."
}}
"""

            response = await self.llm.generate(semantic_prompt, max_tokens=400, temperature=0.1)

            return self._parse_json_response(response)

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"operation": "extract_concepts", "error_type": type(e).__name__, "error": str(e)},
                description="Concept extraction failed in multimodal fusion",
            )
            return {"main_concepts": [], "domain": "general"}

    async def _generate_embedding(self, text: str) -> List[float]:
        """Generate semantic embedding for text.

        Uses the LLM's embedding capability if available, otherwise falls back
        to local sentence-transformer embeddings (all-MiniLM-L6-v2, 384 dimensions).
        """
        try:
            # Use LLM to generate embedding if available
            if hasattr(self.llm, "get_embedding"):
                return await self.llm.get_embedding(text)
            else:
                # Fallback: Use local sentence-transformer model
                try:
                    from ..memory.local_embeddings import get_local_embedding_async

                    return await get_local_embedding_async(text)
                except ImportError:
                    # If sentence-transformers not available, use linguistic fallback
                    return self._generate_semantic_fallback_embedding(text)

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"operation": "generate_embedding", "error_type": type(e).__name__, "error": str(e)},
                description="Embedding generation failed in multimodal fusion",
            )
            # Try local embeddings as last resort
            try:
                from ..memory.local_embeddings import get_local_embedding

                return get_local_embedding(text)
            except Exception:
                return [0.0] * 384  # Zero embedding as final fallback (384 for local model)

    def _generate_semantic_fallback_embedding(self, text: str) -> List[float]:
        """
        Generate a semantically meaningful fallback embedding based on
        linguistic and statistical features instead of random hash bits.
        """
        import re
        import math

        # Normalize text
        text_lower = text.lower()
        words = re.findall(r"\b\w+\b", text_lower)

        # Initialize embedding vector (512 dimensions)
        embedding = [0.0] * 512

        # 1. Basic statistical features (dimensions 0-63)
        embedding[0] = min(len(words) / 100.0, 1.0)  # Word count (normalized)
        embedding[1] = min(len(text) / 1000.0, 1.0)  # Character count
        embedding[2] = len(set(words)) / max(len(words), 1)  # Vocabulary diversity
        embedding[3] = (
            sum(len(word) for word in words) / max(len(words), 1) / 10.0
        )  # Avg word length

        # Count sentence markers
        sentence_count = len(re.findall(r"[.!?]+", text))
        embedding[4] = min(sentence_count / 20.0, 1.0)

        # Question/exclamation indicators
        embedding[5] = 1.0 if "?" in text else 0.0
        embedding[6] = 1.0 if "!" in text else 0.0

        # 2. Character frequency features (dimensions 64-127)
        char_freq = {}
        for char in text_lower:
            if char.isalpha():
                char_freq[char] = char_freq.get(char, 0) + 1

        total_chars = sum(char_freq.values())
        if total_chars > 0:
            # Map character frequencies to embedding dimensions
            for i, char in enumerate("abcdefghijklmnopqrstuvwxyz"):
                if i < 26:  # Ensure we don't exceed bounds
                    freq = char_freq.get(char, 0) / total_chars
                    embedding[64 + i] = freq

        # 3. Common word pattern features (dimensions 128-255)
        common_words = {
            "the": 0,
            "and": 1,
            "is": 2,
            "in": 3,
            "to": 4,
            "of": 5,
            "a": 6,
            "that": 7,
            "it": 8,
            "with": 9,
            "for": 10,
            "as": 11,
            "was": 12,
            "on": 13,
            "are": 14,
            "you": 15,
            "this": 16,
            "be": 17,
            "at": 18,
            "have": 19,
            "or": 20,
            "not": 21,
            "from": 22,
            "they": 23,
            "we": 24,
            "can": 25,
            "will": 26,
            "would": 27,
            "there": 28,
            "what": 29,
            "about": 30,
            "which": 31,
            "when": 32,
            "where": 33,
            "how": 34,
            "why": 35,
            "who": 36,
            "if": 37,
            "then": 38,
            "now": 39,
            "get": 40,
            "make": 41,
            "go": 42,
            "see": 43,
            "know": 44,
            "take": 45,
            "think": 46,
            "come": 47,
            "give": 48,
            "work": 49,
            "time": 50,
            "way": 51,
            "good": 52,
            "new": 53,
            "first": 54,
            "last": 55,
            "long": 56,
            "great": 57,
            "little": 58,
            "own": 59,
            "other": 60,
            "old": 61,
            "right": 62,
            "big": 63,
        }

        word_total = len(words)
        if word_total > 0:
            for word, idx in common_words.items():
                if idx < 64:  # Ensure we don't exceed allocated space
                    count = words.count(word)
                    embedding[128 + idx] = count / word_total

        # 4. Semantic category indicators (dimensions 256-383)
        semantic_patterns = {
            "technical": r"\b(?:system|process|data|algorithm|function|method|code|software|technology)\b",
            "emotional": r"\b(?:feel|emotion|happy|sad|angry|love|hate|excited|worried|calm)\b",
            "temporal": r"\b(?:yesterday|today|tomorrow|now|then|before|after|during|while)\b",
            "spatial": r"\b(?:here|there|above|below|left|right|near|far|inside|outside)\b",
            "quantitative": r"\b(?:many|few|more|less|all|some|most|several|number|amount)\b",
            "modal": r"\b(?:must|should|could|would|might|may|can|will|shall)\b",
            "negative": r"\b(?:not|no|never|nothing|nobody|nowhere|neither|nor)\b",
            "positive": r"\b(?:yes|good|great|excellent|wonderful|amazing|perfect|best)\b",
        }

        for i, (category, pattern) in enumerate(semantic_patterns.items()):
            if i < 64:  # Limit to available dimensions
                matches = len(re.findall(pattern, text_lower))
                embedding[256 + i] = min(matches / max(word_total, 1), 1.0)

        # 5. N-gram features (dimensions 384-511)
        # Simple bigram frequency for common patterns
        if len(words) > 1:
            bigrams = [f"{words[i]}_{words[i+1]}" for i in range(len(words) - 1)]
            bigram_counts = {}
            for bigram in bigrams:
                bigram_counts[bigram] = bigram_counts.get(bigram, 0) + 1

            # Use hash of bigrams for consistent but distributed representation
            for bigram, count in list(bigram_counts.items())[:64]:  # Limit to 64 bigrams
                bigram_hash = hash(bigram) % 128  # Map to remaining dimensions
                if 384 + bigram_hash < 512:
                    embedding[384 + bigram_hash] += count / len(bigrams)

        # 6. Normalize the embedding to unit length for better similarity computation
        magnitude = math.sqrt(sum(x * x for x in embedding))
        if magnitude > 0:
            embedding = [x / magnitude for x in embedding]

        return embedding

    async def generate_description(self, content: MultiModalContent) -> str:
        """Generate description of text content"""
        text = content.content
        features = content.extracted_features

        lang = features.get("language", "unknown")
        tone = features.get("tone", "neutral")
        words = len(text.split())
        return f"Text content ({words} words, {lang} language, {tone} tone)"

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON response from LLM with improved error handling and observability"""
        if not response or not response.strip():
            return {}

        # Try to extract JSON from markdown code blocks first (common LLM pattern)
        markdown_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        if markdown_match:
            json_str = markdown_match.group(1).strip()
        else:
            # Improved regex for balanced braces to avoid greedy matching
            json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", response)
            if json_match:
                json_str = json_match.group(0).strip()
            else:
                observability.observe(
                    event_type=observability.ErrorEvents.SERIALIZATION_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={"operation": "parse_json_response", "error": "no_json_found"},
                    description="No JSON found in LLM response",
                )
                return {}

        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                return parsed
            else:
                observability.observe(
                    event_type=observability.ErrorEvents.SERIALIZATION_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={"operation": "parse_json_response", "error": "json_not_dict"},
                    description="JSON in LLM response was not a dictionary",
                )
                return {}
        except json.JSONDecodeError as e:
            observability.observe(
                event_type=observability.ErrorEvents.SERIALIZATION_ERROR,
                level=observability.EventLevel.WARNING,
                data={"operation": "parse_json_response", "error": "json_decode_error", "error_details": str(e)},
                description="JSON decode error in LLM response",
            )
            return {}
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.SERIALIZATION_ERROR,
                level=observability.EventLevel.WARNING,
                data={
                    "operation": "parse_json_response",
                    "error": "unexpected_error",
                    "error_type": type(e).__name__,
                    "error_details": str(e)
                },
                description="Unexpected error parsing JSON in LLM response",
            )
            return {}


class ImageProcessor(ModalityProcessor):
    """Advanced image processing with vision analysis"""

    def __init__(self, llm: "LLM"):
        super().__init__(llm, ModalityType.IMAGE)

    async def process(self, content: MultiModalContent) -> Dict[str, Any]:
        """Process image content with vision analysis"""
        start_time = time.time()

        try:
            # Extract basic image metadata
            image_metadata = await self._extract_image_metadata(content)

            # Perform vision analysis
            vision_analysis = await self._perform_vision_analysis(content)

            # Extract visual features
            features = await self.extract_features(content)

            result = {
                "image_metadata": image_metadata,
                "vision_analysis": vision_analysis,
                "features": features,
                "dimensions": content.dimensions,
                "file_size": content.size_bytes,
            }

            content.processing_time_ms = (time.time() - start_time) * 1000
            return result

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"operation": "process_image_content", "error_type": type(e).__name__, "error": str(e)},
                description="Image content processing failed in multimodal fusion",
            )
            return {"error": str(e)}

    async def extract_features(self, content: MultiModalContent) -> Dict[str, Any]:
        """Extract visual features from image"""
        try:
            # Basic feature extraction
            features = {
                "format": content.mime_type,
                "dimensions": content.dimensions,
                "size_category": self._categorize_size(content.dimensions),
                "aspect_ratio": self._calculate_aspect_ratio(content.dimensions),
            }

            return features

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"operation": "extract_image_features", "error_type": type(e).__name__, "error": str(e)},
                description="Image feature extraction failed in multimodal fusion",
            )
            return {}

    async def _extract_image_metadata(self, content: MultiModalContent) -> Dict[str, Any]:
        """Extract technical metadata from image"""
        try:
            # Basic metadata extraction
            metadata = {
                "mime_type": content.mime_type,
                "size_bytes": content.size_bytes,
                "dimensions": content.dimensions,
            }

            # Add derived metadata
            if content.dimensions:
                metadata["megapixels"] = (content.dimensions[0] * content.dimensions[1]) / 1_000_000
                metadata["aspect_ratio"] = content.dimensions[0] / content.dimensions[1]

            return metadata

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"operation": "extract_image_features", "error_type": type(e).__name__, "error": str(e)},
                description="Image feature extraction failed in multimodal fusion",
            )
            return {}

    async def _perform_vision_analysis(self, content: MultiModalContent) -> Dict[str, Any]:
        """Perform computer vision analysis"""
        try:
            # If LLM supports vision, use it for analysis
            if hasattr(self.llm, "analyze_image"):
                analysis = await self.llm.analyze_image(content.content)
                return analysis
            else:
                # Fallback analysis
                return {
                    "description": "Image content detected",
                    "objects": [],
                    "scene": "unknown",
                    "confidence": 0.5,
                }

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"operation": "analyze_image_with_vision", "error_type": type(e).__name__, "error": str(e)},
                description="Vision analysis failed in multimodal fusion",
            )
            return {"description": "Vision analysis unavailable"}

    def _categorize_size(self, dimensions: Optional[Tuple[int, int]]) -> str:
        """Categorize image size"""
        if not dimensions:
            return "unknown"

        width, height = dimensions
        pixels = width * height

        if pixels < 100_000:
            return "thumbnail"
        elif pixels < 1_000_000:
            return "small"
        elif pixels < 5_000_000:
            return "medium"
        else:
            return "large"

    def _calculate_aspect_ratio(self, dimensions: Optional[Tuple[int, int]]) -> str:
        """Calculate aspect ratio category"""
        if not dimensions:
            return "unknown"

        width, height = dimensions
        ratio = width / height

        if 0.9 <= ratio <= 1.1:
            return "square"
        elif ratio > 1.1:
            return "landscape"
        else:
            return "portrait"

    async def generate_description(self, content: MultiModalContent) -> str:
        """Generate description of image content"""
        metadata = content.extracted_features
        dims = content.dimensions

        if dims:
            size_cat = metadata.get("size_category", "unknown")
            return f"Image content ({dims[0]}x{dims[1]}, {size_cat} size)"
        else:
            return "Image content (dimensions unknown)"


class AudioProcessor(ModalityProcessor):
    """Advanced audio processing with speech and sound analysis"""

    def __init__(self, llm: "LLM"):
        super().__init__(llm, ModalityType.AUDIO)

    async def process(self, content: MultiModalContent) -> Dict[str, Any]:
        """Process audio content"""
        start_time = time.time()

        try:
            # Extract audio metadata
            audio_metadata = await self._extract_audio_metadata(content)

            # Perform audio analysis
            audio_analysis = await self._perform_audio_analysis(content)

            # Extract features
            features = await self.extract_features(content)

            result = {
                "audio_metadata": audio_metadata,
                "audio_analysis": audio_analysis,
                "features": features,
                "duration": content.duration_seconds,
                "file_size": content.size_bytes,
            }

            content.processing_time_ms = (time.time() - start_time) * 1000
            return result

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"operation": "process_image_content", "error_type": type(e).__name__, "error": str(e)},
                description="Image content processing failed in multimodal fusion",
            )
            return {"error": str(e)}

    async def extract_features(self, content: MultiModalContent) -> Dict[str, Any]:
        """Extract audio features"""
        try:
            features = {
                "format": content.mime_type,
                "duration_seconds": content.duration_seconds,
                "duration_category": self._categorize_duration(content.duration_seconds),
                "file_size": content.size_bytes,
            }

            return features

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"operation": "extract_image_features", "error_type": type(e).__name__, "error": str(e)},
                description="Image feature extraction failed in multimodal fusion",
            )
            return {}

    async def _extract_audio_metadata(self, content: MultiModalContent) -> Dict[str, Any]:
        """Extract technical audio metadata"""
        try:
            metadata = {
                "mime_type": content.mime_type,
                "size_bytes": content.size_bytes,
                "duration_seconds": content.duration_seconds,
            }

            return metadata

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"operation": "extract_image_features", "error_type": type(e).__name__, "error": str(e)},
                description="Image feature extraction failed in multimodal fusion",
            )
            return {}

    async def _perform_audio_analysis(self, content: MultiModalContent) -> Dict[str, Any]:
        """Perform audio content analysis"""
        try:
            # If LLM supports audio, use it for analysis
            if hasattr(self.llm, "transcribe_audio"):
                analysis = await self.llm.transcribe_audio(content.content)
                return {"transcription": analysis, "has_speech": True}
            else:
                # Fallback analysis
                return {"transcription": "", "has_speech": False, "confidence": 0.5}

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"operation": "transcribe_audio", "error_type": type(e).__name__, "error": str(e)},
                description="Audio transcription failed in multimodal fusion",
            )
            return {"transcription": "", "has_speech": False}

    def _categorize_duration(self, duration: Optional[float]) -> str:
        """Categorize audio duration"""
        if not duration:
            return "unknown"

        if duration < 10:
            return "short"
        elif duration < 60:
            return "medium"
        elif duration < 300:
            return "long"
        else:
            return "very_long"

    async def generate_description(self, content: MultiModalContent) -> str:
        """Generate description of audio content"""
        duration = content.duration_seconds
        features = content.extracted_features

        if duration:
            duration_cat = features.get("duration_category", "unknown")
            return f"Audio content ({duration:.1f}s duration, {duration_cat} length)"
        else:
            return "Audio content (duration unknown)"


class MultiModalFusionEngine:
    """
    Advanced multi-modal fusion engine with cross-modal attention and
    intelligent context integration.
    """

    def __init__(self, llm: "LLM"):
        self.llm = llm

        # Initialize modality processors
        self.processors = {
            ModalityType.TEXT: TextProcessor(llm),
            ModalityType.IMAGE: ImageProcessor(llm),
            ModalityType.AUDIO: AudioProcessor(llm),
            # Note: VIDEO and DOCUMENT processors would be implemented similarly
        }

        self.fusion_cache: Dict[str, MultiModalProcessingResult] = {}

    async def process_multimodal_content(
        self,
        content_items: List[MultiModalContent],
        processing_mode: ProcessingMode = ProcessingMode.ADAPTIVE,
        fusion_options: Dict[str, Any] = None,
    ) -> MultiModalProcessingResult:
        """
        Process multiple modalities with intelligent fusion.

        Args:
            content_items: List of multi-modal content to process
            processing_mode: How to process the modalities
            fusion_options: Additional fusion configuration

        Returns:
            Unified multi-modal processing result
        """
        start_time = time.time()

        try:
            options = fusion_options or {}

            # Determine optimal processing mode if adaptive
            if processing_mode == ProcessingMode.ADAPTIVE:
                processing_mode = self._determine_optimal_mode(content_items)

            # Process individual modalities
            modality_results = await self._process_individual_modalities(
                content_items, processing_mode
            )

            # Compute cross-modal attention
            cross_modal_attention = await self._compute_cross_modal_attention(
                content_items, modality_results
            )

            # Perform fusion
            unified_representation = await self._perform_fusion(
                modality_results, cross_modal_attention, options
            )

            # Calculate fusion quality
            fusion_quality = self._calculate_fusion_quality(modality_results, cross_modal_attention)

            # Determine dominant modality
            dominant_modality = self._determine_dominant_modality(modality_results)

            # Calculate information density
            information_density = self._calculate_information_density(modality_results)

            result = MultiModalProcessingResult(
                unified_representation=unified_representation,
                modality_results=modality_results,
                cross_modal_attention=cross_modal_attention,
                processing_mode=processing_mode,
                total_processing_time_ms=(time.time() - start_time) * 1000,
                fusion_quality_score=fusion_quality,
                dominant_modality=dominant_modality,
                information_density=information_density,
                redundancy_score=self._calculate_redundancy_score(modality_results),
            )

            observability.observe(
                event_type=observability.ConversationEvents.RESPONSE_SYNTHESIZED,
                level=observability.EventLevel.INFO,
                data={
                    "modality_count": len(content_items),
                    "fusion_quality": fusion_quality,
                    "processing_time_ms": sum(
                        item.processing_time_ms
                        for item in content_items
                        if item.processing_time_ms
                    ),
                },
                description=(
                    f"Multi-modal processing completed: {len(content_items)} modalities, "
                    f"fusion quality {fusion_quality:.2f}"
                ),
            )

            return result

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.ERROR,
                data={
                    "operation": "fuse_multi_modal_content",
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "modality_count": len(content_items)
                },
                description="Multi-modal fusion failed, using fallback",
            )
            return self._create_fallback_result(content_items)

    async def _process_individual_modalities(
        self, content_items: List[MultiModalContent], processing_mode: ProcessingMode
    ) -> Dict[ModalityType, Dict[str, Any]]:
        """Process each modality individually"""

        results = {}

        if processing_mode == ProcessingMode.PARALLEL:
            # Process all modalities simultaneously
            tasks = []
            for content in content_items:
                if content.modality in self.processors:
                    processor = self.processors[content.modality]
                    tasks.append(processor.process(content))

            if tasks:
                parallel_results = await asyncio.gather(*tasks, return_exceptions=True)

                for i, content in enumerate(content_items):
                    if i < len(parallel_results) and not isinstance(parallel_results[i], Exception):
                        results[content.modality] = parallel_results[i]
        else:
            # Sequential processing
            for content in content_items:
                if content.modality in self.processors:
                    processor = self.processors[content.modality]
                    result = await processor.process(content)
                    results[content.modality] = result

        return results

    async def _compute_cross_modal_attention(
        self,
        content_items: List[MultiModalContent],
        modality_results: Dict[ModalityType, Dict[str, Any]],
    ) -> List[CrossModalAttention]:
        """Compute attention weights between modalities"""

        attention_weights = []
        modalities = list(modality_results.keys())

        # Compute pairwise attention between modalities
        for i, source_mod in enumerate(modalities):
            for j, target_mod in enumerate(modalities):
                if i != j:
                    attention = await self._compute_pairwise_attention(
                        source_mod, target_mod, modality_results
                    )
                    attention_weights.append(attention)

        return attention_weights

    async def _compute_pairwise_attention(
        self,
        source_modality: ModalityType,
        target_modality: ModalityType,
        modality_results: Dict[ModalityType, Dict[str, Any]],
    ) -> CrossModalAttention:
        """Compute attention between two modalities"""

        try:
            source_result = modality_results.get(source_modality, {})
            target_result = modality_results.get(target_modality, {})

            # Calculate semantic similarity
            semantic_similarity = await self._calculate_semantic_similarity(
                source_result, target_result
            )

            # Calculate attention weight based on information content
            source_info = self._calculate_information_content(source_result)
            target_info = self._calculate_information_content(target_result)

            # Attention weight is proportional to information relevance
            attention_weight = (semantic_similarity * (source_info + target_info)) / 2

            return CrossModalAttention(
                source_modality=source_modality,
                target_modality=target_modality,
                attention_weight=min(attention_weight, 1.0),
                semantic_similarity=semantic_similarity,
                temporal_alignment=0.0,  # Would be computed for temporal modalities
                spatial_alignment=0.0,  # Would be computed for spatial modalities
                confidence=0.8,
            )

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"operation": "compute_cross_modal_attention", "error_type": type(e).__name__, "error": str(e)},
                description="Cross-modal attention computation failed",
            )
            return CrossModalAttention(
                source_modality=source_modality,
                target_modality=target_modality,
                attention_weight=0.5,
                confidence=0.3,
            )

    async def _calculate_semantic_similarity(
        self, source_result: Dict[str, Any], target_result: Dict[str, Any]
    ) -> float:
        """Calculate semantic similarity between modality results"""
        try:
            # Extract semantic representations
            source_desc = self._extract_semantic_description(source_result)
            target_desc = self._extract_semantic_description(target_result)

            # Use LLM to assess similarity
            similarity_prompt = f"""
Compare the semantic similarity between these two content descriptions:

Content A: {source_desc}
Content B: {target_desc}

Rate their semantic similarity on a scale of 0.0 to 1.0, where:
- 0.0 = completely unrelated
- 1.0 = highly related or complementary

Provide only the numerical score:
"""

            response = await self.llm.generate(similarity_prompt, max_tokens=10, temperature=0.1)

            # Extract numerical score
            import re

            score_match = re.search(r"(\d+\.?\d*)", response)
            if score_match:
                return float(score_match.group(1))
            else:
                return 0.5

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={"operation": "assess_fusion_quality", "error_type": type(e).__name__, "error": str(e)},
                description="Fusion quality assessment failed",
            )
            return 0.5

    def _extract_semantic_description(self, result: Dict[str, Any]) -> str:
        """Extract semantic description from modality result"""
        if "description" in result:
            return result["description"]
        elif "processed_text" in result:
            return result["processed_text"][:200]  # First 200 chars
        elif "vision_analysis" in result:
            return str(result["vision_analysis"].get("description", "Visual content"))
        elif "transcription" in result:
            return result["transcription"][:200]
        else:
            return "Content processed"

    def _calculate_information_content(self, result: Dict[str, Any]) -> float:
        """Calculate information content score for a modality result"""
        score = 0.0

        # Text-based information
        if "processed_text" in result:
            text_length = len(result["processed_text"])
            score += min(text_length / 1000, 1.0)  # Normalize by 1000 chars

        # Features information
        if "features" in result:
            feature_count = len(result["features"])
            score += min(feature_count / 10, 0.5)  # Normalize by 10 features

        # Vision analysis information
        if "vision_analysis" in result:
            vision_data = result["vision_analysis"]
            if isinstance(vision_data, dict):
                score += min(len(vision_data) / 5, 0.5)

        return min(score, 1.0)

    async def _perform_fusion(
        self,
        modality_results: Dict[ModalityType, Dict[str, Any]],
        cross_modal_attention: List[CrossModalAttention],
        options: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Perform intelligent fusion of modality results"""

        try:
            # Collect all content descriptions
            content_descriptions = []
            for modality, result in modality_results.items():
                desc = self._extract_semantic_description(result)
                content_descriptions.append(f"{modality.value}: {desc}")

            # Create fusion prompt
            fusion_prompt = f"""
You are an expert multi-modal content synthesizer. Create a unified understanding
from these different modalities:

{chr(10).join(content_descriptions)}

Create a comprehensive fusion analysis as JSON:
{{
    "unified_summary": "...",
    "key_insights": ["...", "...", "..."],
    "modality_relationships": "...",
    "overall_theme": "...",
    "information_completeness": 0.0,
    "consistency_score": 0.0,
    "actionable_items": ["...", "..."]
}}
"""

            response = await self.llm.generate(fusion_prompt, max_tokens=800, temperature=0.3)

            fusion_analysis = self._parse_json_response(response)

            # Add technical fusion metadata
            fusion_result = {
                **fusion_analysis,
                "modality_count": len(modality_results),
                "processed_modalities": list(modality_results.keys()),
                "attention_weights": {
                    f"{att.source_modality.value}->{att.target_modality.value}": att.attention_weight
                    for att in cross_modal_attention
                },
                "fusion_timestamp": time.time(),
            }

            return fusion_result

        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.INTERNAL_ERROR,
                level=observability.EventLevel.WARNING,
                data={
                    "operation": "synthesize_unified_representation",
                    "error_type": type(e).__name__,
                    "error": str(e)
                },
                description="Unified representation synthesis failed",
            )
            return {
                "unified_summary": "Multi-modal content processed",
                "modality_count": len(modality_results),
                "error": str(e),
            }

    def _determine_optimal_mode(self, content_items: List[MultiModalContent]) -> ProcessingMode:
        """Determine optimal processing mode based on content"""

        # Simple heuristics for mode selection
        modality_count = len(set(item.modality for item in content_items))
        total_items = len(content_items)

        if modality_count == 1:
            return ProcessingMode.SEQUENTIAL
        elif total_items <= 3:
            return ProcessingMode.PARALLEL
        elif modality_count >= 3:
            return ProcessingMode.FUSION
        else:
            return ProcessingMode.PARALLEL

    def _calculate_fusion_quality(
        self,
        modality_results: Dict[ModalityType, Dict[str, Any]],
        cross_modal_attention: List[CrossModalAttention],
    ) -> float:
        """Calculate quality of fusion"""

        # Base quality from number of successful modalities
        base_quality = len(modality_results) / 5  # Assume max 5 modalities

        # Attention quality contribution
        if cross_modal_attention:
            total_attention = sum(att.attention_weight for att in cross_modal_attention)
            avg_attention = total_attention / len(cross_modal_attention)
            attention_quality = avg_attention * 0.5
        else:
            attention_quality = 0.0

        # Information completeness
        results_values = modality_results.values()
        total_info = sum(self._calculate_information_content(result) for result in results_values)
        info_quality = min(total_info / len(modality_results), 1.0) * 0.3

        return min(base_quality + attention_quality + info_quality, 1.0)

    def _determine_dominant_modality(
        self, modality_results: Dict[ModalityType, Dict[str, Any]]
    ) -> Optional[ModalityType]:
        """Determine which modality contains the most information"""

        if not modality_results:
            return None

        modality_scores = {}
        for modality, result in modality_results.items():
            modality_scores[modality] = self._calculate_information_content(result)

        return max(modality_scores, key=modality_scores.get)

    def _calculate_information_density(
        self, modality_results: Dict[ModalityType, Dict[str, Any]]
    ) -> Dict[ModalityType, float]:
        """Calculate information density for each modality"""

        density = {}
        for modality, result in modality_results.items():
            density[modality] = self._calculate_information_content(result)

        return density

    def _calculate_redundancy_score(
        self, modality_results: Dict[ModalityType, Dict[str, Any]]
    ) -> float:
        """Calculate redundancy between modalities"""

        if len(modality_results) < 2:
            return 0.0

        # Simple redundancy calculation based on semantic overlap
        # In a full implementation, this would use more sophisticated analysis
        return 0.3  # Placeholder value

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON response from LLM with improved error handling and observability"""
        if not response or not response.strip():
            return {}

        # Try to extract JSON from markdown code blocks first (common LLM pattern)
        markdown_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
        if markdown_match:
            json_str = markdown_match.group(1).strip()
        else:
            # Improved regex for balanced braces to avoid greedy matching
            json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", response)
            if json_match:
                json_str = json_match.group(0).strip()
            else:
                observability.observe(
                    event_type=observability.ErrorEvents.SERIALIZATION_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={"operation": "parse_json_response", "error": "no_json_found"},
                    description="No JSON found in LLM response",
                )
                return {}

        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                return parsed
            else:
                observability.observe(
                    event_type=observability.ErrorEvents.SERIALIZATION_ERROR,
                    level=observability.EventLevel.WARNING,
                    data={"operation": "parse_json_response", "error": "json_not_dict"},
                    description="JSON in LLM response was not a dictionary",
                )
                return {}
        except json.JSONDecodeError as e:
            observability.observe(
                event_type=observability.ErrorEvents.SERIALIZATION_ERROR,
                level=observability.EventLevel.WARNING,
                data={"operation": "parse_json_response", "error": "json_decode_error", "error_details": str(e)},
                description="JSON decode error in LLM response",
            )
            return {}
        except Exception as e:
            observability.observe(
                event_type=observability.ErrorEvents.SERIALIZATION_ERROR,
                level=observability.EventLevel.WARNING,
                data={
                    "operation": "parse_json_response",
                    "error": "unexpected_error",
                    "error_type": type(e).__name__,
                    "error_details": str(e)
                },
                description="Unexpected error parsing JSON in LLM response",
            )
            return {}

    def _create_fallback_result(
        self, content_items: List[MultiModalContent]
    ) -> MultiModalProcessingResult:
        """Create fallback result when processing fails"""

        return MultiModalProcessingResult(
            unified_representation={
                "unified_summary": "Multi-modal content processed with fallback",
                "modality_count": len(content_items),
                "fallback_used": True,
            },
            modality_results={},
            processing_mode=ProcessingMode.SEQUENTIAL,
            fusion_quality_score=0.5,
        )
