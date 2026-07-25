"""Constants and pure protocol validation for Acoustic Alarm Detector."""

from __future__ import annotations

from typing import Any

DOMAIN = "acoustic_alarm_detector"
VERSION = "9.5.0"
PLATFORMS = ["binary_sensor"]

CONF_ALARM_TYPE = "alarm_type"
CONF_DEVICE_NAME = "device_name"
CONF_PROFILE_ID = "profile_id"

ALARM_TYPE_SMOKE = "smoke"
ALARM_TYPE_CO = "co"
ALARM_TYPE_SAFETY = "safety"
ALARM_TYPES = {
    ALARM_TYPE_SMOKE: "Smoke Alarm",
    ALARM_TYPE_CO: "CO Alarm",
    ALARM_TYPE_SAFETY: "Safety Alarm",
}
DEFAULT_DEVICE_NAME = "smoke_alarm_detector"
DEFAULT_ALARM_TYPE = ALARM_TYPE_SMOKE
DEFAULT_PROFILE_ID = ALARM_TYPE_SMOKE

EVENT_STATE_UPDATE = "acoustic_alarm_detector_state"
SIGNAL_STATE_UPDATED = f"{DOMAIN}_state_updated_{{entry_id}}"
PROTOCOL_VERSION = 1
STATE_STALE_AFTER = 150.0

ATTR_PROTOCOL_VERSION = "protocol_version"
ATTR_DETECTOR_ID = "detector_id"
ATTR_PROFILE_ID = "profile_id"
ATTR_ALARM_TYPE = "alarm_type"
ATTR_ACTIVE = "active"
ATTR_UPDATED_AT = "updated_at"
ATTR_SOURCE_VERSION = "source_version"

DISCOVERY_DETECTOR_ID = "detector_id"
DISCOVERY_PROFILE_ID = "profile_id"
DISCOVERY_ALARM_TYPE = "alarm_type"


def parse_discovery_config(config: dict[str, Any]) -> dict[str, str] | None:
    """Convert validated Supervisor discovery data into config-entry data."""

    if config.get(ATTR_PROTOCOL_VERSION) != PROTOCOL_VERSION:
        return None

    detector_id = config.get(DISCOVERY_DETECTOR_ID)
    profile_id = config.get(DISCOVERY_PROFILE_ID)
    alarm_type = config.get(DISCOVERY_ALARM_TYPE)
    if not isinstance(detector_id, str) or not detector_id.strip():
        return None
    if not isinstance(profile_id, str) or not profile_id.strip():
        return None
    if alarm_type not in ALARM_TYPES:
        return None

    return {
        CONF_DEVICE_NAME: detector_id.strip(),
        CONF_PROFILE_ID: profile_id.strip(),
        CONF_ALARM_TYPE: alarm_type,
    }


def entry_unique_id(detector_id: str, profile_id: str) -> str:
    """Return the stable config-entry identity shared by all setup paths."""

    return f"{detector_id}_{profile_id}"


def migrate_entry_data(data: dict[str, Any]) -> dict[str, Any]:
    """Add the explicit profile ID introduced in config-entry minor version 2."""

    migrated = dict(data)
    migrated.setdefault(
        CONF_PROFILE_ID,
        migrated.get(CONF_ALARM_TYPE, DEFAULT_PROFILE_ID),
    )
    return migrated


def parse_state_payload(
    data: dict[str, Any],
    detector_id: str,
    profile_id: str,
    alarm_type: str | None = None,
) -> tuple[bool, str | None, str | None] | None:
    """Validate one matching add-on payload without Home Assistant dependencies."""

    if data.get(ATTR_PROTOCOL_VERSION) != PROTOCOL_VERSION:
        return None
    if data.get(ATTR_DETECTOR_ID) != detector_id:
        return None
    if data.get(ATTR_PROFILE_ID) != profile_id:
        return None
    event_alarm_type = data.get(ATTR_ALARM_TYPE)
    if alarm_type is not None and event_alarm_type not in {None, alarm_type}:
        return None

    active = data.get(ATTR_ACTIVE)
    if not isinstance(active, bool):
        return None

    updated_at = data.get(ATTR_UPDATED_AT)
    source_version = data.get(ATTR_SOURCE_VERSION)
    return (
        active,
        updated_at if isinstance(updated_at, str) else None,
        source_version if isinstance(source_version, str) else None,
    )
