"""Constants and protocol validation for the Acoustica integration."""

from __future__ import annotations

from typing import Any

DOMAIN = "acoustica"
PLATFORMS = ["binary_sensor"]

EVENT_TYPE = "acoustica_state"
DISCOVERY_SERVICE = "acoustica"
PROTOCOL_VERSION = 1
STATE_STALE_AFTER = 150

DEVICE_ID = "acoustica"
DEVICE_NAME = "Acoustica"
MANUFACTURER = "h0tp / acoustic-engine"
DEFAULT_DEVICE_CLASS = "sound"


def parse_discovery_config(config: dict[str, Any]) -> dict[str, str] | None:
    """Validate Supervisor discovery data and return config-entry data."""

    if config.get("protocol_version") != PROTOCOL_VERSION:
        return None
    detector_id = config.get("detector_id")
    if not isinstance(detector_id, str) or not detector_id.strip():
        return None
    source_version = config.get("source_version")
    if source_version is not None and not isinstance(source_version, str):
        return None
    return {
        "detector_id": detector_id.strip(),
        "source_version": source_version or "unknown",
    }


def parse_state_payload(data: dict[str, Any]) -> dict[str, Any] | None:
    """Validate one add-on state event before it reaches entity state."""

    if data.get("protocol_version") != PROTOCOL_VERSION:
        return None
    if data.get("detector_id") != DEVICE_ID:
        return None

    profile_id = data.get("profile_id")
    device_class = data.get("device_class") or DEFAULT_DEVICE_CLASS
    active = data.get("active")
    updated_at = data.get("updated_at")
    source_version = data.get("source_version")

    if not isinstance(profile_id, str) or not profile_id.strip():
        return None
    if not isinstance(device_class, str) or not device_class.strip():
        return None
    if not isinstance(active, bool):
        return None
    if not isinstance(updated_at, str) or not updated_at:
        return None
    if not isinstance(source_version, str) or not source_version:
        return None

    return {
        "profile_id": profile_id.strip(),
        "device_class": device_class.strip(),
        "active": active,
        "updated_at": updated_at,
        "source_version": source_version,
    }
