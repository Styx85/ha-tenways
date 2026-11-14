"""TENWAYS select: how the integration clears the trip automatically."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TenwaysConfigEntry
from .const import CONF_TRIP_RESET, TRIP_RESET_MODES
from .entity import TenwaysEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: TenwaysConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([TenwaysTripResetSelect(entry, entry.runtime_data, CONF_TRIP_RESET)])


class TenwaysTripResetSelect(TenwaysEntity, SelectEntity):
    """The option "Clear the trip automatically" on the device page; stored in the entry's options."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:broom"
    _attr_options = list(TRIP_RESET_MODES)

    def __init__(self, entry: TenwaysConfigEntry, coordinator, key: str) -> None:
        super().__init__(entry, coordinator, key)
        self._entry = entry

    @property
    def available(self) -> bool:
        return True

    @property
    def current_option(self) -> str:
        return self.coordinator.trip_reset

    async def async_select_option(self, option: str) -> None:
        self.hass.config_entries.async_update_entry(
            self._entry, options={**self._entry.options, CONF_TRIP_RESET: option}
        )
