"""TENWAYS Bluetooth visibility and light."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TenwaysConfigEntry
from .entity import TenwaysEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: TenwaysConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([
        TenwaysVisible(entry, entry.runtime_data, "bluetooth_visible"),
        TenwaysLight(entry, entry.runtime_data, "light"),
    ])


class TenwaysVisible(TenwaysEntity, BinarySensorEntity):
    """Whether HA has heard a recent connectable advertisement (not an active connection)."""

    _attr_icon = "mdi:bluetooth"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data and self.coordinator.data.bluetooth_visible)


class TenwaysLight(TenwaysEntity, BinarySensorEntity):
    """Light switch state from status field 0x11; unknown while the bike is unreachable."""

    _attr_device_class = BinarySensorDeviceClass.LIGHT

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.light if self.coordinator.data else None

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.is_on is not None
