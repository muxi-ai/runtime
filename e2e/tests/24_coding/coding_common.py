"""
Shared helpers for the 24_coding e2e area (coding-agent delegation).

Every test in this area runs a REAL headless coding agent (claude or
droid) end to end: chat turn -> delegate_coding tool -> tracked
subprocess -> completion re-entry. These helpers keep the six standalone
scripts small without hiding the flow.

NOTE: the filename deliberately matches the runners' skip patterns
("common.py") so it is never collected as a test.
"""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from muxi.runtime.formation import Formation  # noqa: E402

# Real agent runs take minutes; poll generously.
POLL_INTERVAL_SECONDS = 5
DELEGATION_DEADLINE_SECONDS = 600

TEST_USER = "coder-user"
TEST_SESSION = "coding-session-1"


def ensure_local_bin_on_path() -> None:
    """droid installs to ~/.local/bin, which may not be on PATH."""
    local_bin = os.path.expanduser("~/.local/bin")
    if local_bin not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = local_bin + os.pathsep + os.environ.get("PATH", "")


def content_of(response) -> str:
    content = getattr(response, "content", None)
    return content if isinstance(content, str) else str(response)


async def load_formation(formation_dirname: str):
    """Load a formation from this area and start its overlord."""
    formation_path = Path(__file__).parent / formation_dirname
    formation = Formation()
    await formation.load(str(formation_path))
    overlord = await formation.start_overlord()
    if overlord.delegation_service is None:
        raise AssertionError("delegation service was not initialized from the coding block")
    return formation, overlord


async def delegate_via_chat(overlord, task: str) -> tuple:
    """
    One chat turn asking the agent to delegate `task`.

    Returns (reply, job, user): `user` is the id the runtime tracked the
    job under -- single-user formations normalize every caller to "0",
    multi-user ones keep the external id.
    """
    # Snapshot pre-existing job ids: the formation's SQLite persistence
    # carries records across test runs, so the NEW job is the one whose id
    # was not tracked before this turn.
    before = set()
    for candidate in (TEST_USER, "0"):
        for entry in await overlord.delegation_service.list_user_jobs(candidate):
            before.add(entry["id"])

    message = f'Please delegate this coding task: "{task}"'
    print(f"\nUser: {message}")
    response = await overlord.chat(
        message=message,
        user_id=TEST_USER,
        session_id=TEST_SESSION,
        use_async=False,
        stream=False,
    )
    reply = content_of(response)
    print(f"System: {reply[:200]}")

    # The tracked surface is authoritative: the new job must exist for the
    # calling user (this IS the retrievability assertion).
    job = None
    user = TEST_USER
    for candidate in (TEST_USER, "0"):
        for entry in await overlord.delegation_service.list_user_jobs(candidate):
            if entry["id"] not in before:
                job, user = entry, candidate
                break
        if job is not None:
            break
    assert job is not None, "delegate_coding did not create a tracked job for the calling user"
    assert job["kind"] == "coding"
    print(f"Tracked job: {job['id']} status={job['status']} adapter={job['adapter']}")
    return reply, job, user


async def wait_for_completion(overlord, job_id: str, user: str):
    """Poll the tracked job until it reaches a terminal state."""
    service = overlord.delegation_service
    deadline = time.time() + DELEGATION_DEADLINE_SECONDS
    while time.time() < deadline:
        job = service.get_job(job_id, user)
        assert job is not None, f"job {job_id} vanished from the tracked surface"
        if job.status != "running":
            print(f"Job {job_id} reached terminal state: {job.status}")
            return job
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    raise AssertionError(f"job {job_id} did not finish within {DELEGATION_DEADLINE_SECONDS}s")


async def wait_for_reentry(overlord, job_id: str, user: str, timeout: float = 120):
    """Wait for the completion re-entry turn (route_class: delegation)."""
    service = overlord.delegation_service
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = service.get_job(job_id, user)
        if job is not None and job.reentry_at is not None:
            print(f"Completion re-entry recorded at {job.reentry_at.isoformat()}")
            return job
        await asyncio.sleep(2)
    raise AssertionError(f"completion re-entry did not happen for job {job_id}")


def assert_cross_user_isolation(overlord, job_id: str) -> None:
    """Another user's view: the job reads as not found."""
    assert overlord.delegation_service.get_job(job_id, "someone-else") is None
    print("Cross-user lookup correctly reads as not found")


def git(args, cwd=None, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(["git"] + args, cwd=cwd, check=check, capture_output=True, text=True)


def make_bare_remote(base_dir: Path) -> str:
    """A local bare git repo with one seeded commit on main (no network)."""
    bare = base_dir / "remote.git"
    seed = base_dir / "seed"
    git(["init", "--bare", str(bare)])
    seed.mkdir()
    git(["init"], cwd=seed)
    git(["checkout", "-b", "main"], cwd=seed)
    (seed / "notes.txt").write_text("initial notes\n")
    git(["add", "notes.txt"], cwd=seed)
    git(
        [
            "-c",
            "user.name=MUXI E2E",
            "-c",
            "user.email=e2e@muxi.test",
            "commit",
            "-m",
            "seed",
        ],
        cwd=seed,
    )
    git(["remote", "add", "origin", str(bare)], cwd=seed)
    git(["push", "origin", "main"], cwd=seed)
    return f"file://{bare}"


async def teardown(formation) -> None:
    try:
        await formation.stop_overlord()
    except Exception:
        pass
    await asyncio.sleep(1)
