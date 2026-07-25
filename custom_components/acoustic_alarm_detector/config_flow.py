"""Config flow for Acoustic Alarm Detector."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from .const import (
    ALARM_TYPES,
    CONF_ALARM_TYPE,
    CONF_DEVICE_NAME,
    CONF_PROFILE_ID,
    DEFAULT_ALARM_TYPE,
    DEFAULT_DEVICE_NAME,
    DEFAULT_PROFILE_ID,
    DOMAIN,
    entry_unique_id,
    parse_discovery_config,
)

PROFILE_ID_SCHEMA = vol.All(
    str,
    vol.Strip,
    vol.Match(r"^[a-z0-9][a-z0-9_]*$"),
)


class AcousticAlarmDetectorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure the entity that receives add-on state events."""

    VERSION = 1
    MINOR_VERSION = 3

    def __init__(self) -> None:
        super().__init__()
        self._discovered_data: dict[str, str] | None = None

    async def async_step_hassio(
        self,
        discovery_info: HassioServiceInfo,
    ) -> config_entries.ConfigFlowResult:
        """Handle discovery from the Home Assistant app."""

        data = parse_discovery_config(dict(discovery_info.config))
        if data is None:
            return self.async_abort(reason="invalid_discovery")

        await self.async_set_unique_id(
            entry_unique_id(
                data[CONF_DEVICE_NAME],
                data[CONF_PROFILE_ID],
            )
        )
        self._abort_if_unique_id_configured(updates=data)
        if _entry_already_exists(self._async_current_entries(), data):
            return self.async_abort(reason="already_configured")

        self._discovered_data = data
        self.context["title_placeholders"] = {
            "name": data[CONF_DEVICE_NAME],
            "profile": data[CONF_PROFILE_ID],
        }
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Ask the user to confirm the discovered detector."""

        if self._discovered_data is None:
            return self.async_abort(reason="invalid_discovery")

        if user_input is not None:
            return self.async_create_entry(
                title=_entry_title(self._discovered_data),
                data=self._discovered_data,
            )

        return self.async_show_form(
            step_id="hassio_confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "detector": self._discovered_data[CONF_DEVICE_NAME],
                "profile": self._discovered_data[CONF_PROFILE_ID],
                "alarm_type": ALARM_TYPES[
                    self._discovered_data[CONF_ALARM_TYPE]
                ],
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Provide a manual fallback when Supervisor discovery is unavailable."""

        errors: dict[str, str] = {}

        if user_input is not None:
            data = {
                CONF_DEVICE_NAME: user_input[CONF_DEVICE_NAME].strip(),
                CONF_PROFILE_ID: user_input[CONF_PROFILE_ID].strip(),
                CONF_ALARM_TYPE: user_input[CONF_ALARM_TYPE],
            }

            if not data[CONF_DEVICE_NAME]:
                errors[CONF_DEVICE_NAME] = "invalid_device_name"
            else:
                await self.async_set_unique_id(
                    entry_unique_id(
                        data[CONF_DEVICE_NAME],
                        data[CONF_PROFILE_ID],
                    )
                )
                self._abort_if_unique_id_configured()
                if _entry_already_exists(self._async_current_entries(), data):
                    return self.async_abort(reason="already_configured")
                return self.async_create_entry(
                    title=_entry_title(data),
                    data=data,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_DEVICE_NAME,
                        default=DEFAULT_DEVICE_NAME,
                    ): str,
                    vol.Required(
                        CONF_PROFILE_ID,
                        default=DEFAULT_PROFILE_ID,
                    ): PROFILE_ID_SCHEMA,
                    vol.Required(
                        CONF_ALARM_TYPE,
                        default=DEFAULT_ALARM_TYPE,
                    ): vol.In(ALARM_TYPES),
                }
            ),
            errors=errors,
        )


def _entry_title(data: dict[str, str]) -> str:
    return f"{data[CONF_DEVICE_NAME]} ({data[CONF_PROFILE_ID]})"


def _entry_already_exists(entries, data: dict[str, str]) -> bool:
    return any(
        entry.data.get(CONF_DEVICE_NAME) == data[CONF_DEVICE_NAME]
        and entry.data.get(CONF_PROFILE_ID) == data[CONF_PROFILE_ID]
        for entry in entries
    )
