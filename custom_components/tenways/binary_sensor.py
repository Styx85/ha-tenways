"""TENWAYS Bluetooth visibility diagnostic."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ADDRESS
from .coordinator import TenwaysCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([TenwaysVisible(entry, entry.runtime_data)])


class TenwaysVisible(CoordinatorEntity[TenwaysCoordinator], BinarySensorEntity):
    """Whether HA has heard a recent connectable advertisement (not an active connection)."""

    _attr_has_entity_name = True
    _attr_name = "Bluetooth recently seen"
    _attr_icon = "mdi:bluetooth"
    _attr_entity_registry_enabled_default = False

    def __init__(self, entry: ConfigEntry, coordinator: TenwaysCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.data[CONF_ADDRESS]}_bluetooth_visible"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data and self.coordinator.data.bluetooth_visible)
