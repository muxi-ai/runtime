"""Unit tests for SecretsManager.reload() non-destructive merge semantics."""

import pytest
from cryptography.fernet import InvalidToken

from muxi.runtime.services.secrets.secrets_manager import SecretsManager


@pytest.mark.asyncio
async def test_reload_adds_new_disk_secrets(tmp_path):
    """Secrets present on disk but missing in memory are added to the cache."""
    sm = SecretsManager(tmp_path)
    await sm.initialize_encryption()

    # Initial state on disk: A=1
    await sm.store_secret("A", "1")

    # Simulate external update: write B=2 directly via a sibling manager
    # (same .key file, so encryption is compatible)
    sm2 = SecretsManager(tmp_path)
    await sm2.initialize_encryption()
    await sm2.store_secret("B", "2")

    # First manager doesn't know about B yet
    assert await sm.get_secret("B") is None

    summary = await sm.reload()

    assert "B" in summary["added"]
    assert summary["overwritten"] == []
    assert summary["preserved"] == []
    assert summary["count"] == 2
    assert await sm.get_secret("B") == "2"
    assert await sm.get_secret("A") == "1"


@pytest.mark.asyncio
async def test_reload_overwrites_changed_disk_secrets(tmp_path):
    """Secrets present in both places are overwritten with the disk value."""
    sm = SecretsManager(tmp_path)
    await sm.initialize_encryption()
    await sm.store_secret("A", "old")

    sm2 = SecretsManager(tmp_path)
    await sm2.initialize_encryption()
    await sm2.store_secret("A", "new", overwrite=True)

    # Cache in sm still has old value
    assert await sm.get_secret("A") == "old"

    summary = await sm.reload()

    assert summary["added"] == []
    assert "A" in summary["overwritten"]
    assert summary["preserved"] == []
    assert await sm.get_secret("A") == "new"


@pytest.mark.asyncio
async def test_reload_preserves_in_memory_only_secrets(tmp_path):
    """Secrets only in memory must NOT be deleted on reload."""
    sm = SecretsManager(tmp_path)
    await sm.initialize_encryption()
    await sm.store_secret("DISK_KEY", "disk_value")

    # Inject an in-memory-only secret directly into the cache, bypassing disk
    sm._secrets_cache["MEMORY_ONLY"] = "memory_value"

    summary = await sm.reload()

    # MEMORY_ONLY is not on disk, must be preserved
    assert "MEMORY_ONLY" in summary["preserved"]
    assert await sm.get_secret("MEMORY_ONLY") == "memory_value"
    # DISK_KEY remains accessible
    assert await sm.get_secret("DISK_KEY") == "disk_value"


@pytest.mark.asyncio
async def test_reload_failure_leaves_cache_intact(tmp_path):
    """If decrypting secrets.enc fails, the existing cache must remain untouched."""
    sm = SecretsManager(tmp_path)
    await sm.initialize_encryption()
    await sm.store_secret("A", "1")

    # Corrupt the secrets file
    sm.secrets_file_path.write_bytes(b"not-valid-fernet-payload")

    with pytest.raises(InvalidToken):
        await sm.reload()

    # Cache still intact
    assert await sm.get_secret("A") == "1"


@pytest.mark.asyncio
async def test_reload_with_no_secrets_file(tmp_path):
    """Reload should succeed when secrets.enc does not exist; treat as empty disk."""
    sm = SecretsManager(tmp_path)
    await sm.initialize_encryption()
    sm._secrets_cache["MEMORY_ONLY"] = "v"

    # Ensure no secrets.enc exists
    if sm.secrets_file_path.exists():
        sm.secrets_file_path.unlink()

    summary = await sm.reload()

    assert summary["added"] == []
    assert summary["overwritten"] == []
    assert "MEMORY_ONLY" in summary["preserved"]
    assert await sm.get_secret("MEMORY_ONLY") == "v"
