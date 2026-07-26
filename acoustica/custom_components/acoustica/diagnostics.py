"""Diagnostics support for Acoustica."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, object]:
    """Return non-sensitive runtime diagnostics."""

    store = entry.runtime_data
    return {
        "entry": dict(entry.data),
        "detectors": {
            profile_id: {
                "device_class": runtime.device_class,
                "active": runtime.active,
                "available": runtime.available,
                "removed": runtime.removed,
                "updated_at": runtime.updated_at,
                "last_seen": runtime.last_seen,
                "source_version": runtime.source_version,
            }
            for profile_id, runtime in store["runtimes"].items()
        },
    }
