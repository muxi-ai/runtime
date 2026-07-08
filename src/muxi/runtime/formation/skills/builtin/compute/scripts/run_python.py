#!/usr/bin/env python3
"""
Compute skill executor for RCE execution.

Runs a self-contained Python file written by the agent (delivered as an
input file into the sandbox working directory), after validating the path
and the import policy. Sandboxing, ulimits, and subprocess isolation are
provided by the Skill RCE service; this script does not duplicate them.

Usage:
    python3 scripts/run_python.py main.py

Exit code mirrors the executed file's exit code. Errors detected before
execution are reported on stderr with a machine-readable prefix:
    PathValidationError: ...
    ImportPolicyViolation: ...
"""

import ast
import subprocess
import sys
from pathlib import Path

ALLOWED_IMPORTS = {
    # Most common (inlined in SKILL.md)
    "json",
    "math",
    "datetime",
    "re",
    "statistics",
    "csv",
    "pandas",
    "numpy",
    # Scientific / data
    "scipy",
    "statsmodels",
    "dateutil",
    # Numbers, time, text
    "decimal",
    "fractions",
    "random",
    "cmath",
    "time",
    "calendar",
    "zoneinfo",
    "collections",
    "itertools",
    "functools",
    "operator",
    "string",
    "textwrap",
    "unicodedata",
    # Encoding / hashing / binary
    "io",
    "base64",
    "hashlib",
    "binascii",
    "struct",
    "uuid",
    # Data structures
    "heapq",
    "bisect",
    "array",
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

EXECUTION_TIMEOUT = 60


def validate_path(raw_path: str) -> tuple:
    """Validate that the target file is a plain file inside the working directory.

    Rejects absolute paths, path traversal components, and symlinks.
    Returns (path or None, error message or None).
    """
    candidate = Path(raw_path)

    if candidate.is_absolute():
        return None, f"absolute paths are not allowed: {raw_path}"
    if ".." in candidate.parts:
        return None, f"path traversal is not allowed: {raw_path}"

    workdir = Path.cwd().resolve()
    full = workdir / candidate

    # Reject symlinks at the target or any intermediate component
    probe = full
    while probe != workdir and probe != probe.parent:
        if probe.is_symlink():
            return None, f"symlinks are not allowed: {raw_path}"
        probe = probe.parent

    if not full.is_file():
        return None, f"file not found: {raw_path}"

    resolved = full.resolve()
    if not resolved.is_relative_to(workdir):
        return None, f"path escapes the working directory: {raw_path}"

    return full, None


def transform_trailing_expression(tree: ast.Module) -> str:
    """Give the file REPL semantics: echo the value of a trailing bare expression.

    Returns transformed source, or an empty string when no transform applies
    (no trailing expression, a docstring, or an explicit print call).
    """
    last = tree.body[-1] if tree.body else None
    if not isinstance(last, ast.Expr):
        return ""
    value = last.value
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return ""
    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == "print"
    ):
        return ""

    assign = ast.parse("_muxi_result = None").body[0]
    assign.value = value
    guard = ast.parse("if _muxi_result is not None:\n    print(_muxi_result)").body[0]
    tree.body[-1:] = [assign, guard]
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def validate_code(code: str) -> tuple:
    """AST-validate imports and dangerous builtins. Returns (ok, error, tree)."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntax error: {e}", None

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split(".")[0]
                if mod not in ALLOWED_IMPORTS:
                    return False, f"import not allowed: {alias.name}", None
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mod = node.module.split(".")[0]
                if mod not in ALLOWED_IMPORTS:
                    return False, f"import not allowed: {node.module}", None
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in DANGEROUS_FUNCS:
                return False, f"function not allowed: {node.func.id}", None
            elif isinstance(node.func, ast.Attribute) and node.func.attr in DANGEROUS_FUNCS:
                return False, f"attribute not allowed: {node.func.attr}", None

    return True, None, tree


def main():
    if len(sys.argv) != 2:
        print("PathValidationError: usage: run_python.py <file>", file=sys.stderr)
        sys.exit(2)

    path, error = validate_path(sys.argv[1])
    if error:
        print(f"PathValidationError: {error}", file=sys.stderr)
        sys.exit(2)

    code = path.read_text(encoding="utf-8")
    if not code.strip():
        print("PathValidationError: file is empty", file=sys.stderr)
        sys.exit(2)

    valid, error, tree = validate_code(code)
    if not valid:
        print(f"ImportPolicyViolation: {error}", file=sys.stderr)
        sys.exit(2)

    # REPL semantics: a trailing bare expression is echoed to stdout
    transformed = transform_trailing_expression(tree)
    exec_path = path
    temp_path = None
    if transformed:
        temp_path = Path("_muxi_exec.py")
        temp_path.write_text(transformed, encoding="utf-8")
        exec_path = temp_path

    try:
        result = subprocess.run(
            [sys.executable, str(exec_path)],
            capture_output=True,
            text=True,
            timeout=EXECUTION_TIMEOUT,
            cwd=str(Path.cwd()),
        )
    except subprocess.TimeoutExpired:
        print(f"Error: execution timed out ({EXECUTION_TIMEOUT}s)", file=sys.stderr)
        sys.exit(1)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
