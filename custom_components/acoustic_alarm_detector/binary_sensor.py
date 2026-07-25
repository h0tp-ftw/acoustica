"""Binary sensor platform for Acoustic Alarm Detector."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ALARM_TYPE_CO,
    ALARM_TYPE_SMOKE,
    DOMAIN,
    SIGNAL_STATE_UPDATED,
    VERSION,
)
from .runtime import DetectorRuntime


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the integration-owned binary sensor."""

    async_add_entities(
        [AcousticAlarmBinarySensor(entry.entry_id, entry.runtime_data)]
    )


class AcousticAlarmBinarySensor(BinarySensorEntity):
    """Alarm state received from the acoustic detector add-on."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry_id: str, runtime: DetectorRuntime) -> None:
        self._entry_id = entry_id
        self._runtime = runtime

        if runtime.alarm_type == ALARM_TYPE_SMOKE:
            self._attr_device_class = BinarySensorDeviceClass.SMOKE
            sensor_name = "Smoke alarm"
        elif runtime.alarm_type == ALARM_TYPE_CO:
            self._attr_device_class = BinarySensorDeviceClass.CO
            sensor_name = "CO alarm"
        else:
            self._attr_device_class = BinarySensorDeviceClass.SAFETY
            sensor_name = "Alarm"

        self._attr_unique_id = f"{runtime.detector_id}_{runtime.profile_id}"
        self._attr_name = sensor_name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, runtime.detector_id)},
            name=runtime.detector_id.replace("_", " ").title(),
            manufacturer="Open Source",
            model="Acoustic Alarm Detector",
            sw_version=VERSION,
        )

    @property
    def is_on(self) -> bool:
        return self._runtime.active

    @property
    def available(self) -> bool:
        return self._runtime.available

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "detector_id": self._runtime.detector_id,
            "profile_id": self._runtime.profile_id,
            "alarm_type": self._runtime.alarm_type,
            "last_update": self._runtime.updated_at,
            "last_seen": self._runtime.last_seen,
            "source_version": self._runtime.source_version,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_STATE_UPDATED.format(entry_id=self._entry_id),
                self._handle_state_updated,
            )
        )

    @callback
    def _handle_state_updated(self) -> None:
        self.async_write_ha_state()
