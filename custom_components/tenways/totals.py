"""Values over all trips and per day, computed in HA from the bike's trip counters.

The bike only knows the current trip. Once the trip is cleared (button, display
or an automation), its ride time, maximum and average are gone, so HA keeps its
own running totals, stored per bike and kept across restarts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import logging

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
SAVE_DELAY_SECONDS = 10
# The TENWAYS app also discards higher trip maxima as implausible.
MAX_PLAUSIBLE_SPEED_KMH = 75.0


@dataclass
class TotalsState:
    """What is stored; counters in seconds and km like the bike reports them."""

    ride_s: float = 0.0  # ride time counted since tracking started (the offset option comes on top)
    last_trip_s: float | None = None  # trip ride time at the last read, None before the first
    max_speed: float | None = None
    day: str | None = None  # local date the day values belong to
    day_ride_s: float = 0.0
    day_start_odometer: float | None = None
    last_odometer: float | None = None


class TenwaysTotals:
    """Running totals for one bike."""

    def __init__(self, hass: HomeAssistant, entry_id: str, ride_offset_s: float = 0.0) -> None:
        self._hass = hass
        self._store: Store[dict] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.totals.{entry_id}")
        self.state = TotalsState()
        self.ride_offset_s = ride_offset_s
        self._listeners: list[CALLBACK_TYPE] = []
        self._unsub_midnight: CALLBACK_TYPE | None = None

    async def async_load(self) -> None:
        if stored := await self._store.async_load():
            known = TotalsState.__dataclass_fields__
            self.state = TotalsState(**{k: v for k, v in stored.items() if k in known})
        self._roll_day(dt_util.now().date())
        self._unsub_midnight = async_track_time_change(
            self._hass, self._async_midnight, hour=0, minute=0, second=0
        )

    async def async_unload(self) -> None:
        if self._unsub_midnight is not None:
            self._unsub_midnight()
            self._unsub_midnight = None
        await self._store.async_save(asdict(self.state))

    async def async_remove(self) -> None:
        await self._store.async_remove()

    @callback
    def async_add_listener(self, update: CALLBACK_TYPE) -> CALLBACK_TYPE:
        self._listeners.append(update)
        return lambda: self._listeners.remove(update)

    # Values for the sensors

    @property
    def total_ride_s(self) -> float | None:
        if self.state.last_trip_s is None:
            return None  # nothing read yet
        return self.ride_offset_s + self.state.ride_s

    @property
    def max_speed(self) -> float | None:
        return self.state.max_speed

    @property
    def day_ride_s(self) -> float | None:
        return self.state.day_ride_s if self.state.last_trip_s is not None else None

    @property
    def day_distance(self) -> float | None:
        s = self.state
        if s.last_odometer is None or s.day_start_odometer is None:
            return None
        return round(max(0.0, s.last_odometer - s.day_start_odometer), 2)

    def average_speed(self, odometer: float | None) -> float | None:
        """Odometer over total ride time; both count from kilometre 0 when the offset is right."""
        total = self.total_ride_s
        if odometer is None or not total:
            return None
        return round(odometer * 3600 / total, 1)

    # Updates

    @callback
    def async_update(
        self, ride_s: float | None, odometer: float | None, trip_max: float | None
    ) -> None:
        """Account one successful read of the bike."""
        s = self.state
        self._roll_day(dt_util.now().date())
        if ride_s is not None:
            if s.last_trip_s is None:
                # First read: the trip holds everything since its last reset.
                s.ride_s = float(ride_s)
            else:
                # A lower value means the trip was cleared and counts again from 0.
                delta = ride_s - s.last_trip_s if ride_s >= s.last_trip_s else ride_s
                s.ride_s += delta
                s.day_ride_s += delta
            s.last_trip_s = float(ride_s)
        if odometer is not None:
            if s.day_start_odometer is None:
                s.day_start_odometer = odometer
            s.last_odometer = odometer
        if trip_max is not None and 0 <= trip_max <= MAX_PLAUSIBLE_SPEED_KMH:
            s.max_speed = max(s.max_speed or 0.0, trip_max)
        self._changed()

    @callback
    def async_trip_cleared(self) -> None:
        """The trip was cleared by HA; the next read counts from 0."""
        if self.state.last_trip_s is not None:
            self.state.last_trip_s = 0.0
            self._changed()

    @callback
    def async_reset_max_speed(self) -> None:
        self.state.max_speed = 0.0
        self._changed()

    @callback
    def _async_midnight(self, now: datetime) -> None:
        if self._roll_day(now.date()):
            self._changed()

    def _roll_day(self, today: date) -> bool:
        s = self.state
        if s.day == today.isoformat():
            return False
        s.day = today.isoformat()
        s.day_ride_s = 0.0
        s.day_start_odometer = s.last_odometer
        return True

    def _changed(self) -> None:
        self._store.async_delay_save(lambda: asdict(self.state), SAVE_DELAY_SECONDS)
        for update in list(self._listeners):
            update()
