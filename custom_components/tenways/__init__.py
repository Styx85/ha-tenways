"""TENWAYS BLE integration."""
from __future__ import annotations

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_ADDRESS, CONF_POLL_SECONDS, POLL_SECONDS
from .coordinator import TenwaysCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = TenwaysCoordinator(
        hass, entry.data[CONF_ADDRESS], entry.options.get(CONF_POLL_SECONDS, POLL_SECONDS)
    )
    entry.runtime_data = coordinator
    # Startup should not fail while the bicycle is switched off or away.
    await coordinator.async_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    entry.async_on_unload(bluetooth.async_register_callback(
        hass, coordinator.async_handle_advertisement,
        bluetooth.BluetoothCallbackMatcher(address=entry.data[CONF_ADDRESS], connectable=True),
        bluetooth.BluetoothScanningMode.PASSIVE,
    ))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
