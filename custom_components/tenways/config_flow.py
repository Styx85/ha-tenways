"""Configuration flow for TENWAYS BLE."""
from __future__ import annotations

import re

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_NAME

from .const import CONF_ADDRESS, DOMAIN, NAME_PREFIX


def is_tenways_name(name: str | None) -> bool:
    return bool(name and (name.startswith(NAME_PREFIX) or name.lower().startswith("longtail duo")))

MAC_PATTERN = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


class TenwaysConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a TENWAYS bike."""

    VERSION = 1

    async def async_step_bluetooth(
        self, discovery_info: bluetooth.BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Start from a Bluetooth advertisement."""
        if not discovery_info.connectable or not is_tenways_name(discovery_info.name):
            return self.async_abort(reason="not_supported")
        address = discovery_info.address.upper()
        await self.async_set_unique_id(address)
        self._abort_if_unique_id_configured()
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return self.async_create_entry(
            title=discovery_info.name,
            data={CONF_ADDRESS: address, CONF_NAME: discovery_info.name},
        )

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Allow selecting a discovered bike or entering an address."""
        found = {
            info.address.upper(): info.name
            for info in bluetooth.async_discovered_service_info(self.hass, connectable=True)
            if info.name and is_tenways_name(info.name)
        }
        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            if address in found or MAC_PATTERN.fullmatch(address):
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()
                name = found.get(address, f"TENWAYS {address[-5:]}")
                return self.async_create_entry(
                    title=name, data={CONF_ADDRESS: address, CONF_NAME: name}
                )
            return self.async_show_form(
                step_id="user", data_schema=self._schema(found),
                errors={CONF_ADDRESS: "invalid_address"},
            )
        return self.async_show_form(step_id="user", data_schema=self._schema(found))

    @staticmethod
    def _schema(found: dict[str, str]) -> vol.Schema:
        if found:
            return vol.Schema({vol.Required(CONF_ADDRESS): vol.In(
                {addr: f"{name} ({addr})" for addr, name in found.items()}
            )})
        return vol.Schema({vol.Required(CONF_ADDRESS): str})
