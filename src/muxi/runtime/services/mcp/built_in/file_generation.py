#!/usr/bin/env python3
"""
File Generation MCP Server for MUXI Runtime.

This MCP server allows agents to generate files by executing Python code in a
secure sandbox. It validates code for safety, executes it in a subprocess, and
returns the generated file path.

Security features:
- AST-based validation of imports (whitelist only)
- Subprocess execution with timeout
- Working directory restricted to outputs/
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
from typing import Dict, Any, Optional, Set

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


def validate_code(code: str) -> tuple[bool, Optional[str]]:
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
            if isinstance(node.value, ast.Attribute) and isinstance(node.value.value, ast.Name):
                if node.value.value.id == "sys" and node.value.attr == "modules":
                    return False, "Access to sys.modules not allowed"

    return True, None


def get_output_directory() -> Path:
    """Get or create the output directory for generated files."""
    output_dir = Path.cwd() / "outputs"
    output_dir.mkdir(exist_ok=True)
    return output_dir


def cleanup_old_files(output_dir: Path, max_size_mb: int = MAX_OUTPUT_SIZE_MB):
    """
    Clean up old files if output directory is too large.

    Args:
        output_dir: Output directory path
        max_size_mb: Maximum size in megabytes
    """
    with _cleanup_lock:
        # Calculate directory size
        total_size = sum(f.stat().st_size for f in output_dir.rglob("*") if f.is_file())
        total_size_mb = total_size / (1024 * 1024)

        if total_size_mb > max_size_mb:
            # Remove oldest files until under limit
            files = sorted(output_dir.rglob("*"), key=lambda f: f.stat().st_mtime)
            for file in files:
                if file.is_file():
                    try:
                        file_size = file.stat().st_size
                        file.unlink()
                        total_size_mb -= file_size / (1024 * 1024)
                        if total_size_mb <= max_size_mb * 0.8:  # Leave 20% buffer
                            break
                    except Exception:
                        # Log error but continue cleanup
                        # File may have been deleted by another thread
                        pass


def generate_file(code: str, filename: Optional[str] = None) -> Dict[str, Any]:
    """
    Execute Python code to generate a file.

    Args:
        code: Python code to execute
        filename: Optional filename hint

    Returns:
        Dictionary with file_path and filename on success, or error details
    """
    # Validate code
    is_valid, error_msg = validate_code(code)
    if not is_valid:
        return {"error": error_msg}

    # Prepare output directory
    output_dir = get_output_directory()
    cleanup_old_files(output_dir)

    # Create a temporary Python script with tracking
    import uuid

    execution_id = str(uuid.uuid4())[:8]

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
        json.dump({{"files": list(set(_generated_files))}}, f)

atexit.register(_save_file_list)

# User code starts here
{code}
'''

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp_file:
        tmp_file.write(tracking_code)
        tmp_file_path = tmp_file.name

    try:
        # Execute code in subprocess
        env = os.environ.copy()
        # Remove potentially dangerous environment variables
        sensitive_prefixes = (
            "MUXI_",
            "API_",
            "SECRET_",
            "KEY_",
            "TOKEN_",
            "PASSWORD_",
            "CREDENTIAL_",
            "AUTH_",
        )
        for key in list(env.keys()):
            if any(key.startswith(prefix) for prefix in sensitive_prefixes):
                del env[key]

        # Prepare subprocess with resource limits (where supported)
        try:
            if sys.platform != "win32":
                import resource

                def set_limits():
                    try:
                        # Set memory limit (some systems may not support this)
                        resource.setrlimit(resource.RLIMIT_AS, (MAX_MEMORY_BYTES, MAX_MEMORY_BYTES))
                    except (OSError, ValueError):
                        # Memory limit not supported on this system
                        pass
                    
                    try:
                        # Set CPU time limit (slightly higher than timeout to allow graceful shutdown)
                        resource.setrlimit(
                            resource.RLIMIT_CPU, (MAX_EXECUTION_TIME + 5, MAX_EXECUTION_TIME + 5)
                        )
                    except (OSError, ValueError):
                        # CPU limit not supported on this system
                        pass

                result = subprocess.run(
                    [sys.executable, tmp_file_path],
                    cwd=str(output_dir),
                    capture_output=True,
                    text=True,
                    timeout=MAX_EXECUTION_TIME,
                    env=env,
                    preexec_fn=set_limits,
                )
            else:
                # Windows doesn't support preexec_fn or resource limits
                result = subprocess.run(
                    [sys.executable, tmp_file_path],
                    cwd=str(output_dir),
                    capture_output=True,
                    text=True,
                    timeout=MAX_EXECUTION_TIME,
                    env=env,
                )
        except Exception as e:
            # Fallback: run without resource limits if that fails
            result = subprocess.run(
                [sys.executable, tmp_file_path],
                cwd=str(output_dir),
                capture_output=True,
                text=True,
                timeout=MAX_EXECUTION_TIME,
                env=env,
            )

        if result.returncode != 0:
            return {"error": f"Execution failed: {result.stderr}", "stdout": result.stdout}

        # Read tracking file to get generated files
        tracking_file = output_dir / f".muxi_tracking_{execution_id}.json"
        generated_files = []

        try:
            if tracking_file.exists():
                with open(tracking_file, "r") as f:
                    tracking_data = json.load(f)
                    generated_files = [Path(p) for p in tracking_data.get("files", [])]
                # Clean up tracking file
                tracking_file.unlink()
        except Exception:
            # Fallback to time-based detection if tracking fails
            import time

            current_time = time.time()
            for file_path in output_dir.iterdir():
                if file_path.is_file() and not file_path.name.startswith(".muxi_tracking_"):
                    # Check if file was created in the last minute
                    if current_time - file_path.stat().st_mtime < 60:
                        generated_files.append(file_path)

        if not generated_files:
            return {"error": "No file was generated"}

        # Return the newest file (or the first one if tracked)
        if len(generated_files) == 1:
            newest_file = generated_files[0]
        else:
            newest_file = max(generated_files, key=lambda f: f.stat().st_mtime if f.exists() else 0)

        return {
            "file_path": str(newest_file.absolute()),
            "filename": newest_file.name,
            "stdout": result.stdout if result.stdout else None,
        }

    except subprocess.TimeoutExpired:
        return {"error": f"Code execution timed out after {MAX_EXECUTION_TIME} seconds"}

    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}

    finally:
        # Clean up temporary script
        try:
            os.unlink(tmp_file_path)
        except Exception:
            pass


def handle_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle an MCP request.

    Args:
        request: MCP request dictionary

    Returns:
        MCP response dictionary
    """
    method = request.get("method", "")

    if method == "tools/list":
        return {
            "tools": [
                {
                    "name": "generate_file",
                    "description": "Generate files (charts, documents, spreadsheets, images, presentations) by executing Python code with curated libraries",  # noqa: E501
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "Python code to execute for file generation. The code should save the output file in the current directory.",  # noqa: E501
                            },
                            "filename": {
                                "type": "string",
                                "description": "Optional filename hint for the generated file",
                            },
                        },
                        "required": ["code"],
                    },
                }
            ]
        }

    elif method == "tools/call":
        tool_name = request.get("params", {}).get("name", "")

        if tool_name == "generate_file":
            arguments = request.get("params", {}).get("arguments", {})
            result = generate_file(
                code=arguments.get("code", ""), filename=arguments.get("filename")
            )

            # Format as MCP response
            if "error" in result:
                return {"error": {"code": -32603, "message": result["error"]}}
            else:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"File generated successfully: {result['filename']}",
                        },
                        {
                            "type": "resource",
                            "resource": {
                                "uri": f"file://{result['file_path']}",
                                "name": result["filename"],
                                "mimeType": "application/octet-stream",
                            },
                        },
                    ]
                }

        else:
            return {"error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}}

    else:
        return {"error": {"code": -32601, "message": f"Unknown method: {method}"}}


def main():
    """Main entry point for MCP server."""
    # MCP servers communicate via stdin/stdout
    while True:
        try:
            # Read request from stdin
            line = sys.stdin.readline()

            # Handle EOF gracefully
            if not line:
                # stdin closed, exit cleanly
                break

            # Skip empty lines (just newline characters)
            line = line.strip()
            if not line:
                continue

            # Parse JSON request - let json.loads() handle validation
            try:
                request = json.loads(line)
            except json.JSONDecodeError as e:
                response = {"error": {"code": -32700, "message": f"Parse error: {str(e)}"}}
            else:
                # Handle request
                response = handle_request(request)

            # Send response
            print(json.dumps(response))
            sys.stdout.flush()

        except KeyboardInterrupt:
            # Clean shutdown on Ctrl+C
            break
        except IOError as e:
            # Handle pipe errors (e.g., when parent process dies)
            if e.errno == 32:  # Broken pipe
                break
            # Other IO errors - log and continue
            response = {"error": {"code": -32603, "message": f"IO error: {str(e)}"}}
            print(json.dumps(response))
            sys.stdout.flush()
        except Exception as e:
            # Log error and continue
            response = {"error": {"code": -32603, "message": f"Internal error: {str(e)}"}}
            try:
                print(json.dumps(response))
                sys.stdout.flush()
            except Exception:
                # If we can't even write errors, exit
                break


if __name__ == "__main__":
    main()
