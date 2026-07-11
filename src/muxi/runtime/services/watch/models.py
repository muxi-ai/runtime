"""
Database model for tracked watch jobs (remote async tools).

Persistence exists for restart survival of RECORDS (the /jobs listing
stays honest across restarts); poll loops do NOT survive a runtime
restart -- the watch's GBAC context is request-scoped and never
persisted, so on boot rows stuck in ``watching`` are marked ``orphaned``
(the coding-delegation precedent).

The table is created centrally by ``_create_all_database_tables`` during
formation initialization (import registered there); formations without
persistent memory run with in-memory tracking only.
"""

from sqlalchemy import Column, DateTime, Integer, String, Text

from ...utils.datetime_utils import utc_now_naive
from ..db import AsyncModelMixin, Base

# Live + terminal watch states (PRD):
# watching | completed | failed | timed_out | cancelled | orphaned
STATUS_WATCHING = "watching"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_TIMED_OUT = "timed_out"
STATUS_CANCELLED = "cancelled"
STATUS_ORPHANED = "orphaned"

TERMINAL_STATUSES = (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_TIMED_OUT,
    STATUS_CANCELLED,
    STATUS_ORPHANED,
)


class WatchJobRecord(Base, AsyncModelMixin):
    """One tracked watch job (poll loop over an MCP tool)."""

    __tablename__ = "watch_jobs"

    id = Column(String(64), primary_key=True)
    formation_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)  # External user id
    originating_session_id = Column(String(255), nullable=True)
    agent_id = Column(String(255), nullable=True)
    server_id = Column(String(255), nullable=False)
    tool_name = Column(String(255), nullable=False)
    args = Column(Text, nullable=True)  # JSON-encoded poll arguments
    done_when = Column(Text, nullable=True)  # JSON-encoded terminal condition
    result_selector = Column(String(512), nullable=True)
    label = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default=STATUS_WATCHING, index=True)
    polls = Column(Integer, nullable=False, default=0)
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: utc_now_naive())
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<WatchJobRecord(id={self.id!r}, status={self.status!r})>"
