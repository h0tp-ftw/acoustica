"""Diagnostics for Acoustic Alarm Detector config entries."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import PROTOCOL_VERSION
from .runtime import DetectorRuntime


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return non-sensitive pairing and latest-state diagnostics."""

    runtime: DetectorRuntime = entry.runtime_data
    return {
        "protocol_version": PROTOCOL_VERSION,
        "detector_id": runtime.detector_id,
        "profile_id": runtime.profile_id,
        "alarm_type": runtime.alarm_type,
        "active": runtime.active,
        "available": runtime.available,
        "updated_at": runtime.updated_at,
        "last_seen": runtime.last_seen,
        "source_version": runtime.source_version,
    }
