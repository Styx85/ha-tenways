"""TENWAYS clock sync button."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import TenwaysConfigEntry
from .entity import TenwaysEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: TenwaysConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([TenwaysSetClock(entry, entry.runtime_data, "set_clock")])


class TenwaysSetClock(TenwaysEntity, ButtonEntity):
    """Sets the bike's clock to Home Assistant's local time, only when pressed.

    This is the only command the integration sends to the bike. The bike has no
    daylight saving of its own, so press it again after a change.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:clock-check-outline"

    @property
    def available(self) -> bool:
        return True  # pressing it explains when the bike is out of range

    async def async_press(self) -> None:
        await self.coordinator.async_set_clock(dt_util.now())
