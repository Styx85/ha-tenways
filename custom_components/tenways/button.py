"""TENWAYS buttons: set the clock, clear the trip, reset HA's overall maximum.

The first two write to the bike and exist as working buttons only for a model confirmed on a
bike (the coordinator's ``writes_allowed``); for any other model they are unavailable.
"""
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
        TenwaysResetMaxSpeedTotal(entry, entry.runtime_data, "reset_max_speed_total"),
    ])


class TenwaysSetClock(TenwaysEntity, ButtonEntity):
    """Sets the bike's clock to Home Assistant's local time when pressed.

    One of the two commands the integration sends to the bike (the other is the trip reset),
    by this button or by the option "Set the clock automatically", and only to a model
    confirmed on a bike. The bike has no daylight saving of its own, so press it again after
    a change.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:clock-check-outline"

    @property
    def available(self) -> bool:
        return self.coordinator.writes_allowed  # when in range or not, pressing explains the rest

    async def async_press(self) -> None:
        await self.coordinator.async_set_clock(dt_util.now())


class TenwaysResetTrip(TenwaysEntity, ButtonEntity):
    """Clears the bike's trip like the display's "Clear trip" when pressed.

    Trip distance, trip time, maximum and average speed (and the display's CO2
    and trees, derived from the trip) go to 0; the odometer stays. Sent by this button or by
    the option "Clear the trip automatically", and only to a model confirmed on a bike.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:broom"

    @property
    def available(self) -> bool:
        return self.coordinator.writes_allowed  # when in range or not, pressing explains the rest

    async def async_press(self) -> None:
        await self.coordinator.async_reset_trip()


class TenwaysResetMaxSpeedTotal(TenwaysEntity, ButtonEntity):
    """Sets HA's maximum over all trips to 0, e.g. after an implausible reading. Sends nothing."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:speedometer-slow"
    _attr_entity_registry_enabled_default = False

    async def async_press(self) -> None:
        self.coordinator.totals.async_reset_max_speed()
