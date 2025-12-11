"""
Atomic YAML file operations.

Provides atomic write operations for YAML configuration files, protecting against
partial writes and crashes.

**CRITICAL - CONCURRENCY WARNING:**
The update_yaml function performs read-modify-write and is NOT safe for concurrent
updates to the same file without external locking. Multiple concurrent calls WILL
result in lost updates. Callers MUST implement external locking (e.g., fcntl.flock,
filelock library, or distributed locks) when multiple processes/threads may update
the same file concurrently.
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

import aiofiles
import yaml


class AtomicYAMLError(Exception):
    """Raised when atomic YAML operations fail."""


def _sync_fsync(file_path: str) -> None:
    """
    Synchronously fsync a file.

    Called via run_in_executor to avoid blocking the event loop.
    Opens the file in read mode to get a file descriptor for fsync.

    Args:
        file_path: Path to file to fsync
    """
    # Open in read+write mode to get file descriptor for fsync
    # The file was already written and closed by aiofiles
    with open(file_path, 'r+b') as f:
        f.flush()
        os.fsync(f.fileno())


def _clean_config_for_yaml(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clean configuration for YAML serialization.

    Removes None values and ensures clean output.

    Args:
        config: Configuration dictionary to clean

    Returns:
        Cleaned configuration dictionary
    """
    if not isinstance(config, dict):
        return config

    cleaned = {}
    for key, value in config.items():
        if value is None:
            continue

        if isinstance(value, dict):
            cleaned_dict = _clean_config_for_yaml(value)
            if cleaned_dict:  # Only include non-empty dicts
                cleaned[key] = cleaned_dict
        elif isinstance(value, list):
            # Clean list items recursively
            cleaned_list = []
            for item in value:
                if isinstance(item, dict):
                    cleaned_item = _clean_config_for_yaml(item)
                    if cleaned_item:
                        cleaned_list.append(cleaned_item)
                elif item is not None:
                    cleaned_list.append(item)
            if cleaned_list:  # Only include non-empty lists
                cleaned[key] = cleaned_list
        else:
            cleaned[key] = value

    return cleaned


async def atomic_write_yaml(
    file_path: str | Path,
    data: Dict[str, Any],
    preserve_permissions: bool = True,
    clean: bool = True,
) -> None:
    """
    Atomically write data to a YAML file.

    Uses a temporary file + atomic replace pattern to prevent data corruption
    during writes. This is especially important for critical configuration files.

    **Atomicity Guarantees:**
    - Write to temp file in same directory (ensures same filesystem)
    - Flush and fsync to ensure data is written to disk
    - Use os.replace for atomic replacement (POSIX and Windows)
    - Clean up temp file on error

    **Thread Safety:**
    - This function is async-safe for concurrent calls to different files
    - For concurrent updates to the SAME file, caller must provide external locking

    Args:
        file_path: Path to the YAML file to write
        data: Dictionary to serialize to YAML
        preserve_permissions: If True, preserve original file permissions
        clean: If True, remove None values from data before writing

    Raises:
        AtomicYAMLError: If the write operation fails
        TypeError: If data is not a dictionary
    """
    if not isinstance(data, dict):
        raise TypeError("Data must be a dictionary for YAML serialization")

    file_path = Path(file_path)

    try:
        # Clean data if requested
        if clean:
            data = _clean_config_for_yaml(data)

        # Convert to YAML string
        yaml_content = yaml.safe_dump(
            data,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            indent=2,
        )

        # Create temp file in same directory to ensure same filesystem
        file_dir = file_path.parent
        file_dir.mkdir(parents=True, exist_ok=True)

        temp_fd, temp_path = tempfile.mkstemp(
            suffix=".tmp",
            prefix=f".{file_path.stem}_",
            dir=file_dir,
            text=True,
        )

        try:
            # Close the file descriptor as we'll use aiofiles
            os.close(temp_fd)

            # Write to temporary file
            async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
                await f.write(yaml_content)
                await f.flush()

            # Ensure data is written to disk using executor to avoid blocking
            # aiofiles handles don't have fileno(), so we open synchronously in thread
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,  # Use default ThreadPoolExecutor
                _sync_fsync,
                temp_path
            )

            # Preserve original file permissions if requested
            if preserve_permissions and file_path.exists():
                try:
                    original_stats = os.stat(file_path)
                    os.chmod(temp_path, original_stats.st_mode)
                except (FileNotFoundError, OSError):
                    # Original file doesn't exist or permissions error
                    pass

            # Atomically replace the original file
            # os.replace is atomic on POSIX systems and Windows
            os.replace(temp_path, file_path)

        except Exception:
            # Clean up temp file on error
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    except (OSError, yaml.YAMLError) as e:
        raise AtomicYAMLError(f"Failed to write YAML file {file_path}: {str(e)}") from e


async def update_yaml(
    file_path: str | Path,
    updates: Dict[str, Any],
    preserve_permissions: bool = True,
    deep_merge: bool = True,
) -> None:
    """
    Update a YAML file with partial data using atomic write.

    Reads the existing file, merges updates, and writes atomically.

    **CRITICAL - CONCURRENCY WARNING:**
    This function performs a read-modify-write and is NOT safe for concurrent
    updates to the same file without external locking. Multiple concurrent calls
    will result in lost updates (classic lost-update race condition). Callers MUST
    implement external locking (e.g., fcntl.flock, filelock library, or distributed
    locks) when multiple processes/threads may update the same file.

    **What happens without locking:**
    1. Process A reads file (version 1)
    2. Process B reads file (version 1)
    3. Process A writes update (version 2)
    4. Process B writes update (version 2 - Process A's changes are LOST)

    **Atomic write guarantee:**
    The write itself is atomic (no partial writes), but this does NOT prevent
    lost updates from concurrent readers.

    Args:
        file_path: Path to the YAML file to update
        updates: Dictionary of fields to update
        preserve_permissions: If True, preserve original file permissions
        deep_merge: If True, perform deep merge; if False, shallow merge

    Raises:
        AtomicYAMLError: If the operation fails
        FileNotFoundError: If the file doesn't exist

    Example with proper locking:
        ```python
        from filelock import FileLock

        lock = FileLock("config.yaml.lock")
        with lock:
            await update_yaml("config.afs", {"key": "value"})
        ```
    """
    file_path = Path(file_path)

    try:
        # Read existing content
        # Note: No separate existence check - open() will raise FileNotFoundError if missing
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
            existing_data = yaml.safe_load(content)

        if not isinstance(existing_data, dict):
            raise TypeError(f"YAML file must contain a dictionary, got {type(existing_data).__name__}")

        # Merge updates
        if deep_merge:
            updated_data = _deep_merge(existing_data, updates)
        else:
            updated_data = {**existing_data, **updates}

        # Write atomically
        await atomic_write_yaml(
            file_path,
            updated_data,
            preserve_permissions=preserve_permissions,
            clean=True,
        )

    except FileNotFoundError:
        # Re-raise FileNotFoundError directly (don't wrap in AtomicYAMLError)
        raise
    except (OSError, yaml.YAMLError) as e:
        raise AtomicYAMLError(f"Failed to update YAML file {file_path}: {str(e)}") from e


def _deep_merge(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge two dictionaries.

    Updates override base values. Lists and other types are replaced, not merged.

    Args:
        base: Base dictionary
        updates: Updates to apply

    Returns:
        Merged dictionary
    """
    result = base.copy()

    for key, value in updates.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Recursively merge nested dictionaries
            result[key] = _deep_merge(result[key], value)
        else:
            # Replace value (including lists and primitives)
            result[key] = value

    return result


# Backward compatibility alias (deprecated)
async def atomic_update_yaml(
    file_path: str | Path,
    updates: Dict[str, Any],
    preserve_permissions: bool = True,
    deep_merge: bool = True,
) -> None:
    """
    Deprecated alias for update_yaml. Use update_yaml instead.

    This function is maintained for backward compatibility but will be removed
    in a future version. The name "atomic_update_yaml" is misleading because
    the update operation (read-modify-write) is NOT atomic without external locking.
    """
    import warnings
    warnings.warn(
        "atomic_update_yaml is deprecated and will be removed in a future version. "
        "Use update_yaml instead. Note: This function is NOT safe for concurrent "
        "updates without external locking.",
        DeprecationWarning,
        stacklevel=2
    )
    return await update_yaml(file_path, updates, preserve_permissions, deep_merge)


async def atomic_read_yaml(file_path: str | Path) -> Dict[str, Any]:
    """
    Read a YAML file atomically.

    Args:
        file_path: Path to the YAML file to read

    Returns:
        Parsed YAML data as dictionary

    Raises:
        AtomicYAMLError: If the read operation fails
        FileNotFoundError: If the file doesn't exist
    """
    file_path = Path(file_path)

    try:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
            data = yaml.safe_load(content)

        if not isinstance(data, dict):
            raise TypeError("YAML file must contain a dictionary")
        return data

    except (OSError, yaml.YAMLError) as e:
        raise AtomicYAMLError(f"Failed to read YAML file {file_path}: {e!s}") from e
