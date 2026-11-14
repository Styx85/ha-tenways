"""TENWAYS switch: set the bike's clock automatically."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TenwaysConfigEntry
from .const import CONF_AUTO_CLOCK
from .entity import TenwaysEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: TenwaysConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([TenwaysAutoClockSwitch(entry, entry.runtime_data, CONF_AUTO_CLOCK)])


class TenwaysAutoClockSwitch(TenwaysEntity, SwitchEntity):
    """The option "Set the clock automatically" on the device page; stored in the entry's options."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, entry: TenwaysConfigEntry, coordinator, key: str) -> None:
        super().__init__(entry, coordinator, key)
        self._entry = entry

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.auto_clock

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._set(False)

    def _set(self, value: bool) -> None:
        self.hass.config_entries.async_update_entry(self._entry, options={**self._entry.options, CONF_AUTO_CLOCK: value})
