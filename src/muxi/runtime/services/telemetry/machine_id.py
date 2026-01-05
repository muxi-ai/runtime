"""Deterministic machine identifier for telemetry."""

import uuid

_cached_machine_id: str | None = None


def get_machine_id() -> str:
    """Generate a deterministic UUID from hardware identifiers.

    Uses MAC address as the base, hashed through UUID5 with a namespace
    to create a stable, privacy-preserving identifier. The same machine
    will always generate the same ID, but the MAC address cannot be
    reverse-engineered from the UUID.

    Returns:
        A stable UUID string for this machine.
    """
    global _cached_machine_id
    if _cached_machine_id is None:
        mac = uuid.getnode()  # MAC address as int
        _cached_machine_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"muxi.org:{mac}"))
    return _cached_machine_id
