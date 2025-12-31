"""
Unit tests for audit log timestamp filtering.
"""

import pytest
import tempfile
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

from muxi.runtime.formation.server.audit import AuditLogger


@pytest.mark.asyncio
async def test_audit_log_since_filter_with_timezone_aware_datetime():
    """Test that since filter works correctly with timezone-aware datetimes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock get_user_dir to use temp directory
        with patch("muxi.runtime.formation.server.audit.get_user_dir", return_value=Path(tmpdir)):
            logger = AuditLogger("test_formation")

            # Create test entries with different timestamps
            base_time = datetime(2025, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

            # Entry 1: 2 hours ago
            entry1 = {
                "timestamp": (base_time - timedelta(hours=2)).isoformat(),
                "action": "test.action1",
                "resource_type": "test",
                "resource_id": "1",
            }

            # Entry 2: 1 hour ago
            entry2 = {
                "timestamp": (base_time - timedelta(hours=1)).isoformat(),
                "action": "test.action2",
                "resource_type": "test",
                "resource_id": "2",
            }

            # Entry 3: now
            entry3 = {
                "timestamp": base_time.isoformat(),
                "action": "test.action3",
                "resource_type": "test",
                "resource_id": "3",
            }

            # Write entries to log file
            with open(logger.log_path, "w") as f:
                f.write(json.dumps(entry1) + "\n")
                f.write(json.dumps(entry2) + "\n")
                f.write(json.dumps(entry3) + "\n")

            # Filter entries since 1.5 hours ago
            since = base_time - timedelta(hours=1, minutes=30)
            entries = await logger.get_entries(since=since)

            # Should only get entry2 and entry3
            assert len(entries) == 2
            assert entries[0]["action"] == "test.action3"  # Most recent first
            assert entries[1]["action"] == "test.action2"


@pytest.mark.asyncio
async def test_audit_log_since_filter_with_naive_datetime():
    """Test that since filter works correctly with naive datetimes (assumes UTC)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("muxi.runtime.formation.server.audit.get_user_dir", return_value=Path(tmpdir)):
            logger = AuditLogger("test_formation")

            # Create test entries
            base_time = datetime(2025, 10, 26, 12, 0, 0, tzinfo=timezone.utc)

            entry1 = {
                "timestamp": (base_time - timedelta(hours=1)).isoformat(),
                "action": "test.old",
                "resource_type": "test",
                "resource_id": "1",
            }

            entry2 = {
                "timestamp": (base_time + timedelta(hours=1)).isoformat(),
                "action": "test.new",
                "resource_type": "test",
                "resource_id": "2",
            }

            with open(logger.log_path, "w") as f:
                f.write(json.dumps(entry1) + "\n")
                f.write(json.dumps(entry2) + "\n")

            # Use naive datetime (should be treated as UTC)
            since = datetime(2025, 10, 26, 12, 0, 0)  # Naive
            entries = await logger.get_entries(since=since)

            # Should only get entry2 (after base_time)
            assert len(entries) == 1
            assert entries[0]["action"] == "test.new"


@pytest.mark.asyncio
async def test_audit_log_since_filter_with_different_timezones():
    """Test that since filter correctly converts different timezones to UTC."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("muxi.runtime.formation.server.audit.get_user_dir", return_value=Path(tmpdir)):
            logger = AuditLogger("test_formation")

            # Entry at 12:00 UTC
            entry = {
                "timestamp": datetime(2025, 10, 26, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
                "action": "test.action",
                "resource_type": "test",
                "resource_id": "1",
            }

            with open(logger.log_path, "w") as f:
                f.write(json.dumps(entry) + "\n")

            # Query with timestamp in different timezone (11:00 UTC+01:00 = 10:00 UTC)
            # This should include the entry since 12:00 UTC > 10:00 UTC
            from datetime import timezone as tz
            since = datetime(2025, 10, 26, 11, 0, 0, tzinfo=tz(timedelta(hours=1)))
            entries = await logger.get_entries(since=since)

            assert len(entries) == 1
            assert entries[0]["action"] == "test.action"


@pytest.mark.asyncio
async def test_audit_log_handles_malformed_timestamps():
    """Test that malformed timestamps are excluded rather than causing errors."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("muxi.runtime.formation.server.audit.get_user_dir", return_value=Path(tmpdir)):
            logger = AuditLogger("test_formation")

            # Good entry
            good_entry = {
                "timestamp": datetime(2025, 10, 26, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
                "action": "test.good",
                "resource_type": "test",
                "resource_id": "1",
            }

            # Bad entries
            bad_entry1 = {
                "timestamp": "not-a-timestamp",
                "action": "test.bad1",
                "resource_type": "test",
                "resource_id": "2",
            }

            bad_entry2 = {
                # Missing timestamp
                "action": "test.bad2",
                "resource_type": "test",
                "resource_id": "3",
            }

            with open(logger.log_path, "w") as f:
                f.write(json.dumps(good_entry) + "\n")
                f.write(json.dumps(bad_entry1) + "\n")
                f.write(json.dumps(bad_entry2) + "\n")

            # Filter should handle malformed entries gracefully
            since = datetime(2025, 10, 26, 11, 0, 0, tzinfo=timezone.utc)
            entries = await logger.get_entries(since=since)

            # Should only get the good entry
            assert len(entries) == 1
            assert entries[0]["action"] == "test.good"
