"""Binary sensor platform for Acoustica.

One binary_sensor per configured detector, all grouped under a single device.
Entities are created from the add-on's discovery file at setup and, for any
detector not yet seen, on the fly when its first event arrives.
"""

from __future__ import annotations

import json
import logging
import os
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

from .const import (
    DEFAULT_DEVICE_CLASS,
    DEVICE_ID,
    DEVICE_NAME,
    DOMAIN,
    MANUFACTURER,
    PROFILES_PATH,
)

_LOGGER = logging.getLogger(__name__)


def _read_discovery() -> list[dict]:
    """Read the add-on's discovery file (blocking; call via executor)."""
    if not os.path.exists(PROFILES_PATH):
        return []
    try:
        with open(PROFILES_PATH, "r") as f:
            data = json.load(f)
        return data.get("profiles", []) or []
    except (OSError, ValueError) as err:
        _LOGGER.warning("Could not read discovery file %s: %s", PROFILES_PATH, err)
        return []


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors for this entry."""
    store = hass.data[DOMAIN][entry.entry_id]
    store["add_entities"] = async_add_entities

    profiles = await hass.async_add_executor_job(_read_discovery)

    new_entities = []
    for profile in profiles:
        name = profile.get("name")
        if not name or name in store["entities"]:
            continue
        device_class = profile.get("device_class") or DEFAULT_DEVICE_CLASS
        state = bool(store["states"].get(name, False))
        entity = AcousticaBinarySensor(entry.entry_id, name, device_class, state)
        store["entities"][name] = entity
        new_entities.append(entity)

    if new_entities:
        _LOGGER.info("Creating %d binary sensor(s): %s",
                     len(new_entities), ", ".join(e.detector_name for e in new_entities))
        async_add_entities(new_entities)


def _to_device_class(value: str) -> BinarySensorDeviceClass:
    """Map a device_class string to the enum, falling back to SOUND."""
    try:
        return BinarySensorDeviceClass(value)
    except ValueError:
        _LOGGER.debug("Unknown device_class '%s'; using 'sound'.", value)
        return BinarySensorDeviceClass.SOUND


class AcousticaBinarySensor(BinarySensorEntity):
    """A single acoustic detector exposed as a binary sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        entry_id: str,
        name: str,
        device_class: str,
        initial_state: bool = False,
    ) -> None:
        self._entry_id = entry_id
        self._name = name
        self._attr_name = name
        self._attr_is_on = initial_state
        self._attr_unique_id = f"{DOMAIN}_{slugify(name)}"
        self._attr_device_class = _to_device_class(device_class)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, DEVICE_ID)},
            name=DEVICE_NAME,
            manufacturer=MANUFACTURER,
            model="acoustic-engine detector",
        )

    @property
    def detector_name(self) -> str:
        return self._name

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"detector": self._name}

    async def async_added_to_hass(self) -> None:
        """Apply the most recent state once the entity is registered."""
        await super().async_added_to_hass()
        store = self.hass.data.get(DOMAIN, {}).get(self._entry_id)
        if store and self._name in store["states"]:
            self._attr_is_on = bool(store["states"][self._name])
        _LOGGER.debug("Sensor %r added (state=%s)", self._name, self._attr_is_on)

    def update_from_event(self, state: bool, device_class: str) -> None:
        """Update from an add-on event. Safe to call before the entity is added."""
        new_dc = _to_device_class(device_class)
        changed = state != self._attr_is_on or new_dc != self._attr_device_class
        self._attr_is_on = state
        self._attr_device_class = new_dc
        if changed and self.hass is not None:
            self.async_write_ha_state()
