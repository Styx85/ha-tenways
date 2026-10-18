"""Configuration flow for TENWAYS BLE."""
from __future__ import annotations

import re

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from tenways_ble.const import TENWAYS_SERVICE_UUID

from .const import (
    CONF_ADDRESS, CONF_POLL_SECONDS, DOMAIN, MAX_POLL_SECONDS, MIN_POLL_SECONDS, NAME_PREFIX,
    POLL_SECONDS,
)


def is_tenways_name(name: str | None) -> bool:
    return bool(name and (name.startswith(NAME_PREFIX) or name.lower().startswith("longtail duo")))


def has_telemetry(info: bluetooth.BluetoothServiceInfoBleak) -> bool:
    """Only the endpoint with the King Meter service delivers bike data.

    The second endpoint (Tenways-ble-*) is not offered automatically; it can
    still be added by hand for diagnostics.
    """
    return bool(info.name and info.name.lower().startswith("longtail duo")) or (
        TENWAYS_SERVICE_UUID in (info.service_uuids or [])
    )

MAC_PATTERN = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


class TenwaysConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a TENWAYS bike."""

    VERSION = 1
    _discovered: tuple[str, str] | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return TenwaysOptionsFlow()

    async def async_step_bluetooth(
        self, discovery_info: bluetooth.BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Start from a Bluetooth advertisement."""
        if not discovery_info.connectable or not has_telemetry(discovery_info):
            return self.async_abort(reason="not_supported")
        address = discovery_info.address.upper()
        await self.async_set_unique_id(address)
        self._abort_if_unique_id_configured()
        name = discovery_info.name or f"TENWAYS {address[-5:]}"
        self._discovered = (address, name)
        self.context["title_placeholders"] = {"name": name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Ask before adding, so a removed entry is not recreated on the next advertisement."""
        assert self._discovered is not None
        address, name = self._discovered
        if user_input is not None:
            return self.async_create_entry(title=name, data={CONF_ADDRESS: address, CONF_NAME: name})
        self._set_confirm_only()
        return self.async_show_form(step_id="bluetooth_confirm", description_placeholders={"name": name})

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


class TenwaysOptionsFlow(OptionsFlow):
    """Adjust how often HA connects to the bike."""

    async def async_step_init(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_POLL_SECONDS, POLL_SECONDS)
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required(CONF_POLL_SECONDS, default=current): vol.All(
                vol.Coerce(int), vol.Range(min=MIN_POLL_SECONDS, max=MAX_POLL_SECONDS)
            ),
        }))
