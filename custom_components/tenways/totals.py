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
MAX_FAILURES_PER_DAY = 3
CLOCK_MAX_AGE_SECONDS = 90 * 24 * 3600


@dataclass
class TotalsState:
    """What is stored; counters in seconds and km like the bike reports them."""

    ride_s: float = 0.0  # ride time counted since tracking started (the offset option comes on top)
    last_trip_s: float | None = None  # trip ride time at the last read, None before the first
    max_speed: float | None = None
    last_trip_km: float | None = None
    last_trip_max: float | None = None
    max_ignore_upto: float | None = None  # after a reset of the maximum: the trip maximum it discarded
    day: str | None = None  # local date the day values belong to
    day_ride_s: float = 0.0
    day_start_odometer: float | None = None
    last_odometer: float | None = None
    # Automatic writes (options): day of the last trip reset, last clock set, failures today.
    trip_reset_day: str | None = None
    clock_set_at: float | None = None  # timestamp
    clock_utc_offset: float | None = None  # seconds, local offset when the clock was set
    failed_day: str | None = None
    clock_failures: int = 0
    reset_failures: int = 0


class TenwaysTotals:
    """Running totals for one bike."""

    def __init__(self, hass: HomeAssistant, entry_id: str, ride_offset_s: float = 0.0) -> None:
        self._hass = hass
        self._store: Store[dict] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.totals.{entry_id}")
        self.state = TotalsState()
        self.ride_offset_s = ride_offset_s
        self._listeners: list[CALLBACK_TYPE] = []
        self._unloaded = False

    async def async_load(self) -> None:
        if stored := await self._store.async_load():
            known = TotalsState.__dataclass_fields__
            self.state = TotalsState(**{k: v for k, v in stored.items() if k in known})
        self._roll_day(dt_util.now().date())

    @callback
    def async_track_midnight(self) -> CALLBACK_TYPE:
        """Start the day values afresh at local midnight; returns the unsubscribe callback."""
        return async_track_time_change(self._hass, self._async_midnight, hour=0, minute=0, second=0)

    async def async_unload(self) -> None:
        """Final save; a read still in flight must not overwrite the next instance's data."""
        self._unloaded = True
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

    def average_speed(self, odometer: float | None = None) -> float | None:
        """Odometer over total ride time; both count from kilometre 0 when the offset is right."""
        total = self.total_ride_s
        if odometer is None:
            odometer = self.state.last_odometer  # stored, so available before the first read after a restart
        if odometer is None or not total:
            return None
        return round(odometer * 3600 / total, 1)

    # Updates

    @callback
    def async_update(
        self, ride_s: float | None, odometer: float | None, trip_max: float | None,
        trip_km: float | None = None,
    ) -> None:
        """Account one successful read of the bike."""
        if self._unloaded:
            return
        s = self.state
        self._roll_day(dt_util.now().date())
        if ride_s is not None:
            if s.last_trip_s is None:
                # First read: the trip holds everything since its last reset.
                s.ride_s = float(ride_s)
                s.last_trip_s = float(ride_s)
            elif ride_s >= s.last_trip_s:
                delta = ride_s - s.last_trip_s
                s.ride_s += delta
                s.day_ride_s += delta
                s.last_trip_s = float(ride_s)
            elif trip_km is None or s.last_trip_km is None or trip_km < s.last_trip_km:
                # Ride time and trip distance both lower: the trip was cleared and counts again from 0.
                s.ride_s += ride_s
                s.day_ride_s += ride_s
                s.last_trip_s = float(ride_s)
                s.max_ignore_upto = None
            else:
                # Only the ride time dropped: not a reset; ignore it rather than count the trip twice.
                _LOGGER.debug("Ignoring a drop of the trip ride time without a drop of the trip distance")
        if trip_km is not None:
            s.last_trip_km = trip_km
        if odometer is not None:
            if s.day_start_odometer is None:
                s.day_start_odometer = odometer
            s.last_odometer = odometer
        if trip_max is not None:
            s.last_trip_max = trip_max
            if (
                0 <= trip_max <= MAX_PLAUSIBLE_SPEED_KMH
                and (s.max_ignore_upto is None or trip_max > s.max_ignore_upto)
            ):
                s.max_speed = max(s.max_speed or 0.0, trip_max)
        self._changed()

    @callback
    def async_trip_cleared(self) -> None:
        """The trip was cleared by HA; the next read counts from 0."""
        if self._unloaded:
            return
        s = self.state
        if s.last_trip_s is not None:
            s.last_trip_s = 0.0
        if s.last_trip_km is not None:
            s.last_trip_km = 0.0
        s.max_ignore_upto = None
        self._changed()

    # Automatic writes; attempts stop for the day after MAX_FAILURES_PER_DAY failures.

    def trip_reset_allowed(self, now: datetime) -> bool:
        """Fewer than MAX_FAILURES_PER_DAY failed resets today."""
        return self._failures(now.date().isoformat(), "reset_failures") < MAX_FAILURES_PER_DAY

    def trip_reset_due(self, now: datetime) -> bool:
        """No reset yet today (and not given up for today)."""
        return self.state.trip_reset_day != now.date().isoformat() and self.trip_reset_allowed(now)

    def clock_due(self, now: datetime) -> bool:
        s = self.state
        if self._failures(now.date().isoformat(), "clock_failures") >= MAX_FAILURES_PER_DAY:
            return False
        if s.clock_set_at is None or s.clock_utc_offset is None:
            return True
        offset = now.utcoffset()
        return (
            (offset is not None and offset.total_seconds() != s.clock_utc_offset)
            or now.timestamp() - s.clock_set_at > CLOCK_MAX_AGE_SECONDS
        )

    @callback
    def async_trip_reset_done(self, now: datetime) -> None:
        """The trip was cleared by HA (button or daily option); the next read counts from 0."""
        self.state.trip_reset_day = now.date().isoformat()
        self.async_trip_cleared()

    @callback
    def async_clock_set(self, now: datetime) -> None:
        if self._unloaded:
            return
        offset = now.utcoffset()
        self.state.clock_set_at = now.timestamp()
        self.state.clock_utc_offset = offset.total_seconds() if offset is not None else 0.0
        self._changed()

    @callback
    def async_write_failed(self, now: datetime, which: str) -> None:
        """Count a failed automatic write ("clock_failures" or "reset_failures") for today."""
        if self._unloaded:
            return
        today = now.date().isoformat()
        if self.state.failed_day != today:
            self.state.failed_day = today
            self.state.clock_failures = self.state.reset_failures = 0
        setattr(self.state, which, getattr(self.state, which) + 1)
        self._changed()

    def _failures(self, today: str, which: str) -> int:
        return getattr(self.state, which) if self.state.failed_day == today else 0

    @callback
    def async_reset_max_speed(self) -> None:
        """Set the overall maximum to 0; the current trip's maximum stays ignored until it is exceeded."""
        if self._unloaded:
            return
        self.state.max_speed = 0.0
        self.state.max_ignore_upto = self.state.last_trip_max
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
        if self._unloaded:
            return
        self._store.async_delay_save(lambda: asdict(self.state), SAVE_DELAY_SECONDS)
        for update in list(self._listeners):
            update()
