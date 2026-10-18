"""TENWAYS read-only battery and Bluetooth diagnostic sensors."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import RestoreSensor, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ADDRESS, DOMAIN
from .coordinator import LIVE_FIELDS, TenwaysCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([
        TenwaysSensor(entry, coordinator, "ble_battery", "BLE battery level", "battery_level"),
        TenwaysSensor(entry, coordinator, "traction_battery", "Traction battery", "traction_battery"),
        TenwaysSensor(entry, coordinator, "odometer", "Odometer", "odometer"),
        TenwaysSensor(entry, coordinator, "trip_distance", "Trip distance", "trip_distance"),
        TenwaysSensor(entry, coordinator, "speed", "Speed", "speed"),
        TenwaysSensor(entry, coordinator, "max_speed", "Maximum speed", "max_speed"),
        TenwaysSensor(entry, coordinator, "average_speed", "Average speed", "average_speed"),
        TenwaysSensor(entry, coordinator, "ride_seconds", "Ride duration", "ride_seconds"),
        TenwaysSensor(entry, coordinator, "rssi", "Bluetooth signal strength", "rssi"),
        TenwaysSensor(entry, coordinator, "last_seen", "Last Bluetooth advertisement", "last_advertisement"),
        TenwaysSensor(entry, coordinator, "last_read", "Last successful GATT read", "last_successful_read"),
        TenwaysSensor(entry, coordinator, "firmware", "Firmware", "firmware"),
        TenwaysSensor(entry, coordinator, "serial", "Serial number", "serial"),
        TenwaysSensor(entry, coordinator, "raw_0b", "Unknown field 0x0B", "raw_0b"),
        TenwaysSensor(entry, coordinator, "raw_11", "Unknown field 0x11", "raw_11"),
        TenwaysSensor(entry, coordinator, "raw_23", "Unknown field 0x23", "raw_23"),
        TenwaysSensor(entry, coordinator, "raw_4f", "Unknown field 0x4F", "raw_4f"),
        TenwaysSensor(entry, coordinator, "model", "BLE model", "model"),
        TenwaysSensor(entry, coordinator, "manufacturer", "BLE manufacturer", "manufacturer"),
    ])


class TenwaysSensor(CoordinatorEntity[TenwaysCoordinator], RestoreSensor):
    """A measured standard BLE field, or a diagnostic observation.

    Apart from live fields, the last read value stays while the bike is off
    and is restored after an HA restart; "Last successful GATT read" dates it.
    """

    _attr_has_entity_name = True
    _restored: int | float | str | datetime | None = None

    def __init__(self, entry: ConfigEntry, coordinator: TenwaysCoordinator, key: str, name: str, field: str) -> None:
        super().__init__(coordinator)
        address = entry.data[CONF_ADDRESS]
        self._field = field
        self._attr_unique_id = f"{address}_{key}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)}, name=entry.title, manufacturer="TENWAYS",
        )
        if key == "ble_battery":
            # Preserve the v0.1 entity ID and unique ID during migration.
            self._attr_unique_id = f"{address}_battery"
            self._attr_icon = "mdi:battery-unknown"
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_state_class = SensorStateClass.MEASUREMENT
            # Intentionally NOT battery device class: physical battery is unverified.
            # The Longtail Duo reports 0 % here; the real value is "Traction battery".
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            self._attr_entity_registry_enabled_default = False
        elif key == "traction_battery":
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_device_class = SensorDeviceClass.BATTERY
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif key in ("odometer", "trip_distance"):
            self._attr_native_unit_of_measurement = "km"
            self._attr_device_class = SensorDeviceClass.DISTANCE
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING if key == "odometer" else SensorStateClass.MEASUREMENT
        elif key == "speed":
            # Field 0x06 read 0 while parked; not yet confirmed while riding.
            self._attr_native_unit_of_measurement = "km/h"
            self._attr_device_class = SensorDeviceClass.SPEED
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_entity_registry_enabled_default = False
        elif key in ("max_speed", "average_speed"):
            self._attr_native_unit_of_measurement = "km/h"
            self._attr_device_class = SensorDeviceClass.SPEED
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif key == "ride_seconds":
            self._attr_native_unit_of_measurement = UnitOfTime.SECONDS
            self._attr_suggested_unit_of_measurement = UnitOfTime.HOURS
            self._attr_suggested_display_precision = 1
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif key == "rssi":
            self._attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
            self._attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_entity_registry_enabled_default = False
        elif key == "last_seen":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
            self._attr_entity_registry_enabled_default = False
        elif key == "last_read":
            # Shows how old the retained values are.
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        elif key.startswith("raw_"):
            # Meaning unknown; recorded to help decode the field.
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            self._attr_entity_registry_enabled_default = False
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_icon = "mdi:help-circle-outline"
        else:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            self._attr_entity_registry_enabled_default = key in ("firmware", "serial")
            self._attr_icon = "mdi:information-outline"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._field not in LIVE_FIELDS and (last := await self.async_get_last_sensor_data()):
            self._restored = last.native_value

    @property
    def native_value(self) -> int | float | str | datetime | None:
        value = getattr(self.coordinator.data, self._field) if self.coordinator.data else None
        return self._restored if value is None else value

    @property
    def available(self) -> bool:
        if self._field in LIVE_FIELDS and not self.coordinator.last_update_success:
            return False
        return self.native_value is not None
