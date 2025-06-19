"""
Multi-Modal Integration Engine

This module provides sophisticated multi-modal content handling with intelligent
context fusion, cross-modal attention mechanisms, and unified task processing.
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from ...datatypes import Workflow, SubTask

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

    def __init__(self, llm: LLM, modality: ModalityType):
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

    def __init__(self, llm: LLM):
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
            #  Multimodal error - TODO: add observability
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
            #  Multimodal error - TODO: add observability
            _ = e  # remove this after implementing observability
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
            #  Multimodal error - TODO: add observability
            _ = e  # remove this after implementing observability
            return {"main_concepts": [], "domain": "general"}

    async def _generate_embedding(self, text: str) -> List[float]:
        """Generate semantic embedding for text"""
        try:
            # Use LLM to generate embedding if available
            if hasattr(self.llm, "get_embedding"):
                return await self.llm.get_embedding(text)
            else:
                # Fallback: simple hash-based embedding
                import hashlib

                hash_value = int(hashlib.md5(text.encode()).hexdigest(), 16)
                return [(hash_value >> i) % 2 for i in range(512)]

        except Exception as e:
            #  Multimodal error - TODO: add observability
            _ = e  # remove this after implementing observability
            return [0.0] * 512  # Zero embedding as fallback

    async def generate_description(self, content: MultiModalContent) -> str:
        """Generate description of text content"""
        text = content.content
        features = content.extracted_features

        lang = features.get("language", "unknown")
        tone = features.get("tone", "neutral")
        words = len(text.split())
        return f"Text content ({words} words, {lang} language, {tone} tone)"

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON response from LLM"""
        try:
            import re

            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            else:
                return {}
        except Exception as e:
            #  Multimodal error - TODO: add observability
            _ = e  # remove this after implementing observability
            return {}


class ImageProcessor(ModalityProcessor):
    """Advanced image processing with vision analysis"""

    def __init__(self, llm: LLM):
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
            #  Multimodal error - TODO: add observability
            _ = e  # remove this after implementing observability
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
            #  Multimodal error - TODO: add observability
            _ = e  # remove this after implementing observability
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
            #  Multimodal error - TODO: add observability
            _ = e  # remove this after implementing observability
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
            #  Multimodal error - TODO: add observability
            _ = e  # remove this after implementing observability
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

    def __init__(self, llm: LLM):
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
            #  Multimodal error - TODO: add observability
            _ = e  # remove this after implementing observability
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
            #  Multimodal error - TODO: add observability
            _ = e  # remove this after implementing observability
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
            #  Multimodal error - TODO: add observability
            _ = e  # remove this after implementing observability
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
            #  Multimodal error - TODO: add observability
            _ = e  # remove this after implementing observability
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

    def __init__(self, llm: LLM):
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

            #  Multimodal info - TODO: add observability
            #     f"Multi-modal processing completed: {len(content_items)} modalities, "
            #     f"fusion quality {fusion_quality:.2f}"
            # )

            return result

        except Exception as e:
            #  Multimodal error - TODO: add observability
            _ = e  # remove this after implementing observability
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
            source_name = source_modality.name
            target_name = target_modality.name
            #  Multimodal error - TODO: add observability
            _ = e  # remove this after implementing observability
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
            #  Multimodal error - TODO: add observability
            _ = e  # remove this after implementing observability
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
            #  Multimodal error - TODO: add observability
            _ = e  # remove this after implementing observability
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
        """Parse JSON response from LLM"""
        try:
            import re

            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            else:
                return {}
        except Exception as e:
            #  Multimodal error - TODO: add observability
            _ = e  # remove this after implementing observability
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


class MultiModalWorkflowIntegrator:
    """
    Integrates multi-modal processing into workflow execution.

    Enhances workflows with multi-modal content handling and intelligent
    task routing based on content modalities.
    """

    def __init__(self, fusion_engine: MultiModalFusionEngine):
        self.fusion_engine = fusion_engine
        self.modality_task_mapping: Dict[ModalityType, List[str]] = {
            ModalityType.TEXT: ["text_analysis", "content_generation", "summarization"],
            ModalityType.IMAGE: ["image_analysis", "visual_description", "object_detection"],
            ModalityType.AUDIO: ["transcription", "audio_analysis", "speech_processing"],
        }

    async def enhance_workflow_with_multimodal(
        self, workflow: Workflow, multimodal_content: List[MultiModalContent]
    ) -> Workflow:
        """Enhance workflow with multi-modal content processing"""

        try:
            # Process multi-modal content
            processing_result = await self.fusion_engine.process_multimodal_content(
                multimodal_content
            )

            # Add multi-modal context to workflow
            workflow.context.update(
                {
                    "multimodal_processing": processing_result.unified_representation,
                    "dominant_modality": (
                        processing_result.dominant_modality.value
                        if processing_result.dominant_modality
                        else None
                    ),
                    "modality_results": {
                        modality.value: result
                        for modality, result in processing_result.modality_results.items()
                    },
                }
            )

            # Enhance tasks with modality-specific information
            for task_id, task in workflow.tasks.items():
                await self._enhance_task_with_modality_info(task, processing_result)

            #  Multimodal info - TODO: add observability
            return workflow

        except Exception as e:
            #  Multimodal error - TODO: add observability
            _ = e  # remove this after implementing observability
            return workflow

    async def _enhance_task_with_modality_info(
        self, task: SubTask, processing_result: MultiModalProcessingResult
    ) -> None:
        """Enhance individual task with relevant modality information"""

        # Add relevant modality results to task context
        relevant_modalities = self._find_relevant_modalities_for_task(task)

        for modality in relevant_modalities:
            if modality in processing_result.modality_results:
                modality_analysis = processing_result.modality_results[modality]
                task.context[f"{modality.value}_analysis"] = modality_analysis

        # Add cross-modal attention if relevant
        task.context["cross_modal_attention"] = [
            {
                "source": att.source_modality.value,
                "target": att.target_modality.value,
                "weight": att.attention_weight,
            }
            for att in processing_result.cross_modal_attention
        ]

    def _find_relevant_modalities_for_task(self, task: SubTask) -> List[ModalityType]:
        """Find modalities relevant to a specific task"""

        relevant_modalities = []

        # Check task capabilities against modality mappings
        for modality, capabilities in self.modality_task_mapping.items():
            if any(cap in task.required_capabilities for cap in capabilities):
                relevant_modalities.append(modality)

        # If no specific mapping, include all available modalities
        if not relevant_modalities:
            relevant_modalities = list(ModalityType)

        return relevant_modalities
