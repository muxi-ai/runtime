import json
import os
import asyncio
from pathlib import Path
from typing import Dict, Any, List
import aiofiles
from .base import BaseTransport, TransportStatus
from ....utils.user_dirs import get_observability_dir


class FileTransport(BaseTransport):
    """File transport with rotation support."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.file_path = Path(config.get("destination", f"{get_observability_dir()}/muxi.jsonl"))
        self.rotation_config = config.get("rotation", {})
        self.max_size_mb = self.rotation_config.get("max_size_mb", 100)
        self.max_files = self.rotation_config.get("max_files", 10)
        self.current_file = None
        self.write_lock = asyncio.Lock()

    async def initialize(self) -> bool:
        """Initialize file transport and create directories."""
        try:
            # Create directory if it doesn't exist
            self.file_path.parent.mkdir(parents=True, exist_ok=True)

            # Open file for writing
            self.current_file = await aiofiles.open(self.file_path, mode="a", encoding="utf-8")

            self.status = TransportStatus.HEALTHY
            return True

        except Exception as e:
            self.last_error = str(e)
            self.status = TransportStatus.FAILED
            return False

    async def send_event(self, event: Dict[str, Any]) -> bool:
        """Write single event to file."""
        return await self._write_events([event])

    async def send_batch(self, events: List[Dict[str, Any]]) -> bool:
        """Write batch of events to file."""
        return await self._write_events(events)

    async def _write_events(self, events: List[Dict[str, Any]]) -> bool:
        """Write events to file with rotation check."""
        async with self.write_lock:
            try:
                # Check if rotation is needed
                await self._check_rotation()

                # Write events
                for event in events:
                    line = json.dumps(event, separators=(",", ":")) + "\n"
                    await self.current_file.write(line)
                    await self.current_file.flush()

                return True

            except Exception as e:
                self.last_error = str(e)
                self.error_count += 1
                if self.error_count > 3:
                    self.status = TransportStatus.FAILED
                return False

    async def _check_rotation(self) -> None:
        """Check if file rotation is needed."""
        if not self.current_file:
            return

        try:
            # Check file size
            file_size_mb = os.path.getsize(self.file_path) / (1024 * 1024)

            if file_size_mb >= self.max_size_mb:
                await self._rotate_file()
        except Exception:
            # If we can't check size, continue without rotation
            pass

    async def _rotate_file(self) -> None:
        """Rotate log file."""
        try:
            # Close current file
            await self.current_file.close()

            # Rotate existing files
            for i in range(self.max_files - 1, 0, -1):
                old_file = self.file_path.with_suffix(f".{i}.jsonl")
                new_file = self.file_path.with_suffix(f".{i+1}.jsonl")

                if old_file.exists():
                    if i == self.max_files - 1:
                        old_file.unlink()  # Delete oldest file
                    else:
                        old_file.rename(new_file)

            # Rename current file
            rotated_file = self.file_path.with_suffix(".1.jsonl")
            if self.file_path.exists():
                self.file_path.rename(rotated_file)

            # Open new file
            self.current_file = await aiofiles.open(self.file_path, mode="w", encoding="utf-8")

        except Exception as e:
            self.last_error = f"Rotation failed: {e}"
            self.error_count += 1

    async def close(self) -> None:
        """Clean up file resources."""
        if self.current_file:
            try:
                await self.current_file.close()
            except Exception:
                pass
            self.current_file = None
