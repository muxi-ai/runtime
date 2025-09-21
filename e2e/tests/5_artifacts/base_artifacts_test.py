#!/usr/bin/env python3
"""Base test class for Area 5 Artifacts tests with standardized patterns."""

import sys
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import json

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from muxi.formation import Formation  # noqa: E402

# Import from common module
from common import TestOutputFormatter  # noqa: E402


class BaseArtifactsTest:
    """Base class for Artifacts (File Generation) tests."""

    # Shared formation directory for all artifacts tests
    FORMATION_DIR = Path(__file__).parent / "formations" / "formation-file-generation"

    # File type configurations for different test scenarios
    FILE_TYPES = {
        "chart": {
            "mime_types": ["image/png", "image/jpeg", "image/svg+xml"],
            "extensions": [".png", ".jpg", ".jpeg", ".svg"],
        },
        "document": {
            "mime_types": [
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/pdf",
                "text/plain",
            ],
            "extensions": [".docx", ".pdf", ".txt"],
        },
        "code": {
            "mime_types": ["text/plain", "application/javascript", "text/x-python"],
            "extensions": [".py", ".js", ".ts", ".html", ".css", ".json", ".yaml"],
        },
        "data": {
            "mime_types": ["application/json", "text/csv", "application/xml"],
            "extensions": [".json", ".csv", ".xml", ".xlsx"],
        },
    }

    def __init__(self):
        """Initialize base artifacts test."""
        self.formatter = TestOutputFormatter()
        self.formation = None
        self.overlord = None
        self.generated_artifacts = []

    async def setup_artifacts_formation(self) -> Formation:
        """Setup formation with file generation MCP servers.

        Returns:
            Configured Formation instance
        """
        formation_path = self.FORMATION_DIR / "formation.yaml"

        self.formation = Formation()
        await self.formation.load(str(formation_path))

        # Store overlord reference
        self.overlord = await self.formation.start_overlord()

        return self.formation

    async def generate_artifact(
        self, request: str, user_id: str = "test_user", session_id: str = "test_session"
    ) -> Tuple[bool, Any]:
        """Generate an artifact through natural language request.

        Args:
            request: Natural language request for file generation
            user_id: User ID for the request
            session_id: Session ID for the request

        Returns:
            Tuple of (success, response)
        """
        try:
            # Execute through overlord
            response = await self.overlord.chat(
                request, user_id=user_id, session_id=session_id, use_async=False, stream=False
            )

            # Handle response
            if hasattr(response, "__aiter__"):
                response_text = ""
                async for chunk in response:
                    response_text += chunk
                # Create mock response object for compatibility
                response = type("MockResponse", (), {"content": response_text, "artifacts": []})()

            success = hasattr(response, "artifacts") and len(response.artifacts) > 0

            if success:
                self.generated_artifacts.extend(response.artifacts)

            return success, response

        except Exception as e:
            return False, f"Artifact generation error: {str(e)}"

    def validate_artifact(
        self, artifact: Any, expected_type: str, expected_filename_pattern: Optional[str] = None
    ) -> Dict[str, bool]:
        """Validate an artifact against expected criteria.

        Args:
            artifact: Artifact object to validate
            expected_type: Expected artifact type from FILE_TYPES
            expected_filename_pattern: Optional filename pattern to check

        Returns:
            Dictionary of validation results
        """
        validation = {
            "has_data_url": False,
            "has_correct_mime_type": False,
            "has_correct_extension": False,
            "has_thumbnail": False,
            "filename_matches_pattern": True,  # Default to True if no pattern
        }

        if not artifact:
            return validation

        # Check data URL
        if hasattr(artifact, "data_url") and artifact.data_url:
            validation["has_data_url"] = artifact.data_url.startswith("data:")

        # Check MIME type
        if expected_type in self.FILE_TYPES and hasattr(artifact, "data_url") and artifact.data_url:
            expected_mimes = self.FILE_TYPES[expected_type]["mime_types"]
            validation["has_correct_mime_type"] = any(
                artifact.data_url.startswith(f"data:{mime}") for mime in expected_mimes
            )

        # Check file extension
        if expected_type in self.FILE_TYPES and hasattr(artifact, "filename") and artifact.filename:
            expected_extensions = self.FILE_TYPES[expected_type]["extensions"]
            validation["has_correct_extension"] = any(
                artifact.filename.lower().endswith(ext) for ext in expected_extensions
            )

        # Check thumbnail (common for images and documents)
        if hasattr(artifact, "thumbnail") and artifact.thumbnail:
            validation["has_thumbnail"] = artifact.thumbnail.startswith("data:image/")

        # Check filename pattern
        if expected_filename_pattern and hasattr(artifact, "filename") and artifact.filename:
            validation["filename_matches_pattern"] = (
                expected_filename_pattern.lower() in artifact.filename.lower()
            )

        return validation

    async def test_chart_generation(
        self, chart_type: str, data_description: str
    ) -> Tuple[bool, str]:
        """Test generation of charts/visualizations.

        Args:
            chart_type: Type of chart (bar, line, pie, etc.)
            data_description: Description of data to visualize

        Returns:
            Tuple of (success, details)
        """
        request = f"Create a {chart_type} chart showing {data_description}"
        success, response = await self.generate_artifact(request)

        if not success:
            return False, f"Failed to generate {chart_type} chart"

        if not hasattr(response, "artifacts") or len(response.artifacts) == 0:
            return False, "No artifacts generated"

        artifact = response.artifacts[0]
        validation = self.validate_artifact(artifact, "chart")

        if validation["has_data_url"] and validation["has_correct_mime_type"]:
            return True, f"Successfully generated {chart_type} chart"
        else:
            return False, f"Invalid {chart_type} chart artifact"

    async def test_document_generation(
        self, doc_type: str, content_description: str
    ) -> Tuple[bool, str]:
        """Test generation of documents.

        Args:
            doc_type: Type of document (Word, PDF, etc.)
            content_description: Description of document content

        Returns:
            Tuple of (success, details)
        """
        request = f"Create a {doc_type} document with {content_description}"
        success, response = await self.generate_artifact(request)

        if not success:
            return False, f"Failed to generate {doc_type} document"

        if not hasattr(response, "artifacts") or len(response.artifacts) == 0:
            return False, "No artifacts generated"

        artifact = response.artifacts[0]
        validation = self.validate_artifact(artifact, "document")

        if validation["has_data_url"] and validation["has_correct_extension"]:
            return True, f"Successfully generated {doc_type} document"
        else:
            return False, f"Invalid {doc_type} document artifact"

    async def test_code_generation(self, language: str, code_description: str) -> Tuple[bool, str]:
        """Test generation of code files.

        Args:
            language: Programming language
            code_description: Description of code to generate

        Returns:
            Tuple of (success, details)
        """
        request = f"Create a {language} file with {code_description}"
        success, response = await self.generate_artifact(request)

        if not success:
            return False, f"Failed to generate {language} code file"

        if not hasattr(response, "artifacts") or len(response.artifacts) == 0:
            return False, "No artifacts generated"

        artifact = response.artifacts[0]
        validation = self.validate_artifact(artifact, "code")

        if validation["has_data_url"]:
            return True, f"Successfully generated {language} code file"
        else:
            return False, f"Invalid {language} code file artifact"

    async def test_multi_artifact_generation(self, requests: List[str]) -> Tuple[bool, List[str]]:
        """Test generation of multiple artifacts.

        Args:
            requests: List of generation requests

        Returns:
            Tuple of (success, results)
        """
        results = []
        all_success = True

        for request in requests:
            success, response = await self.generate_artifact(request)
            if success and hasattr(response, "artifacts") and len(response.artifacts) > 0:
                results.append(f"Generated: {response.artifacts[0].filename}")
            else:
                results.append(f"Failed: {request}")
                all_success = False

            # Small delay between generations
            await asyncio.sleep(1)

        return all_success, results

    async def setup_formation(self) -> Formation:
        """Setup formation - alias for setup_artifacts_formation for compatibility."""
        return await self.setup_artifacts_formation()

    async def cleanup(self):
        """Clean up formation and resources."""
        if self.formation:
            try:
                await self.formation.shutdown()
            except Exception:
                pass
        self.formation = None
        self.overlord = None
        self.generated_artifacts = []

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

    def save_test_results(self, test_name: str, success: bool, response: Any, details: Dict = None):
        """Save test results to JSON file for analysis.

        Args:
            test_name: Name of the test
            success: Whether test passed
            response: Response object
            details: Additional test details
        """
        output_dir = Path(__file__).parent / "results"
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / f"{test_name}.json"

        result_data = {
            "test": test_name,
            "status": "PASSED" if success else "FAILED",
            "timestamp": time.time(),
            "artifacts_count": (len(response.artifacts) if hasattr(response, "artifacts") else 0),
            "response_preview": (
                response.content[:200] if hasattr(response, "content") else str(response)[:200]
            ),
        }

        if hasattr(response, "artifacts") and response.artifacts:
            result_data["artifacts"] = [
                {
                    "type": getattr(artifact, "type", "unknown"),
                    "format": getattr(artifact, "format", "unknown"),
                    "filename": getattr(artifact, "filename", "unknown"),
                    "has_data_url": bool(
                        hasattr(artifact, "data_url")
                        and artifact.data_url
                        and artifact.data_url.startswith("data:")
                    ),
                    "has_thumbnail": bool(
                        hasattr(artifact, "thumbnail")
                        and artifact.thumbnail
                        and artifact.thumbnail.startswith("data:")
                    ),
                }
                for artifact in response.artifacts
            ]

        if details:
            result_data.update(details)

        with open(output_file, "w") as f:
            json.dump(result_data, f, indent=2)

        print(f"💾 Results saved to: {output_file}")
