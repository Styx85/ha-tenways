"""TENWAYS read-only battery and Bluetooth diagnostic sensors."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import RestoreSensor, SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT, EntityCategory, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TenwaysConfigEntry
from .const import CONF_ADDRESS
from .coordinator import LIVE_FIELDS, TenwaysCoordinator
from .entity import TenwaysEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: TenwaysConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([
        TenwaysSensor(entry, coordinator, "ble_battery", "battery_level"),
        TenwaysSensor(entry, coordinator, "traction_battery", "traction_battery"),
        TenwaysSensor(entry, coordinator, "odometer", "odometer"),
        TenwaysSensor(entry, coordinator, "trip_distance", "trip_distance"),
        TenwaysSensor(entry, coordinator, "speed", "speed"),
        TenwaysSensor(entry, coordinator, "max_speed", "max_speed"),
        TenwaysSensor(entry, coordinator, "average_speed", "average_speed"),
        TenwaysSensor(entry, coordinator, "ride_seconds", "ride_seconds"),
        TenwaysSensor(entry, coordinator, "remaining_range", "remaining_range"),
        TenwaysSensor(entry, coordinator, "power", "power"),
        TenwaysSensor(entry, coordinator, "rssi", "rssi"),
        TenwaysSensor(entry, coordinator, "last_seen", "last_advertisement"),
        TenwaysSensor(entry, coordinator, "last_read", "last_successful_read"),
        TenwaysSensor(entry, coordinator, "firmware", "firmware"),
        TenwaysSensor(entry, coordinator, "serial", "serial"),
        TenwaysSensor(entry, coordinator, "raw_0b", "raw_0b"),
        TenwaysSensor(entry, coordinator, "raw_11", "raw_11"),
        TenwaysSensor(entry, coordinator, "raw_23", "raw_23"),
        TenwaysSensor(entry, coordinator, "raw_4f", "raw_4f"),
        TenwaysSensor(entry, coordinator, "model", "model"),
        TenwaysSensor(entry, coordinator, "manufacturer", "manufacturer"),
    ])


class TenwaysSensor(TenwaysEntity, RestoreSensor):
    """A measured standard BLE field, or a diagnostic observation.

    Apart from live fields, the last read value stays while the bike is off
    and is restored after an HA restart; "Last successful GATT read" dates it.
    """

    _restored: int | float | str | datetime | None = None

    def __init__(self, entry: TenwaysConfigEntry, coordinator: TenwaysCoordinator, key: str, field: str) -> None:
        super().__init__(entry, coordinator, key)
        address = entry.data[CONF_ADDRESS]
        self._field = field
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
        elif key == "remaining_range":
            # Field 0x0B (remainingRange in the app); km is probable, not stated there.
            self._attr_native_unit_of_measurement = "km"
            self._attr_device_class = SensorDeviceClass.DISTANCE
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif key == "power":
            # Field 0x23 (power in the app), probably motor power; 0 while parked, not seen riding.
            self._attr_native_unit_of_measurement = UnitOfPower.WATT
            self._attr_device_class = SensorDeviceClass.POWER
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
