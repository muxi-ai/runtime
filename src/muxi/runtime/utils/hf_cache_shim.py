"""HuggingFace cache layout shim for SIF / bind-mounted flat caches.

Why this exists
---------------
muxi-server pre-populates ``~/.muxi/server/cache`` with a flat, custom layout::

    <cacheDir>/<org>--<repo>/
        config.json
        tokenizer.json
        onnx/
            model.onnx
        ...

That cache is bind-mounted into the SIF at ``/opt/hf-cache``, and the
runtime sets ``HF_HOME=/opt/hf-cache`` in the Dockerfile so embedding
code can find weights offline. The mismatch: ``onellm`` (and every other
HF-using library) calls ``huggingface_hub.hf_hub_download``, which
expects the standard HF Hub cache layout::

    <HF_HUB_CACHE>/
        models--<org>--<repo>/
            refs/
                main          # contains <commit-sha>
            blobs/
                <sha>         # actual file blobs
            snapshots/
                <commit-sha>/
                    config.json -> ../../blobs/<sha>
                    onnx/
                        model.onnx -> ../../../blobs/<sha>
                    ...

Result: ``hf_hub_download`` cannot find the model at the bind-mounted
path, ``HF_HUB_OFFLINE=1`` prevents a network download, and onellm
reports "Repo has no ONNX weights" before falling back to a non-existent
sentence-transformers install.

What this module does
---------------------
Detects the flat layout at startup and projects it into HF Hub layout
via symlinks under ``/tmp/muxi-hf-hub`` (writable inside the SIF, no
host pollution). After projection, ``HF_HOME`` and ``HF_HUB_CACHE`` are
re-pointed at the shim so all downstream HF code sees a layout it
understands.

Idempotent: re-running on an already-shimmed cache is a no-op. Failures
during shim construction are logged and the original env stays in place
so the caller can still produce a clear "model not found" error rather
than a confusing shim-related stack trace.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_SHIM_ROOT = "/tmp/muxi-hf-hub"
SHIM_REVISION = "local"


def _is_flat_layout_dir(name: str) -> bool:
    """Match flat-layout model dirs: ``<org>--<repo>``.

    Excludes the standard HF Hub layout (``models--<org>--<repo>``) and
    metadata directories (``hub/``, ``.locks/``, etc.).
    """
    if name.startswith("models--") or name.startswith("."):
        return False
    if name in ("hub", "blobs", "refs", "snapshots"):
        return False
    return "--" in name


def _has_hub_layout(cache_dir: Path) -> bool:
    """Return True if ``cache_dir`` already contains an HF Hub layout."""
    if (cache_dir / "hub").is_dir():
        return True
    try:
        for entry in cache_dir.iterdir():
            if entry.name.startswith("models--") and entry.is_dir():
                return True
    except OSError:
        return False
    return False


def _project_flat_to_hub(
    flat_dir: Path,
    shim_root: Path,
    revision: str = SHIM_REVISION,
) -> None:
    """Project a single flat-layout model dir into HF Hub layout.

    ``flat_dir`` is e.g. ``/opt/hf-cache/nomic-ai--nomic-embed-text-v1.5``.
    ``shim_root`` is the writable shim cache root (e.g. ``/tmp/muxi-hf-hub``).
    """
    hub_dir = shim_root / f"models--{flat_dir.name}"
    snap_dir = hub_dir / "snapshots" / revision
    refs_dir = hub_dir / "refs"

    snap_dir.mkdir(parents=True, exist_ok=True)
    refs_dir.mkdir(parents=True, exist_ok=True)

    refs_main = refs_dir / "main"
    if not refs_main.exists():
        refs_main.write_text(revision, encoding="utf-8")

    for entry in flat_dir.iterdir():
        target = snap_dir / entry.name
        if target.exists() or target.is_symlink():
            continue
        try:
            os.symlink(entry, target)
        except OSError as exc:
            # Symlinks may fail on filesystems without symlink support
            # (rare, but possible on some bind-mounted volumes). Surface
            # the error so the caller can decide whether to abort.
            logger.warning(
                "hf_cache_shim: symlink failed: %s -> %s (%s)",
                target,
                entry,
                exc,
            )


def setup_hf_cache_shim(
    cache_dir: Optional[str] = None,
    shim_root: str = DEFAULT_SHIM_ROOT,
) -> Optional[str]:
    """Detect and shim a flat-layout HF cache into HF Hub layout.

    Resolves the source cache from ``cache_dir`` if given, otherwise from
    the ``HF_HUB_CACHE`` / ``HF_HOME`` env vars (in that order). Returns
    the shim root path on success, ``None`` if no shimming was needed
    or possible.

    Side effects on success:
      * Creates ``shim_root`` populated with HF Hub-style symlinks.
      * Sets ``HF_HUB_CACHE`` and ``HF_HOME`` env vars to ``shim_root``
        so downstream code (huggingface_hub, transformers) finds the
        shimmed layout.

    Safe to call multiple times; the second call is a no-op once the
    shim env vars are already set.
    """
    source = cache_dir or os.environ.get("HF_HUB_CACHE") or os.environ.get("HF_HOME")
    if not source:
        return None

    cache_path = Path(source)
    if not cache_path.is_dir():
        return None

    # Already-shimmed: HF_HUB_CACHE is the shim root and points elsewhere.
    if str(cache_path) == shim_root:
        return shim_root

    # If the source already has standard HF Hub layout, nothing to do.
    if _has_hub_layout(cache_path):
        return None

    flat_dirs = [
        entry for entry in cache_path.iterdir()
        if entry.is_dir() and _is_flat_layout_dir(entry.name)
    ]
    if not flat_dirs:
        return None

    shim_path = Path(shim_root)
    try:
        shim_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("hf_cache_shim: cannot create %s: %s", shim_path, exc)
        return None

    for flat in flat_dirs:
        try:
            _project_flat_to_hub(flat, shim_path)
        except OSError as exc:
            logger.warning("hf_cache_shim: projection failed for %s: %s", flat, exc)

    # Re-export so downstream HF code sees the shim. Use os.environ
    # directly (not setdefault) — we explicitly want to override the
    # Dockerfile's ENV defaults, since those point at the unshimmed
    # bind-mount path.
    os.environ["HF_HUB_CACHE"] = str(shim_path)
    os.environ["HF_HOME"] = str(shim_path)

    logger.info(
        "hf_cache_shim: projected %d flat-layout models from %s into %s",
        len(flat_dirs),
        cache_path,
        shim_path,
    )
    return str(shim_path)
