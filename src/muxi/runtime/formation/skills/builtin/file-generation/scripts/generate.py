#!/usr/bin/env python3
"""
File generation script for RCE execution.

Reads user-provided Python code from stdin or a file argument,
validates it against the allowed import whitelist, executes it
in the current directory, and prints the output filename.

Usage:
    echo "import matplotlib..." | python3 scripts/generate.py
    python3 scripts/generate.py code.py
"""

import ast
import subprocess
import sys
from pathlib import Path

ALLOWED_IMPORTS = {
    "pandas",
    "numpy",
    "scipy",
    "statsmodels",
    "matplotlib",
    "seaborn",
    "plotly",
    "bokeh",
    "altair",
    "docx",
    "python-docx",
    "reportlab",
    "fpdf",
    "fpdf2",
    "openpyxl",
    "xlsxwriter",
    "xlrd",
    "xlwt",
    "PIL",
    "Pillow",
    "qrcode",
    "barcode",
    "python-barcode",
    "pptx",
    "python-pptx",
    "yaml",
    "pyyaml",
    "lxml",
    "xml",
    "html",
    "markdown",
    "requests",
    "urllib",
    "http",
    "aiohttp",
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

DANGEROUS_FUNCS = {
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


def validate_code(code: str) -> tuple:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntax error: {e}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split(".")[0]
                if mod not in ALLOWED_IMPORTS:
                    return False, f"Import not allowed: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mod = node.module.split(".")[0]
                if mod not in ALLOWED_IMPORTS:
                    return False, f"Import not allowed: {node.module}"
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in DANGEROUS_FUNCS:
                return False, f"Function not allowed: {node.func.id}"
            elif isinstance(node.func, ast.Attribute) and node.func.attr in DANGEROUS_FUNCS:
                return False, f"Attribute not allowed: {node.func.attr}"

    return True, None


def main():
    if len(sys.argv) > 1:
        code_path = Path(sys.argv[1])
        if not code_path.exists():
            print(f"Error: File not found: {code_path}", file=sys.stderr)
            sys.exit(1)
        code = code_path.read_text()
    else:
        code = sys.stdin.read()

    if not code.strip():
        print("Error: No code provided", file=sys.stderr)
        sys.exit(1)

    valid, error = validate_code(code)
    if not valid:
        print(f"Validation error: {error}", file=sys.stderr)
        sys.exit(1)

    # Prepend matplotlib backend setup
    full_code = "import matplotlib\nmatplotlib.use('Agg')\n" + code

    script_path = Path("_user_code.py")
    script_path.write_text(full_code)

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(Path.cwd()),
        )
        if result.returncode != 0:
            print(f"Execution error: {result.stderr}", file=sys.stderr)
            sys.exit(1)
        if result.stdout:
            print(result.stdout)
    except subprocess.TimeoutExpired:
        print("Error: Execution timed out (60s)", file=sys.stderr)
        sys.exit(1)
    finally:
        script_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
