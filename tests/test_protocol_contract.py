from __future__ import annotations

import inspect
import runpy
from pathlib import Path

from detector.integration_client import (
    EVENT_STATE_UPDATE,
    PROTOCOL_VERSION,
    IntegrationClient,
)


def _integration_protocol() -> dict:
    return runpy.run_path(
        str(Path("custom_components/acoustic_alarm_detector/const.py"))
    )


def test_addon_and_integration_protocol_constants_match() -> None:
    protocol = _integration_protocol()

    assert protocol["EVENT_STATE_UPDATE"] == EVENT_STATE_UPDATE
    assert protocol["PROTOCOL_VERSION"] == PROTOCOL_VERSION


def test_stale_timeout_exceeds_two_heartbeat_intervals() -> None:
    protocol = _integration_protocol()
    heartbeat_interval = inspect.signature(IntegrationClient).parameters[
        "heartbeat_interval"
    ].default

    assert protocol["STATE_STALE_AFTER"] > heartbeat_interval * 2


def test_config_entry_identity_is_stable_across_manual_and_hassio_setup() -> None:
    protocol = _integration_protocol()
    unique_id = protocol["entry_unique_id"]

    assert unique_id("hallway_listener", "hallway_alarm") == (
        "hallway_listener_hallway_alarm"
    )


def test_old_integration_entry_migrates_profile_id_without_changing_category() -> None:
    protocol = _integration_protocol()
    migrate = protocol["migrate_entry_data"]

    assert migrate({"device_name": "hallway", "alarm_type": "smoke"}) == {
        "device_name": "hallway",
        "alarm_type": "smoke",
        "profile_id": "smoke",
    }
    assert migrate(
        {
            "device_name": "hallway",
            "alarm_type": "safety",
            "profile_id": "custom_alarm",
        }
    )["profile_id"] == "custom_alarm"


def test_supervisor_discovery_config_maps_to_entry_data() -> None:
    protocol = _integration_protocol()
    parse = protocol["parse_discovery_config"]

    assert parse(
        {
            "protocol_version": PROTOCOL_VERSION,
            "detector_id": "hallway_listener",
            "profile_id": "hallway_alarm",
            "alarm_type": "smoke",
            "source_version": "9.5.0",
        }
    ) == {
        "device_name": "hallway_listener",
        "profile_id": "hallway_alarm",
        "alarm_type": "smoke",
    }
    assert parse({"detector_id": "hallway"}) is None
    assert parse(
        {
            "protocol_version": 999,
            "detector_id": "hallway_listener",
            "profile_id": "hallway_alarm",
            "alarm_type": "smoke",
        }
    ) is None
    assert parse(
        {
            "detector_id": "hallway",
            "profile_id": "alarm",
            "alarm_type": "unknown",
        }
    ) is None


def test_integration_rejects_unrelated_or_unversioned_payloads() -> None:
    protocol = _integration_protocol()
    parse = protocol["parse_state_payload"]
    valid = {
        "protocol_version": PROTOCOL_VERSION,
        "detector_id": "hallway",
        "profile_id": "smoke",
        "alarm_type": "smoke",
        "active": True,
        "updated_at": "2026-07-25T12:00:00+00:00",
        "source_version": "9.5.0",
    }

    assert parse(valid, "hallway", "smoke") == (
        True,
        "2026-07-25T12:00:00+00:00",
        "9.5.0",
    )
    assert parse({**valid, "protocol_version": 999}, "hallway", "smoke") is None
    assert parse({**valid, "detector_id": "kitchen"}, "hallway", "smoke") is None
    assert parse(
        {**valid, "alarm_type": "co"},
        "hallway",
        "smoke",
        "smoke",
    ) is None
    assert parse({**valid, "active": "on"}, "hallway", "smoke") is None
