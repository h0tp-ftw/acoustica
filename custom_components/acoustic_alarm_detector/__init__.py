"""The Acoustic Alarm Detector integration."""

from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_ALARM_TYPE,
    CONF_DEVICE_NAME,
    CONF_PROFILE_ID,
    DEFAULT_ALARM_TYPE,
    DEFAULT_DEVICE_NAME,
    DEFAULT_PROFILE_ID,
    EVENT_STATE_UPDATE,
    PLATFORMS,
    SIGNAL_STATE_UPDATED,
    STATE_STALE_AFTER,
    entry_unique_id,
    migrate_entry_data,
)
from .runtime import DetectorRuntime

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration namespace."""

    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate profile IDs and stable detector/profile config-entry identity."""

    if entry.version == 1 and entry.minor_version < 3:
        data = migrate_entry_data(dict(entry.data))
        hass.config_entries.async_update_entry(
            entry,
            data=data,
            unique_id=entry_unique_id(
                data[CONF_DEVICE_NAME],
                data[CONF_PROFILE_ID],
            ),
            version=1,
            minor_version=3,
        )

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entity when Supervisor discovery updates its identifiers."""

    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one integration-owned detector entity."""

    runtime = DetectorRuntime(
        detector_id=entry.data.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME),
        profile_id=entry.data.get(CONF_PROFILE_ID, DEFAULT_PROFILE_ID),
        alarm_type=entry.data.get(CONF_ALARM_TYPE, DEFAULT_ALARM_TYPE),
    )
    entry.runtime_data = runtime
    cancel_stale_timer: Callable[[], None] | None = None

    @callback
    def _notify_entities() -> None:
        async_dispatcher_send(
            hass,
            SIGNAL_STATE_UPDATED.format(entry_id=entry.entry_id),
        )

    @callback
    def _mark_stale(_now) -> None:
        nonlocal cancel_stale_timer
        cancel_stale_timer = None
        if runtime.mark_unavailable():
            _LOGGER.warning(
                "No state heartbeat received for %s/%s",
                runtime.detector_id,
                runtime.profile_id,
            )
            _notify_entities()

    @callback
    def _cancel_stale_timer() -> None:
        nonlocal cancel_stale_timer
        if cancel_stale_timer is not None:
            cancel_stale_timer()
            cancel_stale_timer = None

    @callback
    def _handle_addon_state(event: Event) -> None:
        nonlocal cancel_stale_timer
        if not runtime.apply_event(dict(event.data)):
            return

        runtime.last_seen = event.time_fired.isoformat()
        _cancel_stale_timer()
        cancel_stale_timer = async_call_later(
            hass,
            STATE_STALE_AFTER,
            _mark_stale,
        )
        _notify_entities()
        _LOGGER.debug(
            "Accepted %s/%s state: %s",
            runtime.detector_id,
            runtime.profile_id,
            runtime.active,
        )

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    entry.async_on_unload(
        hass.bus.async_listen(EVENT_STATE_UPDATE, _handle_addon_state)
    )
    entry.async_on_unload(_cancel_stale_timer)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload entities and invoke config-entry cleanup callbacks."""

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
