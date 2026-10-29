"""Shared base entity for TENWAYS BLE."""
from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ADDRESS, DOMAIN
from .coordinator import TenwaysCoordinator


class TenwaysEntity(CoordinatorEntity[TenwaysCoordinator]):
    """Entity of one TENWAYS bike; all entities share one device."""

    _attr_has_entity_name = True

    def __init__(self, entry, coordinator: TenwaysCoordinator, unique_suffix: str) -> None:
        super().__init__(coordinator)
        address = entry.data[CONF_ADDRESS]
        self._attr_unique_id = f"{address}_{unique_suffix}"
        self._attr_translation_key = unique_suffix
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            connections={(CONNECTION_BLUETOOTH, address)},
            name=entry.title,
            manufacturer="TENWAYS",
        )
