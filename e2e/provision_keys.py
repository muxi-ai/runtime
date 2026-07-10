#!/usr/bin/env python3
"""
Provision formation ``.key`` symlinks for e2e tests.

Formation directories under ``e2e/tests/`` pair a committed
``secrets.enc`` with a gitignored ``.key`` symlink pointing at the
shared ``e2e/assets/.key``. Fresh checkouts and git worktrees are
missing every ``.key`` symlink; when a test runs without one,
SecretsManager auto-generates a brand-new key that cannot decrypt the
committed ``secrets.enc``, and the test dies with a confusing
``cryptography.fernet.InvalidToken`` / ``InvalidSignature`` error.

This script makes the harness self-provisioning. For every directory
under ``e2e/tests/`` that contains a ``secrets.enc`` or a
``formation.yaml`` it ensures ``.key`` is a relative symlink to
``e2e/assets/.key``:

- missing ``.key``               -> create the symlink
- broken ``.key`` symlink        -> replace with a working relative symlink
- symlink resolving to the key   -> leave as-is
- regular file, same content     -> leave as-is
- regular file, different content:
    - if ``secrets.enc`` is a symlink resolving to the shared
      ``e2e/assets/secrets.enc`` -> stale auto-generated key, replace
    - otherwise                  -> leave alone and warn (the formation
      may legitimately own its key/secrets pair)

The script is idempotent and refuses to touch anything outside
``e2e/tests/``. It runs automatically at the start of
``run_all_tests.py`` and ``run_random_tests.py``; for direct
single-test runs invoke it manually first:

    cd e2e && uv run python provision_keys.py
    cd e2e && uv run python provision_keys.py --self-test
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

E2E_DIR = Path(__file__).resolve().parent
TESTS_DIR = E2E_DIR / "tests"
ASSETS_KEY = E2E_DIR / "assets" / ".key"
ASSETS_SECRETS = E2E_DIR / "assets" / "secrets.enc"

FORMATION_MARKERS = ("secrets.enc", "formation.yaml")


class ProvisionError(RuntimeError):
    """Raised when provisioning cannot proceed safely."""


def _assert_under(path: Path, tests_dir: Path) -> None:
    """Refuse to mutate anything outside the e2e tests tree."""
    parent = path.parent.resolve()
    if not parent.is_relative_to(tests_dir.resolve()):
        raise ProvisionError(f"refusing to touch {path}: outside tests dir {tests_dir}")


def _read_resolved(path: Path) -> Optional[bytes]:
    """Read a file's bytes following symlinks; None if unreadable/broken."""
    try:
        return path.read_bytes()
    except OSError:
        return None


def _replace_with_symlink(key_path: Path, assets_key: Path, tests_dir: Path) -> None:
    """Atomically-ish replace whatever is at key_path with a relative symlink."""
    _assert_under(key_path, tests_dir)
    rel_target = os.path.relpath(assets_key, key_path.parent)
    if key_path.is_symlink() or key_path.exists():
        key_path.unlink()
    key_path.symlink_to(rel_target)


def provision_keys(
    tests_dir: Path = TESTS_DIR,
    assets_key: Path = ASSETS_KEY,
    assets_secrets: Path = ASSETS_SECRETS,
    verbose: bool = True,
) -> Dict[str, List[str]]:
    """
    Ensure every formation dir under tests_dir has a usable .key symlink.

    Returns a stats dict with lists of relative paths per action:
    created, replaced, ok, warnings.
    """
    tests_dir = tests_dir.resolve()
    if not tests_dir.is_dir():
        raise ProvisionError(f"tests dir not found: {tests_dir}")
    if not assets_key.is_file():
        raise ProvisionError(
            f"shared master key not found: {assets_key}\n"
            "Copy e2e/assets/.key from a provisioned checkout of this repo "
            "(it is gitignored and never committed)."
        )

    key_bytes = assets_key.read_bytes()
    shared_secrets_bytes = _read_resolved(assets_secrets)

    # NOTE: a non-zero warnings count does NOT abort the run -- warnings flag
    # formations the provisioner deliberately left alone (e.g. a formation-owned
    # key pair, or a readable symlink pointing at a DIFFERENT checkout's key,
    # which will decrypt with the wrong key). They surface in console output;
    # callers wanting strictness can inspect the returned stats dict.
    stats: Dict[str, List[str]] = {"created": [], "replaced": [], "ok": [], "warnings": []}

    def log(action: str, rel: str, detail: str = "") -> None:
        if verbose:
            suffix = f" ({detail})" if detail else ""
            print(f"[provision_keys] {action}: {rel}{suffix}")

    for dirpath, dirnames, filenames in os.walk(tests_dir):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        if not any(marker in filenames for marker in FORMATION_MARKERS):
            continue

        formation_dir = Path(dirpath)
        key_path = formation_dir / ".key"
        rel = str(key_path.relative_to(tests_dir))

        if not key_path.is_symlink() and not key_path.exists():
            # No .key at all: the common fresh-checkout case.
            _replace_with_symlink(key_path, assets_key, tests_dir)
            stats["created"].append(rel)
            log("created", rel, f"-> {os.readlink(key_path)}")
            continue

        if key_path.is_symlink():
            content = _read_resolved(key_path)
            if content == key_bytes:
                stats["ok"].append(rel)
                continue
            if content is None:
                # Broken symlink (e.g. absolute link into another checkout).
                _replace_with_symlink(key_path, assets_key, tests_dir)
                stats["replaced"].append(rel)
                log("replaced", rel, "broken symlink")
                continue
            msg = f"{rel}: symlink resolves to a different key; left untouched"
            stats["warnings"].append(msg)
            log("warning", msg)
            continue

        # Regular file.
        if key_path.read_bytes() == key_bytes:
            stats["ok"].append(rel)
            continue

        secrets_path = formation_dir / "secrets.enc"
        secrets_bytes = _read_resolved(secrets_path)
        is_shared_secrets = (
            secrets_path.is_symlink()
            and shared_secrets_bytes is not None
            and secrets_bytes == shared_secrets_bytes
        )
        if is_shared_secrets:
            # secrets.enc is the shared one, so a differing regular .key can
            # only be a stale auto-generated key that cannot decrypt it.
            _replace_with_symlink(key_path, assets_key, tests_dir)
            stats["replaced"].append(rel)
            log("replaced", rel, "stale auto-generated key over shared secrets.enc")
            continue

        msg = (
            f"{rel}: regular .key differs from assets/.key but secrets.enc is "
            "not the shared symlinked one; left untouched"
        )
        stats["warnings"].append(msg)
        log("warning", msg)

    if verbose:
        print(
            f"[provision_keys] done: {len(stats['created'])} created, "
            f"{len(stats['replaced'])} replaced, {len(stats['ok'])} ok, "
            f"{len(stats['warnings'])} warnings"
        )
    return stats


def _self_test() -> int:
    """Exercise the provisioning rules in a throwaway sandbox."""
    failures: List[str] = []

    def check(condition: bool, label: str) -> None:
        status = "ok" if condition else "FAIL"
        print(f"  [{status}] {label}")
        if not condition:
            failures.append(label)

    with tempfile.TemporaryDirectory(prefix="provision_keys_selftest_") as tmp:
        root = Path(tmp)
        assets = root / "assets"
        tests = root / "tests"
        assets.mkdir()
        tests.mkdir()

        shared_key = b"SHARED-KEY-BYTES"
        shared_secrets = b"SHARED-SECRETS-BYTES"
        (assets / ".key").write_bytes(shared_key)
        (assets / "secrets.enc").write_bytes(shared_secrets)

        def formation(name: str) -> Path:
            d = tests / name
            d.mkdir()
            return d

        # 1. Missing .key next to a shared secrets.enc symlink.
        f_missing = formation("f_missing")
        (f_missing / "secrets.enc").symlink_to("../../assets/secrets.enc")

        # 2. Already-correct relative symlink.
        f_ok = formation("f_ok")
        (f_ok / "secrets.enc").symlink_to("../../assets/secrets.enc")
        (f_ok / ".key").symlink_to("../../assets/.key")

        # 3. Broken symlink.
        f_broken = formation("f_broken")
        (f_broken / "secrets.enc").symlink_to("../../assets/secrets.enc")
        (f_broken / ".key").symlink_to("/nonexistent/other-checkout/.key")

        # 4. Stale auto-generated regular .key over shared secrets.enc.
        f_stale = formation("f_stale")
        (f_stale / "secrets.enc").symlink_to("../../assets/secrets.enc")
        (f_stale / ".key").write_bytes(b"WRONG-AUTOGENERATED-KEY")

        # 5. Formation that owns its key/secrets pair: never touched.
        f_own = formation("f_own")
        (f_own / "secrets.enc").write_bytes(b"OWN-SECRETS")
        (f_own / ".key").write_bytes(b"OWN-KEY")

        # 6. formation.yaml without secrets.enc still gets a key.
        f_yaml = formation("f_yaml_only")
        (f_yaml / "formation.yaml").write_text("agents: []\n")

        # 7. Non-formation dir is ignored.
        f_other = formation("not_a_formation")
        (f_other / "notes.txt").write_text("nothing to see\n")

        stats = provision_keys(
            tests_dir=tests,
            assets_key=assets / ".key",
            assets_secrets=assets / "secrets.enc",
            verbose=False,
        )

        print("self-test results:")
        check(
            (f_missing / ".key").is_symlink()
            and (f_missing / ".key").read_bytes() == shared_key
            and not os.path.isabs(os.readlink(f_missing / ".key")),
            "missing .key gets a relative symlink to assets/.key",
        )
        check(
            os.readlink(f_ok / ".key") == "../../assets/.key",
            "correct existing symlink is left untouched",
        )
        check(
            (f_broken / ".key").read_bytes() == shared_key
            and not os.path.isabs(os.readlink(f_broken / ".key")),
            "broken symlink is replaced with a relative one",
        )
        check(
            (f_stale / ".key").is_symlink() and (f_stale / ".key").read_bytes() == shared_key,
            "stale auto-generated key over shared secrets.enc is replaced",
        )
        check(
            not (f_own / ".key").is_symlink() and (f_own / ".key").read_bytes() == b"OWN-KEY",
            "formation-owned key/secrets pair is never touched",
        )
        check(
            any("f_own" in w for w in stats["warnings"]),
            "formation-owned differing key is reported as a warning",
        )
        check(
            (f_yaml / ".key").is_symlink() and (f_yaml / ".key").read_bytes() == shared_key,
            "formation.yaml without secrets.enc still gets a key",
        )
        check(
            not (f_other / ".key").exists() and not (f_other / ".key").is_symlink(),
            "non-formation dir is ignored",
        )
        check(
            sorted(stats["created"]) == sorted(["f_missing/.key", "f_yaml_only/.key"])
            and sorted(stats["replaced"]) == sorted(["f_broken/.key", "f_stale/.key"]),
            "stats report exactly the expected mutations",
        )

        # Idempotency: a second run must not change anything.
        stats2 = provision_keys(
            tests_dir=tests,
            assets_key=assets / ".key",
            assets_secrets=assets / "secrets.enc",
            verbose=False,
        )
        check(
            not stats2["created"] and not stats2["replaced"],
            "second run is a no-op (idempotent)",
        )

        # Guard: mutations outside the tests dir must be refused.
        outside = root / "outside"
        outside.mkdir()
        try:
            _replace_with_symlink(outside / ".key", assets / ".key", tests)
            guarded = False
        except ProvisionError:
            guarded = True
        check(guarded, "refuses to touch paths outside tests dir")

    if failures:
        print(f"self-test FAILED: {len(failures)} check(s) failed")
        return 1
    print("self-test passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Provision e2e formation .key symlinks")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the provisioning logic against a temporary sandbox and exit",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="only report errors")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    try:
        provision_keys(verbose=not args.quiet)
    except ProvisionError as exc:
        print(f"[provision_keys] error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
