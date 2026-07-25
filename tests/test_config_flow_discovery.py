from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from dataclasses import dataclass
from pathlib import Path


class _Schema:
    def __init__(self, value):
        self.value = value


class _Required:
    def __init__(self, key, default=None):
        self.key = key
        self.default = default

    def __hash__(self) -> int:
        return hash((self.key, self.default))


class _ConfigFlow:
    configured_unique_ids: dict[str, dict] = {}
    current_entries: list = []

    def __init_subclass__(cls, *, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.domain = domain

    def __init__(self) -> None:
        self.context: dict = {}
        self.unique_id: str | None = None

    async def async_set_unique_id(self, unique_id: str) -> None:
        self.unique_id = unique_id

    def _abort_if_unique_id_configured(self, *, updates=None) -> None:
        if self.unique_id not in self.configured_unique_ids:
            return
        if updates is not None:
            self.configured_unique_ids[self.unique_id] = dict(updates)
        raise RuntimeError("already_configured")

    def _async_current_entries(self):
        return list(self.current_entries)

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}

    def async_abort(self, *, reason: str):
        return {"type": "abort", "reason": reason}


@dataclass
class _HassioServiceInfo:
    config: dict
    name: str
    slug: str
    uuid: str


def _load_config_flow_module():
    root = Path("custom_components/acoustic_alarm_detector")
    package_name = "acoustic_alarm_config_flow_test"

    package = types.ModuleType(package_name)
    package.__path__ = [str(root)]
    sys.modules[package_name] = package

    const_spec = importlib.util.spec_from_file_location(
        f"{package_name}.const", root / "const.py"
    )
    assert const_spec is not None and const_spec.loader is not None
    const_module = importlib.util.module_from_spec(const_spec)
    sys.modules[const_spec.name] = const_module
    const_spec.loader.exec_module(const_module)

    voluptuous = types.ModuleType("voluptuous")
    voluptuous.All = lambda *values: values
    voluptuous.Strip = object()
    voluptuous.Match = lambda pattern: pattern
    voluptuous.Schema = _Schema
    voluptuous.Required = _Required
    voluptuous.In = lambda values: values
    sys.modules["voluptuous"] = voluptuous

    homeassistant = types.ModuleType("homeassistant")
    config_entries = types.ModuleType("homeassistant.config_entries")
    config_entries.ConfigFlow = _ConfigFlow
    config_entries.ConfigFlowResult = dict
    homeassistant.config_entries = config_entries
    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.config_entries"] = config_entries

    helpers = types.ModuleType("homeassistant.helpers")
    service_info = types.ModuleType("homeassistant.helpers.service_info")
    hassio = types.ModuleType("homeassistant.helpers.service_info.hassio")
    hassio.HassioServiceInfo = _HassioServiceInfo
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.service_info"] = service_info
    sys.modules["homeassistant.helpers.service_info.hassio"] = hassio

    flow_spec = importlib.util.spec_from_file_location(
        f"{package_name}.config_flow", root / "config_flow.py"
    )
    assert flow_spec is not None and flow_spec.loader is not None
    flow_module = importlib.util.module_from_spec(flow_spec)
    sys.modules[flow_spec.name] = flow_module
    flow_spec.loader.exec_module(flow_module)
    return flow_module


def test_hassio_discovery_requires_confirmation_and_creates_entry() -> None:
    module = _load_config_flow_module()
    flow = module.AcousticAlarmDetectorConfigFlow()
    discovery = _HassioServiceInfo(
        config={
            "protocol_version": 1,
            "detector_id": "hallway_listener",
            "profile_id": "hallway_alarm",
            "alarm_type": "smoke",
            "source_version": "9.5.0",
        },
        name="Acoustic Alarm Detector",
        slug="local_alarm_detector_v9",
        uuid="supervisor-discovery-uuid",
    )

    assert module.parse_discovery_config(discovery.config) == {
        "device_name": "hallway_listener",
        "profile_id": "hallway_alarm",
        "alarm_type": "smoke",
    }

    result = asyncio.run(flow.async_step_hassio(discovery))

    assert result["type"] == "form"
    assert result["step_id"] == "hassio_confirm"
    assert flow.unique_id == "hallway_listener_hallway_alarm"
    assert result["description_placeholders"] == {
        "detector": "hallway_listener",
        "profile": "hallway_alarm",
        "alarm_type": "Smoke Alarm",
    }

    confirmed = asyncio.run(flow.async_step_hassio_confirm({}))
    assert confirmed == {
        "type": "create_entry",
        "title": "hallway_listener (hallway_alarm)",
        "data": {
            "device_name": "hallway_listener",
            "profile_id": "hallway_alarm",
            "alarm_type": "smoke",
        },
    }


def test_hassio_discovery_rejects_incomplete_payload() -> None:
    module = _load_config_flow_module()
    flow = module.AcousticAlarmDetectorConfigFlow()
    discovery = _HassioServiceInfo(
        config={"detector_id": "hallway_listener"},
        name="Acoustic Alarm Detector",
        slug="local_alarm_detector_v9",
        uuid="bad-discovery",
    )

    result = asyncio.run(flow.async_step_hassio(discovery))

    assert result == {"type": "abort", "reason": "invalid_discovery"}
