"""
Test 6F4: Manual Remote Knowledge Sync Trigger (Admin API)
Verify the POST /v1/agents/{agent_id}/knowledge/sync endpoint:

1. Triggering a sync when the remote is unchanged reports zero changes.
2. After the remote file changes, the trigger re-syncs the mirror and
   incrementally re-embeds the changed file - the agent can answer from
   the NEW content without a restart.
3. Unknown agents / source ids return 404.

Fixture: a local stdlib HTTP server serving a mutable temp webroot seeded
from formations/formation-manual-sync/remote-content/.
"""

import asyncio
import functools
import shutil
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
from muxi.runtime.formation import Formation  # noqa: E402

FORMATION_DIR = Path(__file__).parent / "formations" / "formation-manual-sync"
FORMATION_ID = "remote-knowledge-manual-sync-test"
HTTP_PORT = 18933
API_BASE = "http://127.0.0.1:8273/v1"
ADMIN_HEADERS = {"X-Muxi-Admin-Key": "test-admin-key-6f4", "Content-Type": "application/json"}

# v2 of the served document. The updated fact sits at the TOP because the
# knowledge search pipeline previews chunk content (~200 chars) into the
# agent context; the point of this test is change detection + re-embed,
# not long-document retrieval.
UPDATED_CONTENT = """# The Emberfall Chronicle

The current head scribe of the Ashbound is Archivist Pyra Senn,
appointed in year 512 of the Ashen Calendar.

The Emberfall Chronicle is the fictional record of the volcanic
city-state of Cindervale, stored in the Basalt Library beneath Mount
Cinder.
"""


class QuietHTTPRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        pass


def ensure_secret_links():
    """Create .key / secrets.enc symlinks if missing (they are gitignored)."""
    assets = Path(__file__).parent.parent.parent / "assets"
    for name in (".key", "secrets.enc"):
        link = FORMATION_DIR / name
        if not link.exists():
            if link.is_symlink():
                link.unlink()
            link.symlink_to(Path("..") / ".." / ".." / ".." / "assets" / name)
        assert (assets / name).exists(), f"e2e/assets/{name} missing"


def wipe_remote_mirror():
    """Remove cached knowledge state so the startup sync is exercised cold."""
    knowledge_cache = Path.home() / ".muxi" / FORMATION_ID / "cache" / "knowledge"
    if knowledge_cache.exists():
        shutil.rmtree(knowledge_cache, ignore_errors=True)


def start_http_server(webroot: Path):
    handler = functools.partial(QuietHTTPRequestHandler, directory=str(webroot))
    server = ThreadingHTTPServer(("127.0.0.1", HTTP_PORT), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


async def trigger_sync(client, agent_id, payload=None):
    return await client.post(
        f"{API_BASE}/agents/{agent_id}/knowledge/sync",
        headers=ADMIN_HEADERS,
        json=payload or {},
    )


def test_manual_sync_trigger():
    async def run_test():
        server = None
        formation = None
        webroot = Path(tempfile.mkdtemp(prefix="muxi-6f4-webroot-"))
        try:
            print("\n=== Test 6F4: Manual Remote Knowledge Sync Trigger (Admin API) ===")

            ensure_secret_links()
            wipe_remote_mirror()

            print("\nSeeding webroot and starting local HTTP fixture server...")
            shutil.copytree(FORMATION_DIR / "remote-content", webroot, dirs_exist_ok=True)
            served_file = webroot / "kb" / "emberfall-chronicle.md"
            server = start_http_server(webroot)

            print("Loading formation and starting overlord + API server...")
            formation = Formation()
            await formation.load(str(FORMATION_DIR / "formation.yaml"))
            await formation.start_overlord()
            await formation.start_server(block=False)
            await asyncio.sleep(2)

            async with httpx.AsyncClient(timeout=60.0) as client:
                # 1. Unchanged remote: sync succeeds with zero changes
                print("\n1. Triggering sync with an unchanged remote...")
                response = await trigger_sync(client, "chronicler")
                assert response.status_code == 200, f"Expected 200, got {response.status_code}"
                data = response.json()["data"]
                assert data["agent_id"] == "chronicler"
                result = data["results"][0]
                assert result["status"] == "success", f"Unexpected result: {result}"
                assert (
                    result["files_added"] == 0 and result["files_modified"] == 0
                ), f"Unchanged remote must not re-download: {result}"
                print("   Unchanged remote reported zero changes")

                # 2. Remote changes -> manual sync updates mirror + embeddings
                print("\n2. Updating the remote file and re-triggering the sync...")
                served_file.write_text(UPDATED_CONTENT, encoding="utf-8")
                response = await trigger_sync(
                    client, "chronicler", {"source_id": "emberfall-chronicle"}
                )
                assert response.status_code == 200, f"Expected 200, got {response.status_code}"
                result = response.json()["data"]["results"][0]
                assert result["status"] == "success", f"Unexpected result: {result}"
                assert result["files_modified"] == 1, f"Change not detected: {result}"
                print("   Changed remote re-synced (1 file modified)")

                mirror_root = (
                    Path.home() / ".muxi" / FORMATION_ID / "cache" / "knowledge" / "remote"
                )
                mirrored = list(mirror_root.rglob("emberfall-chronicle.md"))
                assert mirrored, f"Synced file not found under {mirror_root}"
                assert "Pyra Senn" in mirrored[0].read_text(
                    encoding="utf-8"
                ), "Mirror does not contain the updated content"
                print("   Mirror updated with the new content")

                # 3. The changed file was re-embedded: the agent must know
                # the fact that only exists in the post-startup version.
                print("\n3. Asking the agent about the newly synced fact...")
                overlord = formation._overlord
                question = (
                    "According to your knowledge, who is the current head scribe of "
                    "the Ashbound and when were they appointed?"
                )
                chat_response = await overlord.chat(
                    question,
                    agent_name="chronicler",
                    user_id="test_user",
                    session_id="test_session_manual_sync",
                    stream=False,
                )
                if isinstance(chat_response, dict):
                    response_text = chat_response.get("response", str(chat_response))
                else:
                    response_text = str(chat_response)
                print(f"\nUser: {question}")
                print(f"Chronicler: {response_text}")
                assert "pyra" in response_text.lower() or "senn" in response_text.lower(), (
                    "Agent does not know the re-synced fact (re-embedding failed?): "
                    f"{response_text}"
                )
                print("   Agent answered from the re-synced + re-embedded content")

                # 4. Unknown agent / source id -> 404
                print("\n4. Verifying 404s for unknown agent and source id...")
                response = await trigger_sync(client, "no-such-agent")
                assert response.status_code == 404, f"Expected 404, got {response.status_code}"
                response = await trigger_sync(client, "chronicler", {"source_id": "nope"})
                assert response.status_code == 404, f"Expected 404, got {response.status_code}"
                print("   Unknown agent and source id both return 404")

            print("\nTest 6F4 passed: manual sync trigger re-syncs and re-embeds on demand")
            return True

        except Exception as e:
            print(f"\nTest 6F4 failed: {str(e)}")
            import traceback

            traceback.print_exc()
            return False
        finally:
            if formation is not None:
                try:
                    await formation.stop_overlord()
                except Exception:
                    pass
            if server is not None:
                server.shutdown()
                server.server_close()
            shutil.rmtree(webroot, ignore_errors=True)

    success = asyncio.run(run_test())
    return 0 if success else 1


if __name__ == "__main__":
    import os

    exit_code = test_manual_sync_trigger()
    if exit_code == 0:
        print("SUCCESS", flush=True)
    os._exit(exit_code)
