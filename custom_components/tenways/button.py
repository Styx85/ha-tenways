"""TENWAYS buttons: set the clock, clear the trip."""
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
    async_add_entities([
        TenwaysSetClock(entry, entry.runtime_data, "set_clock"),
        TenwaysResetTrip(entry, entry.runtime_data, "reset_trip"),
    ])


class TenwaysSetClock(TenwaysEntity, ButtonEntity):
    """Sets the bike's clock to Home Assistant's local time, only when pressed.

    One of the two commands the integration sends, only on a press. The bike has
    no daylight saving of its own, so press it again after a change.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:clock-check-outline"

    @property
    def available(self) -> bool:
        return True  # pressing it explains when the bike is out of range

    async def async_press(self) -> None:
        await self.coordinator.async_set_clock(dt_util.now())


class TenwaysResetTrip(TenwaysEntity, ButtonEntity):
    """Clears the bike's trip like the display's "Clear trip", only when pressed.

    Trip distance, trip time, maximum and average speed (and the display's CO2
    and trees, derived from the trip) go to 0; the odometer stays.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:broom"

    @property
    def available(self) -> bool:
        return True  # pressing it explains when the bike is out of range

    async def async_press(self) -> None:
        await self.coordinator.async_reset_trip()
