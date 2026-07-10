"""
Database model for tracked coding delegations.

Persistence exists for restart survival of job records and vendor session
ids -- cross-restart continuation (``continue_job_id``) requires the
session id to outlive the process. Running subprocesses do NOT survive a
runtime restart; on boot, rows stuck in ``running`` are marked
``orphaned`` (honest, scheduler-audit precedent).

The table is created centrally by ``_create_all_database_tables`` during
formation initialization (import registered there); formations without
persistent memory run with in-memory tracking only.
"""

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from ...utils.datetime_utils import utc_now_naive
from ..db import AsyncModelMixin, Base

# Terminal + live job states (PRD):
# running | completed | failed | timed_out | cancelled | orphaned
STATUS_RUNNING = "running"
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


class CodingDelegation(Base, AsyncModelMixin):
    """One tracked coding delegation (fire-and-collect background job)."""

    __tablename__ = "coding_delegations"

    id = Column(String(64), primary_key=True)
    formation_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)  # External user id
    originating_session_id = Column(String(255), nullable=True)
    adapter_name = Column(String(255), nullable=True)  # template name or 'inline'
    vendor_session_id = Column(String(255), nullable=True)
    delegation_dir = Column(Text, nullable=True)
    model = Column(String(255), nullable=True)
    prompt = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default=STATUS_RUNNING, index=True)
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    exit_code = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
    continued_from = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=lambda: utc_now_naive())
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<CodingDelegation(id={self.id!r}, status={self.status!r})>"
