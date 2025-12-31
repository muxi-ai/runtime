"""
Enhanced Multi-Modal Integration for Workflow Tasks

This module provides seamless integration of multi-modal content processing
into workflow execution, enabling tasks to receive, process, and output
rich multi-modal content.
"""

import mimetypes
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from pathlib import Path
import time
from urllib.parse import urlparse

from ...datatypes.workflow import SubTask, TaskInput, TaskOutput, Workflow
from .fusion_engine import (
    MultiModalFusionEngine,
    MultiModalContent,
    ModalityType,
    MultiModalProcessingResult,
)

# Security constants
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100MB
ALLOWED_URL_SCHEMES = {"http", "https"}
BLOCKED_URL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}  # Block local network access


@dataclass
class MultiModalTaskInput(TaskInput):
    """Enhanced task input with multi-modal content support"""

    content_items: List[MultiModalContent] = field(default_factory=list)
    fusion_context: Optional[Dict[str, Any]] = None
    processing_mode: str = "adaptive"


@dataclass
class MultiModalTaskOutput(TaskOutput):
    """Enhanced task output with multi-modal content support"""

    content_items: List[MultiModalContent] = field(default_factory=list)
    fusion_result: Optional[MultiModalProcessingResult] = None
    generated_media: List[Dict[str, Any]] = field(default_factory=list)


class WorkflowMultiModalProcessor:
    """
    Processes multi-modal content throughout workflow execution.

    Manages multi-modal content flow between tasks, applies intelligent
    fusion processing, and ensures seamless content transformation
    across the workflow pipeline.
    """

    def __init__(self, fusion_engine: MultiModalFusionEngine):
        self.fusion_engine = fusion_engine
        self.content_registry: Dict[str, MultiModalContent] = {}
        self.task_content_mapping: Dict[str, List[str]] = {}  # task_id -> content_ids

    async def process_workflow_content(
        self, workflow: Workflow, initial_content: List[MultiModalContent] = None
    ) -> Workflow:
        """
        Process multi-modal content for entire workflow.

        Args:
            workflow: Workflow to enhance with multi-modal processing
            initial_content: Initial multi-modal content for the workflow

        Returns:
            Enhanced workflow with multi-modal processing integrated
        """
        try:
            # Register initial content
            if initial_content:
                for content in initial_content:
                    await self._register_content(content)

            # Analyze workflow for multi-modal requirements
            await self._analyze_workflow_requirements(workflow)

            # Enhance tasks with multi-modal capabilities
            for task_id, task in workflow.tasks.items():
                await self._enhance_task_with_multimodal(task, workflow)

            # Set up content flow between tasks
            await self._setup_content_flow(workflow)

            return workflow

        except Exception as e:
            _ = e  # remove this after implementing observability
            return workflow

    async def _register_content(self, content: MultiModalContent) -> str:
        """Register multi-modal content and return content ID"""
        content_id = f"content_{len(self.content_registry)}"
        self.content_registry[content_id] = content
        return content_id

    async def _analyze_workflow_requirements(self, workflow: Workflow):
        """Analyze workflow tasks for multi-modal requirements"""
        multimodal_tasks = []

        for task_id, task in workflow.tasks.items():
            # Check if task requires multi-modal processing
            if self._task_requires_multimodal(task):
                multimodal_tasks.append(task_id)

        # Store analysis in workflow context
        workflow.context["multimodal_tasks"] = multimodal_tasks
        workflow.context["requires_fusion"] = len(multimodal_tasks) > 1

    def _task_requires_multimodal(self, task: SubTask) -> bool:
        """Determine if task requires multi-modal processing"""
        multimodal_capabilities = [
            "image_analysis",
            "audio_processing",
            "video_analysis",
            "multimodal_fusion",
            "content_generation",
            "media_creation",
        ]

        return any(cap in task.required_capabilities for cap in multimodal_capabilities)

    async def _enhance_task_with_multimodal(self, task: SubTask, workflow: Workflow):
        """Enhance individual task with multi-modal capabilities"""
        try:
            # Determine content requirements for this task
            required_modalities = self._get_required_modalities(task)

            # Set up multi-modal inputs
            task.multimodal_inputs = await self._prepare_task_inputs(
                task, required_modalities, workflow
            )

            # Configure multi-modal outputs
            task.multimodal_outputs = self._configure_task_outputs(task, required_modalities)

            # Add multi-modal processing instructions
            task.processing_instructions = self._create_processing_instructions(
                task, required_modalities
            )

        except Exception as e:
            _ = e  # remove this after implementing observability

    def _get_required_modalities(self, task: SubTask) -> List[ModalityType]:
        """Determine which modalities this task requires"""
        modality_mapping = {
            "image_analysis": [ModalityType.IMAGE],
            "audio_processing": [ModalityType.AUDIO],
            "video_analysis": [ModalityType.VIDEO],
            "text_processing": [ModalityType.TEXT],
            "document_analysis": [ModalityType.DOCUMENT],
            "multimodal_fusion": [ModalityType.TEXT, ModalityType.IMAGE, ModalityType.AUDIO],
        }

        required_modalities = set()
        for capability in task.required_capabilities:
            if capability in modality_mapping:
                required_modalities.update(modality_mapping[capability])

        return list(required_modalities)

    async def _prepare_task_inputs(
        self, task: SubTask, required_modalities: List[ModalityType], workflow: Workflow
    ) -> List[MultiModalTaskInput]:
        """Prepare multi-modal inputs for task"""
        task_inputs = []

        # Get relevant content from registry
        relevant_content = self._get_relevant_content(required_modalities)

        # Get content from dependencies
        dependency_content = await self._get_dependency_content(task, workflow)

        # Combine and create task inputs
        all_content = relevant_content + dependency_content

        if all_content:
            task_input = MultiModalTaskInput(content_items=all_content, processing_mode="adaptive")
            task_inputs.append(task_input)

        return task_inputs

    def _get_relevant_content(
        self, required_modalities: List[ModalityType]
    ) -> List[MultiModalContent]:
        """Get content items matching required modalities"""
        relevant_content = []

        for content in self.content_registry.values():
            if content.modality in required_modalities:
                relevant_content.append(content)

        return relevant_content

    async def _get_dependency_content(
        self, task: SubTask, workflow: Workflow
    ) -> List[MultiModalContent]:
        """Get multi-modal content from task dependencies"""
        dependency_content = []

        for dep_task_id in task.dependencies:
            if dep_task_id in workflow.tasks:
                dep_task = workflow.tasks[dep_task_id]

                # Check if dependency has multi-modal outputs
                if hasattr(dep_task, "multimodal_outputs") and dep_task.multimodal_outputs:
                    for output in dep_task.multimodal_outputs:
                        if isinstance(output, MultiModalTaskOutput):
                            dependency_content.extend(output.content_items)

        return dependency_content

    def _configure_task_outputs(
        self, task: SubTask, required_modalities: List[ModalityType]
    ) -> List[MultiModalTaskOutput]:
        """Configure expected multi-modal outputs for task"""
        # Determine expected output modalities based on task type
        output_config = self._get_output_configuration(task, required_modalities)

        task_outputs = []
        for config in output_config:
            output = MultiModalTaskOutput(
                name=config["name"],
                description=config["description"],
                content_type=config.get("content_type", "mixed"),
            )
            task_outputs.append(output)

        return task_outputs

    def _get_output_configuration(
        self, task: SubTask, input_modalities: List[ModalityType]
    ) -> List[Dict[str, Any]]:
        """Get output configuration based on task capabilities"""
        output_configs = []

        # Map capabilities to expected outputs
        capability_outputs = {
            "image_analysis": [
                {
                    "name": "analysis_result",
                    "description": "Image analysis results",
                    "content_type": "text",
                },
                {
                    "name": "annotated_image",
                    "description": "Annotated image",
                    "content_type": "image",
                },
            ],
            "content_generation": [
                {
                    "name": "generated_content",
                    "description": "Generated content",
                    "content_type": "text",
                }
            ],
            "multimodal_fusion": [
                {
                    "name": "fusion_result",
                    "description": "Fused multi-modal content",
                    "content_type": "mixed",
                }
            ],
        }

        for capability in task.required_capabilities:
            if capability in capability_outputs:
                output_configs.extend(capability_outputs[capability])

        return output_configs or [
            {"name": "default_output", "description": "Task output", "content_type": "text"}
        ]

    def _create_processing_instructions(
        self, task: SubTask, required_modalities: List[ModalityType]
    ) -> Dict[str, Any]:
        """Create multi-modal processing instructions for task"""
        return {
            "required_modalities": [mod.value for mod in required_modalities],
            "fusion_enabled": len(required_modalities) > 1,
            "processing_mode": "adaptive",
            "quality_requirements": {
                "min_fusion_quality": 0.7,
                "preserve_original_content": True,
                "generate_fallbacks": True,
            },
        }

    async def _setup_content_flow(self, workflow: Workflow):
        """Set up content flow between tasks in workflow"""
        # Analyze task dependencies for content flow
        content_flow = {}

        for task_id, task in workflow.tasks.items():
            for dep_id in task.dependencies:
                if dep_id not in content_flow:
                    content_flow[dep_id] = []
                content_flow[dep_id].append(task_id)

        # Store content flow configuration
        workflow.context["content_flow"] = content_flow


class TaskInputProcessor:
    """
    Processes multi-modal inputs for individual tasks.

    Handles file uploads, content type detection, preprocessing,
    and preparation of multi-modal content for task execution.
    """

    def __init__(self, fusion_engine: MultiModalFusionEngine):
        self.fusion_engine = fusion_engine
        self.supported_formats = {
            ModalityType.IMAGE: ["jpg", "jpeg", "png", "gif", "svg", "webp"],
            ModalityType.AUDIO: ["mp3", "wav", "m4a", "ogg", "flac"],
            ModalityType.VIDEO: ["mp4", "avi", "mkv", "webm", "mov"],
            ModalityType.DOCUMENT: ["pdf", "doc", "docx", "txt", "md", "rtf"],
        }

    async def process_task_inputs(
        self, task: SubTask, raw_inputs: List[Any]
    ) -> List[MultiModalTaskInput]:
        """
        Process raw inputs into multi-modal task inputs.

        Args:
            task: Task to process inputs for
            raw_inputs: Raw input data (files, text, URLs, etc.)

        Returns:
            Processed multi-modal task inputs
        """
        try:
            processed_inputs = []

            for raw_input in raw_inputs:
                # Detect content type and create MultiModalContent
                content_items = await self._process_single_input(raw_input)

                if content_items:
                    task_input = MultiModalTaskInput(
                        content_items=content_items, processing_mode="adaptive"
                    )
                    processed_inputs.append(task_input)

            return processed_inputs

        except Exception as e:
            _ = e  # remove this after implementing observability
            return []

    async def _process_single_input(self, raw_input: Any) -> List[MultiModalContent]:
        """Process a single input item into MultiModalContent"""
        content_items = []

        if isinstance(raw_input, str):
            # Handle text input or file path
            if self._is_file_path(raw_input):
                content_item = await self._process_file_input(raw_input)
                if content_item:
                    content_items.append(content_item)
            else:
                # Treat as text content
                content_item = self._create_text_content(raw_input)
                content_items.append(content_item)

        elif isinstance(raw_input, bytes):
            # Handle binary data
            content_item = await self._process_binary_input(raw_input)
            if content_item:
                content_items.append(content_item)

        elif isinstance(raw_input, dict):
            # Handle structured input
            content_item = await self._process_structured_input(raw_input)
            if content_item:
                content_items.append(content_item)

        return content_items

    def _is_file_path(self, input_str: str) -> bool:
        """Check if string is a file path"""
        return (
            Path(input_str).exists()
            or input_str.startswith(("http://", "https://"))
            or "." in input_str
            and len(input_str.split(".")[-1]) <= 4
        )

    async def _process_file_input(self, file_path: str) -> Optional[MultiModalContent]:
        """Process file input into MultiModalContent with security validations"""
        try:
            # Detect file type
            mime_type, _ = mimetypes.guess_type(file_path)
            modality = self._detect_modality_from_mime(mime_type)

            if modality is None:
                return None

            # Handle local file vs URL
            if Path(file_path).exists():
                # Validate file size before reading
                file_path_obj = Path(file_path)
                file_size = file_path_obj.stat().st_size

                if file_size > MAX_FILE_SIZE_BYTES:
                    # File too large, reject for security
                    return None

                # Read file content (now that we've validated size)
                with open(file_path, "rb") as f:
                    content = f.read()

                # Create MultiModalContent for local file
                content_item = MultiModalContent(
                    modality=modality,
                    content=content,
                    mime_type=mime_type,
                    metadata={"source": file_path, "filename": file_path_obj.name},
                )
                content_item.size_bytes = file_size

            else:
                # Validate URL before storing
                if not self._validate_url(file_path):
                    # Invalid or malicious URL, reject for security
                    return None

                # Create MultiModalContent for URL (store URL for later processing)
                content_item = MultiModalContent(
                    modality=modality,
                    content=file_path,  # Store validated URL for later processing
                    mime_type=mime_type,
                    metadata={"source": file_path, "is_url": True},
                )

            return content_item

        except Exception as e:
            _ = e  # remove this after implementing observability
            return None

    def _validate_url(self, url: str) -> bool:
        """Validate URL for security concerns"""
        try:
            parsed = urlparse(url)

            # Check if scheme is allowed
            if parsed.scheme not in ALLOWED_URL_SCHEMES:
                return False

            # Check if host is blocked (prevent local network access)
            if parsed.hostname and parsed.hostname.lower() in BLOCKED_URL_HOSTS:
                return False

            # Check for basic URL structure
            if not parsed.netloc:
                return False

            # Additional security checks
            if parsed.hostname:
                # Block IP addresses in private ranges
                hostname_lower = parsed.hostname.lower()
                private_ranges = ["192.168.", "10.", "172.16.", "172.31.", "localhost"]
                if any(hostname_lower.startswith(prefix) for prefix in private_ranges):
                    return False

            return True

        except Exception:
            # If URL parsing fails, consider it invalid
            return False

    def _detect_modality_from_mime(self, mime_type: Optional[str]) -> Optional[ModalityType]:
        """Detect modality from MIME type"""
        if not mime_type:
            return None

        mime_main = mime_type.split("/")[0]

        if mime_main == "image":
            return ModalityType.IMAGE
        elif mime_main == "audio":
            return ModalityType.AUDIO
        elif mime_main == "video":
            return ModalityType.VIDEO
        elif mime_main == "text" or mime_type == "application/pdf":
            return ModalityType.DOCUMENT
        else:
            return ModalityType.DOCUMENT  # Default fallback

    def _create_text_content(self, text: str) -> MultiModalContent:
        """Create text content item"""
        return MultiModalContent(
            modality=ModalityType.TEXT,
            content=text,
            mime_type="text/plain",
            size_bytes=len(text.encode("utf-8")),
            metadata={"source": "direct_input"},
        )

    async def _process_binary_input(self, binary_data: bytes) -> Optional[MultiModalContent]:
        """Process binary input data"""
        try:
            # Try to detect content type from binary data
            # This is a simplified implementation
            if binary_data.startswith(b"\x89PNG"):
                modality = ModalityType.IMAGE
                mime_type = "image/png"
            elif binary_data.startswith(b"\xff\xd8\xff"):
                modality = ModalityType.IMAGE
                mime_type = "image/jpeg"
            else:
                # Default to document
                modality = ModalityType.DOCUMENT
                mime_type = "application/octet-stream"

            return MultiModalContent(
                modality=modality,
                content=binary_data,
                mime_type=mime_type,
                size_bytes=len(binary_data),
                metadata={"source": "binary_input"},
            )

        except Exception as e:
            _ = e  # remove this after implementing observability
            return None

    async def _process_structured_input(
        self, structured_data: Dict[str, Any]
    ) -> Optional[MultiModalContent]:
        """Process structured input data"""
        try:
            # Extract content type and data
            content_type = structured_data.get("type", "text")
            content_data = structured_data.get("data", "")

            # Map content type to modality
            type_mapping = {
                "text": ModalityType.TEXT,
                "image": ModalityType.IMAGE,
                "audio": ModalityType.AUDIO,
                "video": ModalityType.VIDEO,
                "document": ModalityType.DOCUMENT,
            }

            modality = type_mapping.get(content_type, ModalityType.TEXT)

            return MultiModalContent(
                modality=modality,
                content=content_data,
                mime_type=structured_data.get("mime_type", "text/plain"),
                metadata=structured_data.get("metadata", {}),
            )

        except Exception as e:
            _ = e  # remove this after implementing observability
            return None


class TaskOutputProcessor:
    """
    Processes multi-modal outputs from task execution.

    Handles rich output generation, content synthesis, format conversion,
    and preparation of multi-modal results for subsequent tasks.
    """

    def __init__(self, fusion_engine: MultiModalFusionEngine):
        self.fusion_engine = fusion_engine

    async def process_task_outputs(
        self, task: SubTask, raw_outputs: List[Any]
    ) -> List[MultiModalTaskOutput]:
        """
        Process raw task outputs into multi-modal task outputs.

        Args:
            task: Task that generated the outputs
            raw_outputs: Raw output data from task execution

        Returns:
            Processed multi-modal task outputs
        """
        try:
            processed_outputs = []

            for raw_output in raw_outputs:
                # Convert to multi-modal content
                content_items = await self._convert_output_to_content(raw_output, task)

                # Create task output
                task_output = MultiModalTaskOutput(
                    name=f"output_{len(processed_outputs)}",
                    content_items=content_items,
                    metadata={"task_id": task.id, "generated_at": time.time()},
                )

                processed_outputs.append(task_output)

            return processed_outputs

        except Exception as e:
            _ = e  # remove this after implementing observability
            return []

    async def _convert_output_to_content(
        self, raw_output: Any, task: SubTask
    ) -> List[MultiModalContent]:
        """Convert raw output to MultiModalContent items"""
        content_items = []

        if isinstance(raw_output, str):
            # Text output
            content_item = MultiModalContent(
                modality=ModalityType.TEXT,
                content=raw_output,
                mime_type="text/plain",
                metadata={"task_id": task.id, "output_type": "text"},
            )
            content_items.append(content_item)

        elif isinstance(raw_output, dict):
            # Structured output - may contain multiple content types
            for key, value in raw_output.items():
                if key in ["image", "chart", "visualization"]:
                    # Image/chart output
                    content_item = MultiModalContent(
                        modality=ModalityType.IMAGE,
                        content=value,
                        mime_type="image/png",
                        metadata={"task_id": task.id, "output_type": key},
                    )
                    content_items.append(content_item)

                elif key in ["audio", "speech"]:
                    # Audio output
                    content_item = MultiModalContent(
                        modality=ModalityType.AUDIO,
                        content=value,
                        mime_type="audio/wav",
                        metadata={"task_id": task.id, "output_type": key},
                    )
                    content_items.append(content_item)

                else:
                    # Default to text
                    content_item = MultiModalContent(
                        modality=ModalityType.TEXT,
                        content=str(value),
                        mime_type="text/plain",
                        metadata={"task_id": task.id, "output_type": key},
                    )
                    content_items.append(content_item)

        return content_items

    async def synthesize_outputs(
        self, task_outputs: List[MultiModalTaskOutput]
    ) -> MultiModalProcessingResult:
        """
        Synthesize multiple task outputs using fusion engine.

        Args:
            task_outputs: Task outputs to synthesize

        Returns:
            Synthesized multi-modal result
        """
        try:
            # Collect all content items
            all_content = []
            for output in task_outputs:
                all_content.extend(output.content_items)

            # Use fusion engine to synthesize
            if all_content:
                result = await self.fusion_engine.process_multimodal_content(
                    content_items=all_content, fusion_options={"synthesis_mode": "comprehensive"}
                )
                return result
            else:
                # Create empty result
                return MultiModalProcessingResult(
                    unified_representation={"summary": "No content to synthesize"},
                    modality_results={},
                )

        except Exception as e:
            return MultiModalProcessingResult(
                unified_representation={"error": str(e)}, modality_results={}
            )
