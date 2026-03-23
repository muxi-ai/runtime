"""Unit tests for the RCE client.

These tests run against the live RCE server at localhost:7891.
Skip if the server is not running.
"""

import base64

import pytest

from muxi.runtime.services.rce.client import (
    ExecResult,
    RCEClient,
    RCEError,
    RCEStatus,
)

# Skip entire module if RCE server is not reachable
try:
    import httpx

    resp = httpx.get("http://localhost:7891/health", timeout=2)
    RCE_AVAILABLE = resp.status_code == 200
except Exception:
    RCE_AVAILABLE = False

pytestmark = pytest.mark.skipif(not RCE_AVAILABLE, reason="RCE server not running on localhost:7891")


@pytest.fixture
async def client():
    c = RCEClient(url="http://localhost:7891")
    await c.connect()
    yield c
    await c.close()


@pytest.fixture
async def authed_client():
    """Client for port 7892 with bearer token."""
    try:
        c = RCEClient(url="http://localhost:7892", token="testing")
        await c.connect()
        yield c
        await c.close()
    except RCEError:
        pytest.skip("Auth RCE server not running on localhost:7892")


@pytest.fixture
def skill_dir(tmp_path):
    """Create a minimal skill directory for upload tests."""
    skill = tmp_path / "test-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: test-skill\ndescription: unit test\n---\n# Test")
    scripts = skill / "scripts"
    scripts.mkdir()
    (scripts / "run.py").write_text('print("skill executed")\nwith open("out.txt","w") as f: f.write("ok")')
    return skill


class TestRCEStatus:
    @pytest.mark.asyncio
    async def test_connect_returns_status(self, client):
        assert client.status is not None
        assert client.status.version == "0.1.0"
        assert "python" in client.languages
        assert client.status.resources.get("cpus", 0) > 0

    @pytest.mark.asyncio
    async def test_connect_fail_fast(self):
        c = RCEClient(url="http://localhost:59999", connect_timeout=2.0)
        with pytest.raises(RCEError, match="unreachable"):
            await c.connect()

    @pytest.mark.asyncio
    async def test_status_has_packages(self, client):
        assert "python" in client.status.packages
        pkg_names = [p["name"] for p in client.status.packages["python"]]
        assert "numpy" in pkg_names or "pandas" in pkg_names


class TestAdHocRun:
    @pytest.mark.asyncio
    async def test_python_hello(self, client):
        result = await client.run("python", "print('hello')")
        assert result.ok
        assert result.stdout.strip() == "hello"
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_javascript(self, client):
        result = await client.run("javascript", "console.log('js')")
        assert result.ok
        assert "js" in result.stdout

    @pytest.mark.asyncio
    async def test_bash(self, client):
        result = await client.run("bash", "echo bash_works")
        assert result.ok
        assert "bash_works" in result.stdout

    @pytest.mark.asyncio
    async def test_error_returns_stderr(self, client):
        result = await client.run("python", "raise ValueError('boom')")
        assert result.status == "error"
        assert result.exit_code != 0
        assert "boom" in result.stderr

    @pytest.mark.asyncio
    async def test_timeout(self, client):
        result = await client.run("python", "import time; time.sleep(10)", timeout=2)
        assert result.status == "timeout"
        assert result.exit_code == -1

    @pytest.mark.asyncio
    async def test_artifacts_returned(self, client):
        code = 'with open("out.txt", "w") as f: f.write("data")\nprint("done")'
        result = await client.run("python", code)
        assert result.ok
        assert len(result.artifacts) == 1
        assert result.artifacts[0]["name"] == "out.txt"
        content = base64.b64decode(result.artifacts[0]["content"]).decode()
        assert content == "data"

    @pytest.mark.asyncio
    async def test_input_files(self, client):
        csv_b64 = base64.b64encode(b"a,b\n1,2").decode()
        code = "print(open('data.csv').read())"
        result = await client.run("python", code, files={"data.csv": csv_b64})
        assert result.ok
        assert "a,b" in result.stdout

    @pytest.mark.asyncio
    async def test_env_vars(self, client):
        code = "import os; print(os.environ['TEST_VAR'])"
        result = await client.run("python", code, env={"TEST_VAR": "hello123"})
        assert result.ok
        assert "hello123" in result.stdout

    @pytest.mark.asyncio
    async def test_unsupported_language(self, client):
        result = await client.run("rust", "fn main() {}")
        assert result.status == "error"
        assert "unsupported" in result.stderr.lower()


class TestSkillLifecycle:
    @pytest.mark.asyncio
    async def test_check_not_cached(self, client):
        status = await client.check_skill("nonexistent-skill-xyz")
        assert status["cached"] is False

    @pytest.mark.asyncio
    async def test_upload_and_check(self, client, skill_dir):
        result = await client.upload_skill_zip(
            "unit-test-skill", skill_dir, "sha256:" + "a" * 64
        )
        assert result["status"] == "cached"
        assert result["file_count"] == 2

        status = await client.check_skill("unit-test-skill")
        assert status["cached"] is True
        assert status["hash"] == "sha256:" + "a" * 64

        # Cleanup
        await client.delete_skill("unit-test-skill")

    @pytest.mark.asyncio
    async def test_ensure_cached_upload_then_noop(self, client, skill_dir):
        h = "sha256:" + "b" * 64
        uploaded = await client.ensure_cached("unit-test-skill-2", skill_dir, h)
        assert uploaded is True

        uploaded2 = await client.ensure_cached("unit-test-skill-2", skill_dir, h)
        assert uploaded2 is False

        await client.delete_skill("unit-test-skill-2")

    @pytest.mark.asyncio
    async def test_ensure_cached_re_uploads_on_hash_change(self, client, skill_dir):
        h1 = "sha256:" + "c" * 64
        await client.ensure_cached("unit-test-skill-3", skill_dir, h1)

        h2 = "sha256:" + "d" * 64
        uploaded = await client.ensure_cached("unit-test-skill-3", skill_dir, h2)
        assert uploaded is True

        status = await client.check_skill("unit-test-skill-3")
        assert status["hash"] == h2

        await client.delete_skill("unit-test-skill-3")

    @pytest.mark.asyncio
    async def test_run_skill(self, client, skill_dir):
        h = "sha256:" + "e" * 64
        await client.ensure_cached("unit-test-skill-4", skill_dir, h)

        result = await client.run_skill("unit-test-skill-4", "python3 scripts/run.py")
        assert result.ok
        assert "skill executed" in result.stdout
        assert len(result.artifacts) == 1
        assert result.artifacts[0]["name"] == "out.txt"

        await client.delete_skill("unit-test-skill-4")

    @pytest.mark.asyncio
    async def test_run_skill_not_cached(self, client):
        with pytest.raises(RCEError) as exc_info:
            await client.run_skill("not-cached-xyz", "echo hi")
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_run_skill_with_input_files(self, client, skill_dir):
        h = "sha256:" + "f" * 64
        await client.ensure_cached("unit-test-skill-5", skill_dir, h)

        # run_skill auto-encodes input_files to base64
        result = await client.run_skill(
            "unit-test-skill-5",
            "python3 reader.py",
            input_files={"data.csv": "x,y\n1,2\n3,4", "reader.py": "print(open('data.csv').read())"},
        )
        assert result.ok
        assert "x,y" in result.stdout

        await client.delete_skill("unit-test-skill-5")

    @pytest.mark.asyncio
    async def test_delete_not_cached(self, client):
        with pytest.raises(RCEError) as exc_info:
            await client.delete_skill("not-cached-delete-xyz")
        assert exc_info.value.status_code == 404


class TestAuth:
    @pytest.mark.asyncio
    async def test_no_token_rejected(self):
        try:
            c = RCEClient(url="http://localhost:7892")
            await c.connect()  # health/status don't need auth
            with pytest.raises(RCEError, match="authorization"):
                await c.run("python", "print(1)")
            await c.close()
        except RCEError:
            pytest.skip("Auth RCE server not running on localhost:7892")

    @pytest.mark.asyncio
    async def test_valid_token_accepted(self, authed_client):
        result = await authed_client.run("python", "print('ok')")
        assert result.ok


class TestDataclasses:
    def test_exec_result_ok_property(self):
        r = ExecResult(id="x", status="success", exit_code=0, stdout="", stderr="", duration_ms=1, artifacts=[])
        assert r.ok is True
        r2 = ExecResult(id="x", status="error", exit_code=1, stdout="", stderr="", duration_ms=1, artifacts=[])
        assert r2.ok is False

    def test_rce_status_from_dict(self):
        s = RCEStatus.from_dict({
            "version": "0.1.0", "languages": ["python"], "runtimes": [],
            "resources": {"cpus": 2}, "packages": {}, "cached_skills": [], "uptime_seconds": 100,
        })
        assert s.version == "0.1.0"
        assert s.languages == ["python"]

    def test_exec_result_from_dict_null_artifacts(self):
        r = ExecResult.from_dict({"id": "x", "status": "success", "exit_code": 0,
                                   "stdout": "", "stderr": "", "duration_ms": 0, "artifacts": None})
        assert r.artifacts == []

    def test_rce_error_has_status_code(self):
        e = RCEError("test", 404)
        assert e.status_code == 404
        assert "test" in str(e)
