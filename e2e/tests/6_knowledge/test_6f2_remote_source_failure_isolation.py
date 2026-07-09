"""
Test 6F2: Remote Knowledge Source Failure Isolation
An unreachable remote source must NOT break formation startup or chat.

Cold-start policy under test (documented in mental-model.md): when a remote
source is unreachable and nothing was ever synced, the formation still
starts; the source contributes zero knowledge and a loud warning is
emitted. Agents keep answering from their remaining (local) sources.
"""

import asyncio
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
from muxi.runtime.formation import Formation  # noqa: E402

FORMATION_DIR = Path(__file__).parent / "formations" / "formation-remote-degraded"
FORMATION_ID = "remote-knowledge-degraded-test"


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
    """Guarantee a cold start: no previously synced content for the source."""
    knowledge_cache = Path.home() / ".muxi" / FORMATION_ID / "cache" / "knowledge"
    if knowledge_cache.exists():
        shutil.rmtree(knowledge_cache, ignore_errors=True)


def test_remote_source_failure_isolation():
    async def run_test():
        try:
            print("\n=== Test 6F2: Remote Knowledge Source Failure Isolation ===")

            ensure_secret_links()
            wipe_remote_mirror()

            # NOTE: nothing listens on the remote source's port (59721).
            print("\nLoading formation with an unreachable remote knowledge source...")
            formation = Formation()
            await formation.load(str(FORMATION_DIR / "formation.yaml"))

            print("Starting overlord (remote sync will fail; startup must survive)...")
            overlord = await formation.start_overlord()
            print("Formation started despite unreachable remote source")

            question = "According to your knowledge, what is the Aurelian Ledger and where is it stored?"  # noqa: E501
            response = await overlord.chat(
                question,
                agent_name="hybrid",
                user_id="test_user",
                session_id="test_session_failure_isolation",
                stream=False,
            )

            print(f"\nUser: {question}")
            if isinstance(response, dict):
                response_text = response.get("response", str(response))
            else:
                response_text = str(response)
            print(f"Hybrid: {response_text}")

            assert response is not None, "No response from hybrid agent"
            assert len(response_text) > 50, "Response too short, likely no knowledge used"
            response_lower = response_text.lower()
            keywords = ["bramblehollow", "keeper of sums", "oak-gall", "oak gall"]
            assert any(k in response_lower for k in keywords), (
                "Response does not contain facts from the local knowledge source: "
                f"{response_text}"
            )
            print("Agent answered from local knowledge despite the failed remote sync")

            # The failed source must have a manifest recording the failure
            mirror_root = Path.home() / ".muxi" / FORMATION_ID / "cache" / "knowledge" / "remote"
            manifests = list(mirror_root.rglob("manifest.json"))
            assert manifests, "Failed sync should still write a manifest"
            manifest_text = manifests[0].read_text(encoding="utf-8")
            assert '"failed"' in manifest_text, f"Manifest should record failure: {manifest_text}"
            print("Manifest recorded the failed sync (degrade state tracked)")

            await formation.stop_overlord()

            print("\nTest 6F2 passed: unreachable remote source did not break startup or chat")
            return True

        except Exception as e:
            print(f"\nTest 6F2 failed: {str(e)}")
            import traceback

            traceback.print_exc()
            return False

    success = asyncio.run(run_test())
    return 0 if success else 1


if __name__ == "__main__":
    import os

    exit_code = test_remote_source_failure_isolation()
    if exit_code == 0:
        print("SUCCESS", flush=True)
    os._exit(exit_code)
