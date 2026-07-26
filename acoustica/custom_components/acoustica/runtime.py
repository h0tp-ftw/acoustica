"""Pure runtime state used by Acoustica entities and diagnostics."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DetectorRuntime:
    """Latest validated state for one detector profile."""

    profile_id: str
    device_class: str
    active: bool = False
    available: bool = False
    updated_at: str | None = None
    source_version: str | None = None
    last_seen: str | None = None

    def apply(self, payload: dict[str, object], *, last_seen: str) -> None:
        self.device_class = str(payload["device_class"])
        self.active = bool(payload["active"])
        self.available = True
        self.updated_at = str(payload["updated_at"])
        self.source_version = str(payload["source_version"])
        self.last_seen = last_seen

    def mark_unavailable(self) -> bool:
        """Expire availability and return whether anything changed."""

        if not self.available:
            return False
        self.available = False
        return True
