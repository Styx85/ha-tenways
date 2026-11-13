"""TENWAYS BLE integration."""
from __future__ import annotations

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_ADDRESS, CONF_POLL_SECONDS, DOMAIN, POLL_SECONDS
from .coordinator import TenwaysCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]

# Entities that earlier versions created and that no longer exist.
STALE_ENTITIES = (
    ("sensor", "assist_level"),  # 0.6.0, removed in 0.6.1: field 0x0B is the range, not a level
)

type TenwaysConfigEntry = ConfigEntry[TenwaysCoordinator]


def _remove_stale_entities(hass: HomeAssistant, entry: TenwaysConfigEntry) -> None:
    registry = er.async_get(hass)
    for domain, suffix in STALE_ENTITIES:
        if entity_id := registry.async_get_entity_id(domain, DOMAIN, f"{entry.data[CONF_ADDRESS]}_{suffix}"):
            registry.async_remove(entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: TenwaysConfigEntry) -> bool:
    _remove_stale_entities(hass, entry)
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


async def _async_options_updated(hass: HomeAssistant, entry: TenwaysConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: TenwaysConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
