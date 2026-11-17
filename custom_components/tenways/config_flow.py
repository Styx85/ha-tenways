"""Configuration flow for TENWAYS BLE."""
from __future__ import annotations

import re

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict, SelectSelector, SelectSelectorConfig, SelectSelectorMode,
)
from tenways_ble.const import TENWAYS_SERVICE_UUID

from .models import model_profile
from .const import (
    CONF_ADDRESS, CONF_ADVERTISED_NAME, CONF_AUTO_CLOCK, CONF_TRIP_RESET, TRIP_RESET_MODES, TRIP_RESET_OFF, KING_METER_NAME_PREFIXES, CONF_POLL_SECONDS, CONF_RIDE_HOURS_BEFORE, CONF_UNCONFIRMED_WRITES, DOMAIN, MAX_POLL_SECONDS, MIN_POLL_SECONDS, NAME_PREFIX,
    POLL_SECONDS,
)


def is_tenways_name(name: str | None) -> bool:
    return bool(name and (name.startswith(NAME_PREFIX) or name.lower().startswith("longtail duo")))


def has_telemetry(info: bluetooth.BluetoothServiceInfoBleak) -> bool:
    """Only an endpoint with the King Meter service delivers bike data.

    Matched by a King Meter model name or the advertised service. The Longtail
    Duo's second endpoint (Tenways-ble-*) is not offered automatically; it can
    still be added by hand for diagnostics.
    """
    return bool(info.name and info.name.startswith(KING_METER_NAME_PREFIXES)) or (
        TENWAYS_SERVICE_UUID in (info.service_uuids or [])
    )


def unsupported_reason(info: bluetooth.BluetoothServiceInfoBleak) -> str | None:
    """Why a discovered model is not supported (e.g. AGO AIR, encrypted), or None."""
    profile = model_profile(info.name)
    return None if profile.supported else profile.reason

MAC_PATTERN = re.compile(r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def advertised_name(info: bluetooth.BluetoothServiceInfoBleak | None) -> str | None:
    """The name a bike really advertised; None when there is none (or only its address)."""
    name = info.name if info is not None else None
    if not name or name.upper().replace("-", ":") == info.address.upper():
        return None
    return name


def entry_data(address: str, name: str, advertised: str | None) -> dict:
    """Entry data; the advertised name is only stored when the bike really sent one."""
    data = {CONF_ADDRESS: address, CONF_NAME: name}
    if advertised:
        data[CONF_ADVERTISED_NAME] = advertised
    return data


class TenwaysConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a TENWAYS bike."""

    VERSION = 1
    _discovered: tuple[str, str] | None = None
    _advertised: str | None = None

    def _title(self, name: str, address: str) -> str:
        """The entry's title; a second bike with the same name gets the end of its address."""
        if any(entry.title == name for entry in self._async_current_entries()):
            return f"{name} {address[-5:]}"
        return name

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
        if reason := unsupported_reason(discovery_info):
            return self.async_abort(
                reason="unsupported_model",
                description_placeholders={"name": discovery_info.name or "", "reason": reason},
            )
        address = discovery_info.address.upper()
        await self.async_set_unique_id(address)
        self._abort_if_unique_id_configured()
        name = discovery_info.name or f"TENWAYS {address[-5:]}"
        self._discovered = (address, name)
        self._advertised = advertised_name(discovery_info)
        self.context["title_placeholders"] = {"name": name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Ask before adding, so a removed entry is not recreated on the next advertisement."""
        assert self._discovered is not None
        address, name = self._discovered
        if user_input is not None:
            return self.async_create_entry(
                title=self._title(name, address), data=entry_data(address, name, self._advertised),
            )
        self._set_confirm_only()
        return self.async_show_form(step_id="bluetooth_confirm", description_placeholders={"name": name})

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Pick a discovered bike or type its address; typing stays possible when bikes are visible."""
        configured = self._async_current_ids()
        seen = {
            info.address.upper(): info
            for info in bluetooth.async_discovered_service_info(self.hass, connectable=True)
        }
        found = {
            address: info.name or f"TENWAYS {address[-5:]}"
            for address, info in seen.items()
            if has_telemetry(info) and not unsupported_reason(info) and address not in configured
        }
        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            if MAC_PATTERN.fullmatch(address):
                # A typed address of a visible, unsupported model: explain instead of polling in vain.
                if (info := seen.get(address)) is not None and (reason := unsupported_reason(info)):
                    return self.async_abort(
                        reason="unsupported_model",
                        description_placeholders={"name": info.name or address, "reason": reason},
                    )
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()
                name = found.get(address, f"TENWAYS {address[-5:]}")
                return self.async_create_entry(
                    title=self._title(name, address),
                    data=entry_data(address, name, advertised_name(seen.get(address))),
                )
            return self.async_show_form(
                step_id="user", data_schema=self._schema(found),
                errors={CONF_ADDRESS: "invalid_address"},
            )
        return self.async_show_form(step_id="user", data_schema=self._schema(found))

    @staticmethod
    def _schema(found: dict[str, str]) -> vol.Schema:
        if found:
            return vol.Schema({vol.Required(CONF_ADDRESS): SelectSelector(SelectSelectorConfig(
                options=[SelectOptionDict(value=addr, label=f"{name} ({addr})") for addr, name in found.items()],
                custom_value=True, mode=SelectSelectorMode.DROPDOWN,
            ))})
        return vol.Schema({vol.Required(CONF_ADDRESS): str})


class TenwaysOptionsFlow(OptionsFlow):
    """Adjust how often HA connects to the bike, and the ride time from before HA counted.

    The automatic trip reset and clock write to the bike, so they are offered only for a model
    confirmed on a bike, or when the user allows writes to unconfirmed models; a stored choice
    for any other model is kept but not used.
    """

    async def async_step_init(self, user_input: dict | None = None) -> ConfigFlowResult:
        options = self.config_entry.options
        coordinator = getattr(self.config_entry, "runtime_data", None)
        writes = bool(coordinator is not None and coordinator.writes_allowed)
        if user_input is not None:
            kept = {k: v for k, v in options.items() if k in (CONF_TRIP_RESET, CONF_AUTO_CLOCK)}
            return self.async_create_entry(data={**kept, **user_input})
        schema = {
            vol.Required(CONF_POLL_SECONDS, default=options.get(CONF_POLL_SECONDS, POLL_SECONDS)): vol.All(
                vol.Coerce(int), vol.Range(min=MIN_POLL_SECONDS, max=MAX_POLL_SECONDS)
            ),
            vol.Required(CONF_RIDE_HOURS_BEFORE, default=options.get(CONF_RIDE_HOURS_BEFORE, 0)): vol.All(
                vol.Coerce(float), vol.Range(min=0, max=100000)
            ),
            vol.Required(CONF_UNCONFIRMED_WRITES, default=options.get(CONF_UNCONFIRMED_WRITES, False)): bool,
        }
        if writes:
            schema[vol.Required(CONF_TRIP_RESET, default=options.get(CONF_TRIP_RESET, TRIP_RESET_OFF))] = SelectSelector(
                SelectSelectorConfig(options=list(TRIP_RESET_MODES), translation_key=CONF_TRIP_RESET)
            )
            schema[vol.Required(CONF_AUTO_CLOCK, default=options.get(CONF_AUTO_CLOCK, False))] = bool
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
