"""Config flow for Acoustica."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from .const import DEVICE_NAME, DOMAIN, parse_discovery_config


class AcousticaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure the single Acoustica event receiver."""

    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._discovered_data: dict[str, str] | None = None

    async def async_step_hassio(
        self,
        discovery_info: HassioServiceInfo,
    ) -> config_entries.ConfigFlowResult:
        """Handle scoped discovery published by the add-on."""

        data = parse_discovery_config(dict(discovery_info.config))
        if data is None:
            return self.async_abort(reason="invalid_discovery")

        await self.async_set_unique_id(discovery_info.uuid)
        self._abort_if_unique_id_configured(updates=data)
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        self._discovered_data = data
        self.context["title_placeholders"] = {"name": DEVICE_NAME}
        return await self.async_step_hassio_confirm()

    async def async_step_hassio_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Require explicit user confirmation for Supervisor discovery."""

        if self._discovered_data is None:
            return self.async_abort(reason="invalid_discovery")
        if user_input is not None:
            return self.async_create_entry(title=DEVICE_NAME, data=self._discovered_data)
        return self.async_show_form(
            step_id="hassio_confirm",
            data_schema=vol.Schema({}),
            description_placeholders={"name": DEVICE_NAME},
        )

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Provide a manual fallback when discovery is unavailable."""

        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(
                title=DEVICE_NAME,
                data={"detector_id": DOMAIN, "source_version": "manual"},
            )
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))
