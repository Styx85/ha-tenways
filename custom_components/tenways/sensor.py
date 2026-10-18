"""TENWAYS battery sensor."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ADDRESS, DOMAIN
from .coordinator import TenwaysCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([TenwaysBatterySensor(entry, entry.runtime_data)])


class TenwaysBatterySensor(CoordinatorEntity[TenwaysCoordinator], SensorEntity):
    """The value returned by BLE Battery Level 0x2A19."""

    _attr_has_entity_name = True
    _attr_name = "BLE battery level"
    _attr_icon = "mdi:battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, entry: ConfigEntry, coordinator: TenwaysCoordinator) -> None:
        super().__init__(coordinator)
        address = entry.data[CONF_ADDRESS]
        self._attr_unique_id = f"{address}_battery"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            name=entry.title,
            manufacturer="TENWAYS",
            model="Longtail Duo (BLE, unverified)",
        )

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data
