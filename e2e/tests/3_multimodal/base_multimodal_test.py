#!/usr/bin/env python3
"""Base test class for Area 3 Multimodal tests with standardized patterns."""

import sys
from pathlib import Path
from typing import Dict, Tuple, List
import base64

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from muxi.formation import Formation  # noqa: E402

# Import from common module
from common import TestOutputFormatter  # noqa: E402


class BaseMultimodalTest:
    """Base class for multimodal tests with simplified setup."""

    # Shared formation directory for all multimodal tests
    FORMATION_DIR = Path(__file__).parent / "formations" / "formation-multimodal"

    # Default formation file
    DEFAULT_FORMATION = "formation.afs"

    # Test file types
    TEST_FILES = {
        "image": {
            "extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp"],
            "mime_types": ["image/jpeg", "image/png", "image/gif", "image/bmp"],
        },
        "audio": {
            "extensions": [".mp3", ".wav", ".m4a", ".ogg"],
            "mime_types": ["audio/mpeg", "audio/wav", "audio/mp4", "audio/ogg"],
        },
        "video": {
            "extensions": [".mp4", ".avi", ".mov", ".webm"],
            "mime_types": ["video/mp4", "video/x-msvideo", "video/quicktime", "video/webm"],
        },
        "document": {
            "extensions": [".pdf", ".docx", ".txt", ".md"],
            "mime_types": [
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "text/plain",
                "text/markdown",
            ],
        },
    }

    def __init__(self):
        """Initialize base multimodal test."""
        self.formatter = TestOutputFormatter()
        self.formation = None
        self.overlord = None

    async def setup_multimodal_formation(self, formation_file: str = None) -> Formation:
        """Setup formation with multimodal capabilities.

        Args:
            formation_file: Optional specific formation file, defaults to formation.afs

        Returns:
            Configured Formation instance
        """
        if formation_file is None:
            formation_file = self.DEFAULT_FORMATION

        formation_path = self.FORMATION_DIR / formation_file

        self.formation = Formation()
        await self.formation.load(str(formation_path))

        # Store overlord reference
        self.overlord = await self.formation.start_overlord()

        return self.formation

    async def process_file(
        self, file_path: str, user_message: str = None, user_id: str = "test_user"
    ) -> Tuple[bool, str]:
        """Process a file through multimodal service.

        Args:
            file_path: Path to the file to process
            user_message: Optional message to accompany the file
            user_id: User ID for the request

        Returns:
            Tuple of (success, response_text)
        """
        try:
            # Read file content
            with open(file_path, "rb") as f:
                file_content = f.read()

            # Determine file type
            file_extension = Path(file_path).suffix.lower()
            mime_type = self.get_mime_type(file_extension)

            # Create file data structure
            file_data = {
                "filename": Path(file_path).name,
                "content": file_content,
                "content_type": mime_type,
            }

            # Process through overlord using appropriate method
            if user_message:
                # Use chat method with message and files
                response = await self.overlord.chat(
                    user_id=user_id,
                    message=user_message,
                    files=[file_data],
                    use_async=False,
                    stream=False,
                )
            else:
                # Use avchat for automatic processing (audio/video files)
                response = await self.overlord.avchat(
                    files=[file_data], user_id=user_id, use_async=False, stream=False
                )

            # Handle response
            if hasattr(response, "__aiter__"):
                response_text = ""
                async for chunk in response:
                    response_text += chunk
            else:
                response_text = response.content if hasattr(response, "content") else str(response)

            return True, response_text

        except Exception as e:
            return False, f"Error processing file: {str(e)}"

    async def process_image(
        self, image_path: str, question: str = None, user_id: str = "test_user"
    ) -> Tuple[bool, str]:
        """Process an image file.

        Args:
            image_path: Path to the image file
            question: Optional question about the image
            user_id: User ID for the request

        Returns:
            Tuple of (success, response_text)
        """
        if question is None:
            question = "What do you see in this image?"

        return await self.process_file(image_path, question, user_id)

    async def process_audio(
        self, audio_path: str, task: str = None, user_id: str = "test_user"
    ) -> Tuple[bool, str]:
        """Process an audio file.

        Args:
            audio_path: Path to the audio file
            task: Optional task description
            user_id: User ID for the request

        Returns:
            Tuple of (success, response_text)
        """
        if task is None:
            task = "Please transcribe this audio."

        return await self.process_file(audio_path, task, user_id)

    async def process_document(
        self, doc_path: str, query: str = None, user_id: str = "test_user"
    ) -> Tuple[bool, str]:
        """Process a document file.

        Args:
            doc_path: Path to the document file
            query: Optional query about the document
            user_id: User ID for the request

        Returns:
            Tuple of (success, response_text)
        """
        if query is None:
            query = "Please summarize this document."

        return await self.process_file(doc_path, query, user_id)

    def get_mime_type(self, extension: str) -> str:
        """Get MIME type for a file extension.

        Args:
            extension: File extension (e.g., '.jpg')

        Returns:
            MIME type string
        """
        extension = extension.lower()

        for file_type, info in self.TEST_FILES.items():
            if extension in info["extensions"]:
                # Return first matching MIME type
                return info["mime_types"][0]

        # Default to octet-stream for unknown types
        return "application/octet-stream"

    def encode_file_base64(self, file_path: str) -> str:
        """Encode a file as base64.

        Args:
            file_path: Path to the file

        Returns:
            Base64 encoded string
        """
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    async def test_multimodal_capabilities(self) -> Tuple[bool, Dict[str, bool]]:
        """Test basic multimodal capabilities.

        Returns:
            Tuple of (all_passed, capabilities_dict)
        """
        capabilities = {}
        all_passed = True

        # Test image processing
        try:
            # Create a simple test image (1x1 pixel PNG)
            test_image = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x00\x00\x00\x00IEND\xaeB`\x82"  # noqa: E501

            test_path = Path("/tmp/test_image.png")
            test_path.write_bytes(test_image)

            success, _ = await self.process_image(str(test_path))
            capabilities["image"] = success
            if not success:
                all_passed = False

        except Exception:
            capabilities["image"] = False
            all_passed = False

        # Test text processing
        try:
            test_text = "This is a test document."
            test_path = Path("/tmp/test_doc.txt")
            test_path.write_text(test_text)

            success, _ = await self.process_document(str(test_path))
            capabilities["document"] = success
            if not success:
                all_passed = False

        except Exception:
            capabilities["document"] = False
            all_passed = False

        return all_passed, capabilities

    async def cleanup(self):
        """Clean up formation and resources."""
        if self.formation:
            try:
                await self.formation.shutdown()
            except Exception:
                pass
        self.formation = None
        self.overlord = None

    def print_test_header(self, test_name: str, description: str):
        """Print standardized test header."""
        self.formatter.print_test_header(test_name, description)

    def print_test_result(
        self,
        test_name: str,
        success: bool,
        checks: List[str],
        transcript: List[Tuple[str, str]],
        duration: float,
    ):
        """Print standardized test result."""
        self.formatter.print_test_result(test_name, success, checks, transcript, duration)
