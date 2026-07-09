"""
Test 6F3: Remote Archive Knowledge Source (Chat Flow)
Verify a formation can declare an http:// knowledge source with
`extract: true`, download the zip at load time, extract it (with
extract_pattern filtering) into the local mirror, and answer questions
from the extracted content.

Fixture: a local stdlib HTTP server (no external infrastructure) serving
a zip built on the fly from formations/formation-remote-archive/archive-src/.
"""

import asyncio
import functools
import shutil
import sys
import tempfile
import threading
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
from muxi.runtime.formation import Formation  # noqa: E402

FORMATION_DIR = Path(__file__).parent / "formations" / "formation-remote-archive"
FORMATION_ID = "remote-knowledge-archive-test"
HTTP_PORT = 18932


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


def build_archive(webroot: Path) -> Path:
    """Zip archive-src/ into <webroot>/kb/lumen-archive.zip."""
    src_dir = FORMATION_DIR / "archive-src"
    kb_dir = webroot / "kb"
    kb_dir.mkdir(parents=True, exist_ok=True)
    archive_path = kb_dir / "lumen-archive.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in sorted(src_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(src_dir).as_posix())
    return archive_path


def start_http_server(webroot: Path):
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(webroot))
    server = ThreadingHTTPServer(("127.0.0.1", HTTP_PORT), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_remote_archive_knowledge_source():
    async def run_test():
        server = None
        webroot = Path(tempfile.mkdtemp(prefix="muxi-6f3-webroot-"))
        try:
            print("\n=== Test 6F3: Remote Archive Knowledge Source (Chat Flow) ===")

            ensure_secret_links()
            wipe_remote_mirror()

            print("\nBuilding zip fixture and starting local HTTP server...")
            build_archive(webroot)
            server = start_http_server(webroot)

            print("Loading formation with remote archive knowledge source...")
            formation = Formation()
            await formation.load(str(FORMATION_DIR / "formation.yaml"))

            print("Starting overlord (downloads + extracts the archive at startup)...")
            overlord = await formation.start_overlord()

            # The extracted members must be mirrored locally...
            mirror_root = Path.home() / ".muxi" / FORMATION_ID / "cache" / "knowledge" / "remote"
            facts = list(mirror_root.rglob("lumen-facts.md"))
            roster = list(mirror_root.rglob("lamplighter-roster.md"))
            assert facts, f"Extracted file not found under {mirror_root}"
            assert roster, "Nested archive member was not extracted"
            print(f"Archive members extracted into the mirror: {facts[0].parent}")

            # ...the raw archive and pattern-filtered members must not be
            assert not list(mirror_root.rglob("*.zip")), "Raw archive leaked into the mirror"
            assert not list(
                mirror_root.rglob("ignored-notes.txt")
            ), "extract_pattern did not filter .txt member"
            print("Raw archive and non-matching members kept out of the mirror")

            manifests = list(mirror_root.rglob("manifest.json"))
            assert manifests, "Sync manifest was not written"
            manifest_text = manifests[0].read_text(encoding="utf-8")
            assert '"success"' in manifest_text, f"Manifest not successful: {manifest_text}"
            assert '"archive_hash"' in manifest_text, "Manifest missing archive change token"
            print("Sync manifest recorded a successful archive sync")

            question = (
                "According to your knowledge, what is the Lumen Concordat, where is its "
                "seat, and who is the current head lamplighter?"
            )
            response = await overlord.chat(
                question,
                agent_name="archivist",
                user_id="test_user",
                session_id="test_session_remote_archive",
                stream=False,
            )

            print(f"\nUser: {question}")
            if isinstance(response, dict):
                response_text = response.get("response", str(response))
            else:
                response_text = str(response)
            print(f"Archivist: {response_text}")

            assert response is not None, "No response from archivist agent"
            assert len(response_text) > 50, "Response too short, likely no knowledge used"
            response_lower = response_text.lower()
            keywords = ["brightharbor", "prismhall", "lamplighter", "vela orin"]
            assert any(k in response_lower for k in keywords), (
                "Response does not contain facts from the extracted archive: " f"{response_text}"
            )
            print("Agent answered using content extracted from the remote archive")

            await formation.stop_overlord()

            print("\nTest 6F3 passed: remote zip source extracted at load and used in chat")
            return True

        except Exception as e:
            print(f"\nTest 6F3 failed: {str(e)}")
            import traceback

            traceback.print_exc()
            return False
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()
            shutil.rmtree(webroot, ignore_errors=True)

    success = asyncio.run(run_test())
    return 0 if success else 1


if __name__ == "__main__":
    import os

    exit_code = test_remote_archive_knowledge_source()
    if exit_code == 0:
        print("SUCCESS", flush=True)
    os._exit(exit_code)
