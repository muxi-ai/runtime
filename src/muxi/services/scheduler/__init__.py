"""
MUXI Scheduler Service

Provides proactive task scheduling capabilities for MUXI formations.
Enables users to schedule recurring AI tasks through natural language.

Key Components:
- SchedulerService: Main orchestration with @multitasking.task worker
- JobManager: Database operations using map/reduce pattern
- PromptRewriter: Natural language to execution prompt transformation
- ScheduleParser: Cron expression parsing with dynamic exclusions

Architecture:
- Map/Reduce Pattern: No next_run_at calculations, pure job selection
- Session-based Execution: Uses f"job_{job.id}" as session_id
- Formation Integration: Leverages existing RequestTracker and webhooks
- Multi-user Support: Isolated scheduling per user with secure execution
"""

from .service import SchedulerService
from .manager import JobManager
from .parser import ScheduleParser
from .rewriter import PromptRewriter
from .models import ScheduledJob

__all__ = [
    "SchedulerService",
    "JobManager",
    "ScheduleParser",
    "PromptRewriter",
    "ScheduledJob"
]
