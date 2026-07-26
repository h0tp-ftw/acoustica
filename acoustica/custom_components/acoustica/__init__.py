"""The Acoustica integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, EVENT_TYPE, PLATFORMS, STATE_STALE_AFTER, parse_state_payload
from .runtime import DetectorRuntime

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration namespace."""

    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one integration entry and its event subscription."""

    store: dict[str, Any] = {
        "entities": {},
        "runtimes": {},
        "add_entities": None,
        "stale_timers": {},
    }
    entry.runtime_data = store
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = store

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    @callback
    def _cancel_timer(profile_id: str) -> None:
        cancel = store["stale_timers"].pop(profile_id, None)
        if cancel is not None:
            cancel()

    @callback
    def _mark_stale(profile_id: str, _now) -> None:
        store["stale_timers"].pop(profile_id, None)
        runtime = store["runtimes"].get(profile_id)
        if runtime is None or not runtime.mark_unavailable():
            return
        entity = store["entities"].get(profile_id)
        if entity is not None:
            entity.async_write_ha_state()
        _LOGGER.warning("No Acoustica heartbeat received for %s", profile_id)

    @callback
    def _handle_event(event: Event) -> None:
        payload = parse_state_payload(dict(event.data))
        if payload is None:
            return

        profile_id = payload["profile_id"]
        runtime = store["runtimes"].get(profile_id)
        if runtime is None:
            runtime = DetectorRuntime(
                profile_id=profile_id,
                device_class=payload["device_class"],
            )
            store["runtimes"][profile_id] = runtime

        runtime.apply(payload, last_seen=event.time_fired.isoformat())
        _cancel_timer(profile_id)
        if not runtime.removed:
            store["stale_timers"][profile_id] = async_call_later(
                hass,
                STATE_STALE_AFTER,
                lambda now, pid=profile_id: _mark_stale(pid, now),
            )

        entity = store["entities"].get(profile_id)
        if entity is None:
            if runtime.removed:
                return
            add_entities = store["add_entities"]
            if add_entities is None:
                return
            from .binary_sensor import AcousticaBinarySensor

            entity = AcousticaBinarySensor(entry.entry_id, runtime)
            store["entities"][profile_id] = entity
            add_entities([entity])
        else:
            entity.async_write_ha_state()

    @callback
    def _cancel_all_timers() -> None:
        for profile_id in list(store["stale_timers"]):
            _cancel_timer(profile_id)

    entry.async_on_unload(hass.bus.async_listen(EVENT_TYPE, _handle_event))
    entry.async_on_unload(_cancel_all_timers)
    _LOGGER.info("Listening for versioned '%s' events", EVENT_TYPE)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload platforms and release entry data."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
