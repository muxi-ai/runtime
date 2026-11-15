#!/usr/bin/env python3
"""
Test 28A5: A bad ``auth:`` value fails the formation load.

The load fails, with an error naming the trigger and the target, for:
1. a script that does not exist;
2. a script that is not executable;
3. a URL with no HTTP response (connection refused);
4. a value that is neither a path nor an http(s) URL.
"""

import asyncio
import os
import shutil
import socket
import sys
import tempfile
from pathlib import Path

from trigger_auth_common import ALLOW, build_formation, unique_formation_id

from muxi.runtime.datatypes.exceptions import ConfigurationValidationError
from muxi.runtime.formation import Formation


def _closed_port_url() -> str:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return f"http://127.0.0.1:{port}/check"


async def _load_error(tag: str, auth_value: str) -> str:
    """Load a formation whose 'stripe' trigger declares auth_value; return the error."""
    tmp = Path(tempfile.mkdtemp(prefix=f"muxi-trigger-auth-28a5-{tag}-"))
    formation_id = unique_formation_id(tag)
    formation_dir = build_formation(
        tmp,
        formation_id,
        triggers={"stripe": f"---\nauth: {auth_value}\n---\nEvent: ${{{{ data.type }}}}"},
        scripts={"noexec.py": (ALLOW, False)},
    )
    try:
        await Formation().load(str(formation_dir))
    except ConfigurationValidationError as e:
        return str(e)
    finally:
        shutil.rmtree(Path.home() / ".muxi" / formation_id, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)
    raise AssertionError(f"{tag}: the formation loaded with auth {auth_value!r}")


async def main():
    print("MUXI Runtime - Test 28A5: A bad auth value fails the load")
    print("=" * 60)

    try:
        url = _closed_port_url()
        cases = [
            ("missing", "./auth/missing.py", "missing.py", "does not exist"),
            ("noexec", "./auth/noexec.py", "noexec.py", "not executable"),
            ("unreachable", url, url, "not reachable"),
            ("invalid", "ftp://example.com/check", "ftp://example.com/check", "neither"),
        ]
        checks = []
        for tag, value, target, reason in cases:
            error = await _load_error(tag, value)
            assert "trigger 'stripe'" in error, f"{tag}: trigger not named: {error}"
            assert target in error, f"{tag}: target not named: {error}"
            assert reason in error, f"{tag}: reason missing: {error}"
            print(f"{tag}: load failed naming the trigger and target")
            checks.append(f"{tag}: {error.split(': ', 1)[-1]}")

        print("\n" + "=" * 40)
        print("\n### Test Result:")
        print("  SUCCESS: every bad auth value fails the load, naming trigger and target")
        for check in checks:
            print(f"  - {check}")
        print("\n" + "=" * 40)
        print("\n### Chat transcript:")
        print("\n(no chat: load-time checks only)")
        print("\nTest 28A5 PASSED")
        return True

    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if success else 1)
