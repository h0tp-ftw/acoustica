"""Binary sensor platform for Acoustica."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import DEVICE_ID, DEVICE_NAME, DOMAIN, MANUFACTURER
from .runtime import DetectorRuntime

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register the callback used when detector events first appear."""

    store = entry.runtime_data
    store["add_entities"] = async_add_entities

    existing = []
    for profile_id, runtime in store["runtimes"].items():
        entity = AcousticaBinarySensor(entry.entry_id, runtime)
        store["entities"][profile_id] = entity
        existing.append(entity)
    if existing:
        async_add_entities(existing)


def _to_device_class(value: str) -> BinarySensorDeviceClass:
    try:
        return BinarySensorDeviceClass(value)
    except ValueError:
        _LOGGER.debug("Unknown device_class '%s'; using sound", value)
        return BinarySensorDeviceClass.SOUND


class AcousticaBinarySensor(BinarySensorEntity):
    """One integration-owned entity backed by validated runtime state."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry_id: str, runtime: DetectorRuntime) -> None:
        self._entry_id = entry_id
        self._runtime = runtime
        self._attr_name = runtime.profile_id
        self._attr_unique_id = f"{DOMAIN}_{slugify(runtime.profile_id)}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, DEVICE_ID)},
            name=DEVICE_NAME,
            manufacturer=MANUFACTURER,
            model="acoustic-engine detector",
        )

    @property
    def is_on(self) -> bool:
        return self._runtime.active

    @property
    def available(self) -> bool:
        return self._runtime.available

    @property
    def device_class(self) -> BinarySensorDeviceClass:
        return _to_device_class(self._runtime.device_class)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "detector": self._runtime.profile_id,
            "last_update": self._runtime.updated_at,
            "last_seen": self._runtime.last_seen,
            "source_version": self._runtime.source_version,
        }
