"""Runtime state for one configured acoustic detector profile."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .const import parse_state_payload


@dataclass(slots=True)
class DetectorRuntime:
    """Latest valid state received from the add-on for one entity."""

    detector_id: str
    profile_id: str
    alarm_type: str
    active: bool = False
    available: bool = False
    updated_at: str | None = None
    source_version: str | None = None
    last_seen: str | None = None

    def apply_event(self, data: dict[str, Any]) -> bool:
        """Apply one matching, protocol-valid event."""

        parsed = parse_state_payload(
            data,
            self.detector_id,
            self.profile_id,
            self.alarm_type,
        )
        if parsed is None:
            return False

        self.active, self.updated_at, self.source_version = parsed
        self.available = True
        return True

    def mark_unavailable(self) -> bool:
        """Mark the add-on unavailable and report whether state changed."""

        if not self.available:
            return False
        self.available = False
        return True
