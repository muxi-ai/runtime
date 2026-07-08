"""Unit tests for the compute skill executor (scripts/run_python.py).

The executor is a standalone script shipped inside the bundled compute skill.
These tests run it exactly the way the RCE sandbox does: as a subprocess with
the working directory set to a scratch dir containing the agent's input file.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

EXECUTOR = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "muxi"
    / "runtime"
    / "formation"
    / "skills"
    / "builtin"
    / "compute"
    / "scripts"
    / "run_python.py"
)


def run_executor(workdir: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(EXECUTOR), *args],
        capture_output=True,
        text=True,
        timeout=90,
        cwd=str(workdir),
    )


@pytest.fixture
def workdir(tmp_path):
    return tmp_path


class TestComputeExecutorSuccess:
    def test_scalar_result(self, workdir):
        (workdir / "main.py").write_text("print(2**16 + 1)\n")
        result = run_executor(workdir, "main.py")
        assert result.returncode == 0
        assert result.stdout.strip() == "65537"

    def test_json_result(self, workdir):
        (workdir / "main.py").write_text(
            "import json\n"
            "import statistics\n"
            "values = [12, 7, 3, 21, 9]\n"
            "print(json.dumps({'stdev': round(statistics.stdev(values), 2)}))\n"
        )
        result = run_executor(workdir, "main.py")
        assert result.returncode == 0
        assert json.loads(result.stdout) == {"stdev": 6.77}

    def test_allowed_stdlib_imports(self, workdir):
        (workdir / "main.py").write_text(
            "import math, datetime, re, csv, decimal, hashlib\n" "print(math.factorial(10))\n"
        )
        result = run_executor(workdir, "main.py")
        assert result.returncode == 0
        assert result.stdout.strip() == "3628800"

    def test_trailing_expression_echoed_repl_style(self, workdir):
        (workdir / "main.py").write_text("import statistics\nstatistics.stdev([12, 7, 3, 21, 9])\n")
        result = run_executor(workdir, "main.py")
        assert result.returncode == 0
        assert result.stdout.strip().startswith("6.76")
        # The transformed helper file is cleaned up, not left as an artifact
        assert not (workdir / "_muxi_exec.py").exists()

    def test_trailing_none_expression_not_echoed(self, workdir):
        (workdir / "main.py").write_text("x = [1, 2]\nx.sort()\n")
        result = run_executor(workdir, "main.py")
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_trailing_print_not_double_echoed(self, workdir):
        (workdir / "main.py").write_text("print(7)\n")
        result = run_executor(workdir, "main.py")
        assert result.returncode == 0
        assert result.stdout.strip() == "7"


class TestComputeExecutorRuntimeErrors:
    def test_runtime_error_surfaces_traceback(self, workdir):
        (workdir / "main.py").write_text("print(1 / 0)\n")
        result = run_executor(workdir, "main.py")
        assert result.returncode != 0
        assert "ZeroDivisionError" in result.stderr
        assert "ImportPolicyViolation" not in result.stderr
        assert "PathValidationError" not in result.stderr

    def test_empty_file_rejected(self, workdir):
        (workdir / "main.py").write_text("   \n")
        result = run_executor(workdir, "main.py")
        assert result.returncode == 2
        assert "PathValidationError" in result.stderr


class TestComputeExecutorImportPolicy:
    def test_disallowed_import_rejected(self, workdir):
        (workdir / "main.py").write_text("import socket\nprint('x')\n")
        result = run_executor(workdir, "main.py")
        assert result.returncode == 2
        assert "ImportPolicyViolation" in result.stderr
        assert "socket" in result.stderr

    def test_disallowed_import_from_rejected(self, workdir):
        (workdir / "main.py").write_text("from os import getcwd\nprint(getcwd())\n")
        result = run_executor(workdir, "main.py")
        assert result.returncode == 2
        assert "ImportPolicyViolation" in result.stderr

    def test_dangerous_builtin_rejected(self, workdir):
        (workdir / "main.py").write_text("eval('1+1')\n")
        result = run_executor(workdir, "main.py")
        assert result.returncode == 2
        assert "ImportPolicyViolation" in result.stderr
        assert "eval" in result.stderr

    def test_dangerous_builtin_via_dunder_call_rejected(self, workdir):
        (workdir / "main.py").write_text("eval.__call__('1+1')\n")
        result = run_executor(workdir, "main.py")
        assert result.returncode == 2
        assert "ImportPolicyViolation" in result.stderr
        assert "eval" in result.stderr

    def test_dangerous_builtin_via_nested_attribute_chain_rejected(self, workdir):
        (workdir / "main.py").write_text("exec.__call__.__call__('x = 1')\n")
        result = run_executor(workdir, "main.py")
        assert result.returncode == 2
        assert "ImportPolicyViolation" in result.stderr
        assert "exec" in result.stderr

    def test_syntax_error_rejected_with_distinct_prefix(self, workdir):
        (workdir / "main.py").write_text("def broken(:\n")
        result = run_executor(workdir, "main.py")
        assert result.returncode == 2
        assert "SyntaxValidationError" in result.stderr
        assert "ImportPolicyViolation" not in result.stderr


class TestComputeExecutorPathValidation:
    def test_path_traversal_rejected(self, workdir):
        outside = workdir.parent / "evil.py"
        outside.write_text("print('escaped')\n")
        result = run_executor(workdir, "../evil.py")
        assert result.returncode == 2
        assert "PathValidationError" in result.stderr
        assert "escaped" not in result.stdout

    def test_absolute_path_rejected(self, workdir):
        target = workdir / "main.py"
        target.write_text("print('abs')\n")
        result = run_executor(workdir, str(target))
        assert result.returncode == 2
        assert "PathValidationError" in result.stderr

    def test_symlink_rejected(self, workdir):
        outside = workdir.parent / "target.py"
        outside.write_text("print('via symlink')\n")
        (workdir / "link.py").symlink_to(outside)
        result = run_executor(workdir, "link.py")
        assert result.returncode == 2
        assert "PathValidationError" in result.stderr
        assert "via symlink" not in result.stdout

    def test_symlinked_directory_rejected(self, workdir):
        outside_dir = workdir.parent / "outside"
        outside_dir.mkdir()
        (outside_dir / "main.py").write_text("print('via dir symlink')\n")
        (workdir / "sub").symlink_to(outside_dir)
        result = run_executor(workdir, "sub/main.py")
        assert result.returncode == 2
        assert "PathValidationError" in result.stderr

    def test_missing_file_rejected(self, workdir):
        result = run_executor(workdir, "missing.py")
        assert result.returncode == 2
        assert "PathValidationError" in result.stderr

    def test_no_argument_rejected(self, workdir):
        result = run_executor(workdir)
        assert result.returncode == 2
        assert "PathValidationError" in result.stderr
