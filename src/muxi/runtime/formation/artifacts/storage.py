"""Storage system for artifacts in MUXI runtime."""

import threading
from typing import Dict, List
from datetime import datetime, timezone, timedelta
from ...utils.id_generator import generate_nanoid
from ...datatypes.artifacts import MuxiArtifact


class StoredArtifact:
    """Container for stored artifact with metadata."""

    def __init__(
        self,
        id: str,
        artifact: MuxiArtifact,
        session_id: str,
        user_id: str,
        timestamp: datetime
    ):
        self.id = id
        self.artifact = artifact
        self.session_id = session_id
        self.user_id = user_id
        self.timestamp = timestamp


# Module-level storage for recent artifacts by session
_recent_artifacts_by_session: Dict[str, List[StoredArtifact]] = {}
_artifacts_lock = threading.Lock()


def store_artifact(session_id: str, artifact: MuxiArtifact, user_id: str = "0") -> str:
    """
    Store an artifact in session storage.

    Args:
        session_id: Session identifier
        artifact: The artifact to store
        user_id: User identifier (defaults to "0")

    Returns:
        The generated artifact ID
    """
    # Generate artifact ID
    artifact_id = f"art_{generate_nanoid(size=12)}"

    # Create stored artifact instance
    stored_artifact = StoredArtifact(
        id=artifact_id,
        artifact=artifact,
        session_id=session_id,
        user_id=user_id,
        timestamp=datetime.now(timezone.utc)
    )

    # Thread-safe access to session storage
    with _artifacts_lock:
        # Initialize session storage if needed
        if session_id not in _recent_artifacts_by_session:
            _recent_artifacts_by_session[session_id] = []

        # Add to session storage
        _recent_artifacts_by_session[session_id].append(stored_artifact)

    return artifact_id


def get_recent_artifacts(session_id: str, max_age_minutes: int = 60) -> List[MuxiArtifact]:
    """
    Get recent artifacts for a session.

    Args:
        session_id: Session identifier
        max_age_minutes: Maximum age of artifacts to return (default 60 minutes)

    Returns:
        List of MuxiArtifact objects (not StoredArtifact)
    """
    # Calculate cutoff time
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)

    # Thread-safe access to session storage
    with _artifacts_lock:
        # Get artifacts for session
        session_artifacts = _recent_artifacts_by_session.get(session_id, [])

        # Filter by age and return just the MuxiArtifact objects
        recent_artifacts = [
            stored.artifact
            for stored in session_artifacts
            if stored.timestamp >= cutoff_time
        ]

    return recent_artifacts


def cleanup_old_artifacts(max_age_minutes: int = 60) -> int:
    """
    Remove artifacts older than max_age across all sessions.

    Args:
        max_age_minutes: Maximum age of artifacts to keep (default 60 minutes)

    Returns:
        Count of removed artifacts
    """
    # Calculate cutoff time
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)

    # Thread-safe cleanup of all sessions
    with _artifacts_lock:
        removed_count = 0
        sessions_to_remove = []

        # Iterate through all sessions
        for session_id, artifacts in _recent_artifacts_by_session.items():
            # Filter out old artifacts
            original_count = len(artifacts)
            artifacts[:] = [a for a in artifacts if a.timestamp >= cutoff_time]
            removed_count += original_count - len(artifacts)

            # Mark empty sessions for removal
            if not artifacts:
                sessions_to_remove.append(session_id)

        # Remove empty session entries
        for session_id in sessions_to_remove:
            del _recent_artifacts_by_session[session_id]

    return removed_count
