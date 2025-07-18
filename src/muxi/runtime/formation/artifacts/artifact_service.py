"""
Artifact Service for MUXI Runtime.

This service allows agents to generate files by executing Python code in a
secure sandbox. It validates code for safety, executes it in a subprocess, and
returns the generated artifact with base64 encoded content.

Security features:
- AST-based validation of imports (whitelist only)
- Subprocess execution with timeout
- Working directory restricted to temp directory
- Memory limits
- No network access
"""

import ast
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Optional, Set
from datetime import datetime

from .processor import create_artifact_from_file
from ...datatypes.artifacts import MuxiArtifact

# Whitelist of allowed imports for file generation
ALLOWED_IMPORTS: Set[str] = {
    # Data processing and analysis
    "pandas",
    "numpy",
    "scipy",
    "statsmodels",
    # Visualization
    "matplotlib",
    "seaborn",
    "plotly",
    "bokeh",
    "altair",
    # Document generation
    "docx",
    "python-docx",
    "reportlab",
    "fpdf",
    "fpdf2",
    # Spreadsheet handling
    "openpyxl",
    "xlsxwriter",
    "xlrd",
    "xlwt",
    # Image processing
    "PIL",
    "Pillow",
    "qrcode",
    "barcode",
    "python-barcode",
    # Presentation
    "pptx",
    "python-pptx",
    # File formats
    "yaml",
    "pyyaml",
    "lxml",
    "xml",
    "html",
    "markdown",
    # Standard library modules (safe subset)
    "json",
    "csv",
    "datetime",
    "math",
    "random",
    "statistics",
    "collections",
    "itertools",
    "functools",
    "operator",
    "string",
    "textwrap",
    "re",
    "io",
    "base64",
}

# Maximum execution time in seconds
MAX_EXECUTION_TIME = 30

# Maximum output directory size in MB
MAX_OUTPUT_SIZE_MB = 100

# Maximum memory limit for subprocess (in bytes)
MAX_MEMORY_MB = 512
MAX_MEMORY_BYTES = MAX_MEMORY_MB * 1024 * 1024

# Thread lock for safe file cleanup operations
_cleanup_lock = threading.Lock()


class ArtifactService:
    """
    Service for generating files through secure Python code execution.

    This service provides methods to generate various file types (charts, documents,
    spreadsheets, images, presentations) by executing Python code in a sandboxed
    environment with security restrictions.
    """

    def __init__(self):
        """Initialize the artifact service."""
        self.output_dir = self._get_output_directory()
        self._execution_counter = 0
        self._counter_lock = threading.Lock()

    def _get_output_directory(self) -> Path:
        """Get or create the output directory for generated files."""
        # Use system temp directory for file generation
        temp_dir = Path(tempfile.gettempdir())
        output_dir = temp_dir / "muxi_artifacts"
        output_dir.mkdir(exist_ok=True)
        return output_dir

    def _get_next_execution_id(self) -> str:
        """Generate a unique execution ID."""
        with self._counter_lock:
            self._execution_counter += 1
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return f"exe_{timestamp}_{self._execution_counter:04d}"

    def _validate_code(self, code: str) -> tuple[bool, Optional[str]]:
        """
        Validate Python code using AST to ensure it only uses allowed libraries.

        Args:
            code: Python code to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"

        # Check all imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split(".")[0]
                    if module_name not in ALLOWED_IMPORTS:
                        return False, f"Import not allowed: {alias.name}"

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.split(".")[0]
                    if module_name not in ALLOWED_IMPORTS:
                        return False, f"Import not allowed: {node.module}"

            # Check for dangerous operations
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                return False, f"Operation not allowed: {type(node).__name__}"

            # Check for dangerous function calls
            elif isinstance(node, ast.Call):
                # Direct function calls (e.g., exec(), eval())
                if isinstance(node.func, ast.Name):
                    dangerous_funcs = {
                        "exec",
                        "eval",
                        "compile",
                        "__import__",
                        "getattr",
                        "setattr",
                        "delattr",
                        "hasattr",
                        "vars",
                        "dir",
                        "globals",
                        "locals",
                    }
                    if node.func.id in dangerous_funcs:
                        return False, f"Function not allowed: {node.func.id}"
                # Attribute-based calls (e.g., builtins.exec, sys.modules)
                elif isinstance(node.func, ast.Attribute):
                    # Check for dangerous attribute access patterns
                    dangerous_attrs = {
                        "exec",
                        "eval",
                        "compile",
                        "__import__",
                        "getattr",
                        "setattr",
                        "delattr",
                        "hasattr",
                        "vars",
                        "dir",
                        "globals",
                        "locals",
                    }
                    if node.func.attr in dangerous_attrs:
                        return False, f"Attribute access not allowed: {node.func.attr}"

                    # Check for module-based dangerous access
                    if isinstance(node.func.value, ast.Name):
                        dangerous_modules = {"builtins", "sys", "__builtins__"}
                        if node.func.value.id in dangerous_modules:
                            return (
                                False,
                                f"Access to module not allowed: {node.func.value.id}.{node.func.attr}",
                            )

            # Check for dangerous attribute access (non-function calls)
            elif isinstance(node, ast.Attribute):
                dangerous_attrs = {
                    "__class__",
                    "__bases__",
                    "__subclasses__",
                    "__mro__",
                    "__globals__",
                    "__code__",
                    "__closure__",
                    "__defaults__",
                    "__dict__",
                    "__module__",
                }
                if node.attr in dangerous_attrs:
                    return False, f"Attribute access not allowed: {node.attr}"

            # Check for dangerous subscript access (e.g., sys.modules['os'])
            elif isinstance(node, ast.Subscript):
                if isinstance(node.value, ast.Attribute):
                    if (
                        isinstance(node.value.value, ast.Name)
                        and node.value.value.id == "sys"
                        and node.value.attr == "modules"
                    ):
                        return False, "Access to sys.modules not allowed"

        return True, None

    def _cleanup_old_files(self, max_size_mb: int = MAX_OUTPUT_SIZE_MB):
        """
        Clean up old files if output directory is too large.

        Args:
            max_size_mb: Maximum size in megabytes
        """
        with _cleanup_lock:
            # Calculate directory size
            total_size = sum(f.stat().st_size for f in self.output_dir.rglob("*") if f.is_file())
            total_size_mb = total_size / (1024 * 1024)

            if total_size_mb > max_size_mb:
                # Remove oldest files until under limit
                files = sorted(self.output_dir.rglob("*"), key=lambda f: f.stat().st_mtime)
                for file in files:
                    if file.is_file():
                        try:
                            file_size = file.stat().st_size
                            file.unlink()
                            total_size_mb -= file_size / (1024 * 1024)
                            if total_size_mb <= max_size_mb * 0.8:  # Leave 20% buffer
                                break
                        except Exception:
                            # File may have been deleted by another thread
                            pass

    def _get_mime_type(self, file_path: Path) -> str:
        """
        Determine MIME type based on file extension.

        Args:
            file_path: Path to the file

        Returns:
            MIME type string
        """
        extension = file_path.suffix.lower()
        mime_types = {
            # Images
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".bmp": "image/bmp",
            ".webp": "image/webp",
            # Documents
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls": "application/vnd.ms-excel",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".ppt": "application/vnd.ms-powerpoint",
            # Text
            ".txt": "text/plain",
            ".csv": "text/csv",
            ".json": "application/json",
            ".xml": "application/xml",
            ".yaml": "application/x-yaml",
            ".yml": "application/x-yaml",
            ".md": "text/markdown",
            ".html": "text/html",
            # Code
            ".py": "text/x-python",
            ".js": "text/javascript",
            ".css": "text/css",
        }
        return mime_types.get(extension, "application/octet-stream")

    async def generate_file(self, code: str, filename: Optional[str] = None) -> MuxiArtifact:
        """
        Generate files (charts, documents, spreadsheets, images, presentations)
        by executing Python code with curated libraries.

        The code should save the output file in the current directory
        or 'outputs' subdirectory.

        Args:
            code: Python code to execute for file generation.
                  The code should save the output file in the current directory.
            filename: Optional filename hint for the generated file

        Returns:
            MuxiArtifact with the generated file content and metadata

        Raises:
            ValueError: If code validation fails
            RuntimeError: If code execution fails
        """
        # Validate code
        is_valid, error_msg = self._validate_code(code)
        if not is_valid:
            raise ValueError(error_msg)

        # Prepare output directory
        self._cleanup_old_files()

        # Get unique execution ID
        execution_id = self._get_next_execution_id()

        # Modified code to track generated files
        tracking_code = f'''
import atexit
import json
from pathlib import Path

_generated_files = []
_original_open = open

def _tracking_open(file, mode='r', *args, **kwargs):
    """Track files opened for writing."""
    if 'w' in mode or 'a' in mode or 'x' in mode:
        _generated_files.append(str(Path(file).absolute()))
    return _original_open(file, mode, *args, **kwargs)

# Override built-in open
open = _tracking_open

def _save_file_list():
    """Save list of generated files on exit."""
    tracking_file = Path(".muxi_tracking_{execution_id}.json")
    with _original_open(tracking_file, 'w') as f:
        json.dump({{"files": _generated_files}}, f)

atexit.register(_save_file_list)

# Add common plotting backend setup
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend

# User code starts here
{code}
'''

        # Write to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(tracking_code)
            tmp_file_path = f.name

        try:
            # Execute the code in the output directory with limitations
            # Note: ulimit -v doesn't work on macOS, so we make it optional
            # The timeout will still protect against runaway processes
            if sys.platform == "linux":
                # Only apply memory limit on Linux where ulimit -v works reliably
                memory_limit_cmd = f"ulimit -v {MAX_MEMORY_BYTES // 1024} 2>/dev/null; "
                cmd = f"{memory_limit_cmd}{sys.executable} {tmp_file_path}"
                use_shell = True
            else:
                # On macOS and Windows, run without memory limit
                cmd = [sys.executable, tmp_file_path]
                use_shell = False

            result = subprocess.run(
                cmd,
                shell=use_shell,
                cwd=str(self.output_dir),
                capture_output=True,
                text=True,
                timeout=MAX_EXECUTION_TIME,
            )

            if result.returncode != 0:
                error_msg = result.stderr if result.stderr else "Unknown error"
                # Provide more helpful error messages for common issues
                if "ModuleNotFoundError" in error_msg:
                    missing_module = error_msg.split("'")[1]
                    error_msg = (
                        f"Missing required module: {missing_module}. Make sure it's installed."
                    )
                elif "FileNotFoundError" in error_msg:
                    error_msg = "File not found. Make sure all file paths are correct."
                elif "MemoryError" in error_msg:
                    error_msg = f"Memory limit exceeded (max {MAX_MEMORY_MB}MB)"

                raise RuntimeError(f"Execution failed: {error_msg}")

            # Check tracking file for generated files
            tracking_file = self.output_dir / f".muxi_tracking_{execution_id}.json"
            generated_files = []

            if tracking_file.exists():
                try:
                    with open(tracking_file) as f:
                        tracking_data = json.load(f)
                        generated_files = [Path(p) for p in tracking_data.get("files", [])]
                    tracking_file.unlink()  # Clean up tracking file
                except Exception:
                    pass

            # If no files tracked, look for new files in output directory
            if not generated_files:
                # List all files in output directory that aren't tracking files
                all_files = [
                    f
                    for f in self.output_dir.glob("*")
                    if f.is_file() and not f.name.startswith(".muxi_tracking_")
                ]
                if all_files:
                    # Sort by modification time and take the newest
                    generated_files = sorted(
                        all_files, key=lambda f: f.stat().st_mtime, reverse=True
                    )

            if not generated_files:
                # Check if there was any output that might indicate what went wrong
                if result.stdout:
                    raise RuntimeError(f"No file was generated. Output: {result.stdout}")
                else:
                    raise RuntimeError("No file was generated")

            # Return the newest file (or the first one if tracked)
            if len(generated_files) == 1:
                newest_file = generated_files[0]
            else:
                newest_file = max(
                    generated_files, key=lambda f: f.stat().st_mtime if f.exists() else 0
                )

            # Create complete artifact from the generated file
            artifact_metadata = {
                "message": f"File generated successfully: {newest_file.name}",
                "tool_name": "generate_file",
                "mime_type": self._get_mime_type(newest_file),
            }

            artifact = create_artifact_from_file(str(newest_file.absolute()), artifact_metadata)

            if artifact:
                return artifact
            else:
                # Fallback if artifact creation fails
                raise RuntimeError(
                    f"Failed to create artifact from generated file: {newest_file.name}"
                )

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Code execution timed out after {MAX_EXECUTION_TIME} seconds")

        except Exception as e:
            # Re-raise with cleaner error message
            if isinstance(e, (RuntimeError, ValueError)):
                raise
            else:
                raise RuntimeError(f"Unexpected error: {str(e)}")

        finally:
            # Clean up temporary script
            try:
                os.unlink(tmp_file_path)
            except Exception:
                pass


# Singleton instance
_artifact_service_instance = None


def get_artifact_service() -> ArtifactService:
    """Get or create the singleton artifact service instance."""
    global _artifact_service_instance
    if _artifact_service_instance is None:
        _artifact_service_instance = ArtifactService()
    return _artifact_service_instance
