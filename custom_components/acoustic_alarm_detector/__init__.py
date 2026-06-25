"""The Acoustic Alarm Detector integration.

A small companion to the Acoustic Alarm Detector add-on. The add-on does the
listening and fires an event on Home Assistant's event bus whenever a detector
turns on or off; this integration turns those events into binary_sensor entities,
grouped under a single device.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType

from .const import DEFAULT_DEVICE_CLASS, DOMAIN, EVENT_TYPE, PLATFORMS

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration (YAML not supported; config entries only)."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Acoustic Alarm Detector from a config entry."""
    _LOGGER.info("Setting up Acoustic Alarm Detector")

    # Shared state for this entry. The binary_sensor platform fills in
    # `add_entities` and `entities`; the event handler below reads/updates them.
    store = {
        "entities": {},          # name -> AcousticAlarmBinarySensor
        "states": {},            # name -> bool (last known, for late-added entities)
        "device_classes": {},    # name -> str
        "add_entities": None,    # AddEntitiesCallback, set by the platform
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = store

    # Create the initial entities (from the add-on's discovery file) before we
    # start handling events.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    @callback
    def _handle_event(event: Event) -> None:
        """Apply an add-on detection event to the matching binary_sensor."""
        name = event.data.get("name")
        if not name:
            return
        state = bool(event.data.get("state", False))
        device_class = event.data.get("device_class") or DEFAULT_DEVICE_CLASS

        store["states"][name] = state
        store["device_classes"][name] = device_class

        entity = store["entities"].get(name)
        if entity is None:
            # A detector we haven't created a sensor for yet — create it now.
            add_entities = store["add_entities"]
            if add_entities is None:
                return
            from .binary_sensor import AcousticAlarmBinarySensor

            entity = AcousticAlarmBinarySensor(entry.entry_id, name, device_class, state)
            store["entities"][name] = entity
            add_entities([entity])
        else:
            entity.update_from_event(state, device_class)

    entry.async_on_unload(hass.bus.async_listen(EVENT_TYPE, _handle_event))

    _LOGGER.info("Listening for '%s' events from the add-on", EVENT_TYPE)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
