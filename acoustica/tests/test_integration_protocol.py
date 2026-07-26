from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_COMPONENT = Path(__file__).parents[1] / "custom_components" / "acoustica"


def _load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, _COMPONENT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


const = _load_module("acoustica_test_const", "const.py")
runtime_module = _load_module("acoustica_test_runtime", "runtime.py")
PROTOCOL_VERSION = const.PROTOCOL_VERSION
parse_discovery_config = const.parse_discovery_config
parse_state_payload = const.parse_state_payload
DetectorRuntime = runtime_module.DetectorRuntime


def test_discovery_requires_supported_protocol_and_detector_id() -> None:
    assert parse_discovery_config(
        {
            "protocol_version": PROTOCOL_VERSION,
            "detector_id": "acoustica",
            "source_version": "10.4.0",
        }
    ) == {
        "detector_id": "acoustica",
        "source_version": "10.4.0",
    }
    assert parse_discovery_config({"detector_id": "acoustica"}) is None
    assert parse_discovery_config(
        {"protocol_version": 999, "detector_id": "acoustica"}
    ) is None


def test_state_protocol_rejects_unrelated_or_malformed_events() -> None:
    valid = {
        "protocol_version": PROTOCOL_VERSION,
        "detector_id": "acoustica",
        "profile_id": "Smoke Alarm",
        "device_class": "smoke",
        "active": True,
        "removed": False,
        "updated_at": "2026-07-25T12:00:00+00:00",
        "source_version": "10.4.0",
    }
    assert parse_state_payload(valid) == {
        "profile_id": "Smoke Alarm",
        "device_class": "smoke",
        "active": True,
        "removed": False,
        "updated_at": "2026-07-25T12:00:00+00:00",
        "source_version": "10.4.0",
    }
    assert parse_state_payload({**valid, "detector_id": "other"}) is None
    assert parse_state_payload({**valid, "protocol_version": 999}) is None
    assert parse_state_payload({**valid, "active": "on"}) is None
    assert parse_state_payload({**valid, "removed": "yes"}) is None
    assert parse_state_payload({**valid, "profile_id": ""}) is None


def test_runtime_tombstone_is_immediately_unavailable_and_revivable() -> None:
    runtime = DetectorRuntime("Washer", "running")
    runtime.apply(
        {
            "device_class": "running",
            "active": True,
            "removed": True,
            "updated_at": "2026-07-25T12:00:00+00:00",
            "source_version": "10.4.0",
        },
        last_seen="2026-07-25T12:00:01+00:00",
    )
    assert runtime.removed is True
    assert runtime.available is False
    assert runtime.active is False

    runtime.apply(
        {
            "device_class": "running",
            "active": False,
            "removed": False,
            "updated_at": "2026-07-25T12:01:00+00:00",
            "source_version": "10.4.0",
        },
        last_seen="2026-07-25T12:01:01+00:00",
    )
    assert runtime.removed is False
    assert runtime.available is True


def test_runtime_availability_expires_without_changing_alarm_state() -> None:
    runtime = DetectorRuntime("Smoke Alarm", "smoke")
    runtime.apply(
        {
            "device_class": "smoke",
            "active": True,
            "updated_at": "2026-07-25T12:00:00+00:00",
            "source_version": "10.4.0",
        },
        last_seen="2026-07-25T12:00:01+00:00",
    )
    assert runtime.available is True
    assert runtime.active is True

    assert runtime.mark_unavailable() is True
    assert runtime.available is False
    assert runtime.active is True
    assert runtime.mark_unavailable() is False
