"""
Test 6F1: Remote HTTP Knowledge Source (Chat Flow)
Verify a formation can declare an http:// knowledge source, sync it at load
time into the local mirror, and answer questions from the synced content.

Fixture: a local stdlib HTTP server (no external infrastructure) serving
the formations/formation-remote-http/remote-content/ directory.
"""

import asyncio
import functools
import shutil
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
from muxi.runtime.formation import Formation  # noqa: E402

FORMATION_DIR = Path(__file__).parent / "formations" / "formation-remote-http"
FORMATION_ID = "remote-knowledge-http-test"
HTTP_PORT = 18931


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
    """Remove cached knowledge state so the sync is exercised cold."""
    knowledge_cache = Path.home() / ".muxi" / FORMATION_ID / "cache" / "knowledge"
    if knowledge_cache.exists():
        shutil.rmtree(knowledge_cache, ignore_errors=True)


def start_http_server():
    handler = functools.partial(
        SimpleHTTPRequestHandler, directory=str(FORMATION_DIR / "remote-content")
    )
    server = ThreadingHTTPServer(("127.0.0.1", HTTP_PORT), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_remote_http_knowledge_source():
    async def run_test():
        server = None
        try:
            print("\n=== Test 6F1: Remote HTTP Knowledge Source (Chat Flow) ===")

            ensure_secret_links()
            wipe_remote_mirror()

            print(f"\nStarting local HTTP fixture server on 127.0.0.1:{HTTP_PORT}...")
            server = start_http_server()

            print("Loading formation with remote http knowledge source...")
            formation = Formation()
            await formation.load(str(FORMATION_DIR / "formation.yaml"))

            print("Starting overlord (syncs the remote source at startup)...")
            overlord = await formation.start_overlord()

            # The sync must have mirrored the served file locally
            mirror_root = Path.home() / ".muxi" / FORMATION_ID / "cache" / "knowledge" / "remote"
            mirrored = list(mirror_root.rglob("zephyria-facts.md"))
            assert mirrored, f"Synced file not found under {mirror_root}"
            print(f"Remote file mirrored locally: {mirrored[0]}")

            manifests = list(mirror_root.rglob("manifest.json"))
            assert manifests, "Sync manifest was not written"
            manifest_text = manifests[0].read_text(encoding="utf-8")
            assert '"success"' in manifest_text, f"Manifest not successful: {manifest_text}"
            print("Sync manifest recorded a successful sync")

            question = "According to your knowledge, what is the Zephyrine Protocol and where is its command center?"  # noqa: E501
            response = await overlord.chat(
                question,
                agent_name="zephyria",
                user_id="test_user",
                session_id="test_session_remote_http",
                stream=False,
            )

            print(f"\nUser: {question}")
            if isinstance(response, dict):
                response_text = response.get("response", str(response))
            else:
                response_text = str(response)
            print(f"Zephyria: {response_text}")

            assert response is not None, "No response from zephyria agent"
            assert len(response_text) > 50, "Response too short, likely no knowledge used"
            response_lower = response_text.lower()
            keywords = ["windmere", "wind-keeper", "wind keeper", "aetherspire"]
            assert any(k in response_lower for k in keywords), (
                "Response does not contain facts from the remote knowledge source: "
                f"{response_text}"
            )
            print("Agent answered using content synced from the remote HTTP source")

            await formation.stop_overlord()

            print("\nTest 6F1 passed: remote http source synced at load and used in chat")
            return True

        except Exception as e:
            print(f"\nTest 6F1 failed: {str(e)}")
            import traceback

            traceback.print_exc()
            return False
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()

    success = asyncio.run(run_test())
    return 0 if success else 1


if __name__ == "__main__":
    import os

    exit_code = test_remote_http_knowledge_source()
    if exit_code == 0:
        print("SUCCESS", flush=True)
    os._exit(exit_code)
