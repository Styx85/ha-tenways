"""TENWAYS BLE telemetry and diagnostics; writes only on an explicit button press."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import logging
import time

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from tenways_ble import TenwaysBike, TenwaysError, TenwaysProtocolError

from .const import (
    ADVERTISEMENT_MAX_AGE_SECONDS, DOMAIN, BATTERY_UUID, DEVICE_INFO_UUIDS,
    KING_METER_TIMEOUT_SECONDS,
)
from .const import ISSUES_URL, KING_METER_NAME_PREFIXES, TRIP_RESET_DAILY, TRIP_RESET_OFF, TRIP_RESET_RIDE
from .models import model_profile
from .totals import TenwaysTotals

_LOGGER = logging.getLogger(__name__)

# Only describe the bike right now; every other field keeps its last read value.
LIVE_FIELDS = ('speed', 'light', 'remaining_range', 'power', 'rssi')


@dataclass(frozen=True)
class TenwaysData:
    """Values that are actually observed; battery ownership not established."""

    battery_level: int | None = None
    rssi: int | None = None
    bluetooth_visible: bool = False
    last_advertisement: datetime | None = None
    last_successful_read: datetime | None = None
    manufacturer: str | None = None
    model: str | None = None
    firmware: str | None = None
    serial: str | None = None
    traction_battery: int | None = None
    speed: float | None = None
    max_speed: float | None = None
    average_speed: float | None = None
    odometer: float | None = None
    ride_seconds: int | None = None
    trip_distance: float | None = None
    light: bool | None = None
    remaining_range: int | None = None
    power: int | None = None
    raw_0b: int | None = None
    raw_11: int | None = None
    raw_23: int | None = None
    raw_4f: int | None = None


class TenwaysCoordinator(DataUpdateCoordinator[TenwaysData]):
    """Poll the bike through the HA-managed BLE adapter or proxy."""

    def __init__(
        self, hass: HomeAssistant, address: str, poll_seconds: int,
        totals: TenwaysTotals | None = None, name: str | None = None,
        trip_reset: str = TRIP_RESET_OFF, auto_clock: bool = False,
    ) -> None:
        super().__init__(
            hass, _LOGGER, name=f"TENWAYS {address}",
            update_interval=timedelta(seconds=poll_seconds),
        )
        self.address = address
        # Advertised name; picks the model's profile (the app's driver). Updated from advertisements.
        self.model_name = name
        self.trip_reset = trip_reset
        # True until the first read after the bike (re)appeared: a switch-on or a return home.
        self._new_session = True
        self.auto_clock = auto_clock
        self.reload_options: dict = {}
        self._profile_logged: str | None = None
        # Values over all trips and per day; None only in tests that do not need them.
        self.totals = totals
        self._last_successful_read: datetime | None = None
        self._last_advertisement: datetime | None = None
        self._king_meter_info_read = False
        # Last read values, kept while the bike is off or a read fails.
        self._last: dict[str, float | int | str] = {}
        self._absent = True
        self._expiry: CALLBACK_TYPE | None = None
        # One BLE session at a time: a poll and a clock sync must not share the bike.
        self._ble_lock = asyncio.Lock()

    @property
    def profile(self):
        return model_profile(self.model_name)

    def _bike(self, client: BleakClient) -> TenwaysBike:
        profile = self.profile
        if self._profile_logged != profile.name:
            self._profile_logged = profile.name
            if not profile.supported:
                _LOGGER.warning(
                    "%s (%s) is not supported: %s. A debug log or an HCI capture of the TENWAYS app "
                    "could help to add it: %s", self.model_name, self.address, profile.reason, ISSUES_URL,
                )
            elif not profile.tested:
                _LOGGER.warning(
                    "%s (%s) uses the untested %s profile. Please report whether the values match the "
                    "display, with a diagnostics download: %s", self.model_name, self.address, profile.name, ISSUES_URL,
                )
        return TenwaysBike(client, name=self.model_name, profile=profile)

    async def _async_update_data(self) -> TenwaysData:
        info = bluetooth.async_last_service_info(self.hass, self.address, connectable=True)
        # The advertised name decides the model, also an unsupported one (so its warning is logged).
        if info is not None and info.name and info.name != self.model_name and (
            info.name.startswith(KING_METER_NAME_PREFIXES) or not model_profile(info.name).supported
        ):
            self.model_name = info.name
        now = time.monotonic()
        # BluetoothServiceInfoBleak.time is monotonic seconds, NOT Unix time.
        age = max(0.0, now - info.time) if info is not None else None
        visible = age is not None and age < ADVERTISEMENT_MAX_AGE_SECONDS
        rssi = info.rssi if visible and info is not None else None
        if age is not None:
            self._last_advertisement = datetime.now(timezone.utc) - timedelta(seconds=age)
        fallback = TenwaysData(
            rssi=rssi, bluetooth_visible=visible,
            last_advertisement=self._last_advertisement,
            last_successful_read=self._last_successful_read,
            **self._last,
        )
        device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
        if device is None or not visible:
            self._absent = True
            self._new_session = True
            return fallback
        self._absent = False

        async with self._ble_lock:
            client: BleakClient | None = None
            read_ok = False
            try:
                client = await establish_connection(
                    BleakClient, device, self.address, max_attempts=2, timeout=20.0,
                )
                if client.services.get_characteristic(BATTERY_UUID):
                    try:
                        raw = bytes(await asyncio.wait_for(client.read_gatt_char(BATTERY_UUID), 8))
                        if len(raw) == 1 and raw[0] <= 100:
                            self._last['battery_level'] = raw[0]
                            read_ok = True
                    except Exception as exc:
                        _LOGGER.debug('Standard battery read unavailable: %s', exc)
                bike = self._bike(client)
                try:
                    telemetry = await asyncio.wait_for(
                        self._async_read_king_meter(bike), KING_METER_TIMEOUT_SECONDS,
                    )
                except TimeoutError:
                    _LOGGER.debug('King Meter exchange timed out (%s)', self.address)
                    telemetry = {}
                read_ok = read_ok or bool(telemetry)
                live = self._account(telemetry)
                published = False

                def publish_read() -> None:
                    """Show the values as read, before a reset clears the trip: the ride then
                    appears in the trip sensors' history and long-term statistics."""
                    nonlocal published
                    published = True
                    self._last_successful_read = datetime.now(timezone.utc)
                    self.data = TenwaysData(
                        rssi=rssi, bluetooth_visible=True, **live,
                        last_advertisement=self._last_advertisement,
                        last_successful_read=self._last_successful_read,
                        **self._last,
                    )
                    self.async_update_listeners()

                if telemetry:
                    # Right after the read, in the same connection: the bike may leave range soon.
                    try:
                        await self._async_automatic_writes(bike, publish_read)
                    except Exception:  # never lose the read over an automatic write
                        _LOGGER.exception("Automatic write to %s failed", self.address)
                # Optional reads only when advertised as present in the GATT table.
                for key, uuid in DEVICE_INFO_UUIDS.items():
                    if key in self._last:
                        continue
                    if client.services.get_characteristic(uuid) is None:
                        continue
                    try:
                        value = bytes(await asyncio.wait_for(client.read_gatt_char(uuid), 3))
                        decoded = value.decode("utf-8", errors="replace").strip("\x00 ")
                        if decoded:
                            self._last[key] = decoded[:100]
                    except (Exception, asyncio.CancelledError) as exc:
                        if isinstance(exc, asyncio.CancelledError):
                            raise
                        _LOGGER.debug("Optional TENWAYS %s characteristic not readable: %s", key, exc)
                if read_ok and not published:
                    # Only a valid reply dates the kept values; a failed status read must not.
                    self._last_successful_read = datetime.now(timezone.utc)
                return TenwaysData(
                    rssi=rssi, bluetooth_visible=True, **live,
                    last_advertisement=self._last_advertisement,
                    last_successful_read=self._last_successful_read,
                    **self._last,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Retain advertisement diagnostics even if GATT is busy or fails.
                _LOGGER.debug("TENWAYS read failed (%s): %s", self.address, exc)
                return fallback
            finally:
                if client is not None and client.is_connected:
                    try:
                        await asyncio.wait_for(client.disconnect(), 5)
                    except Exception as exc:
                        _LOGGER.debug("TENWAYS disconnect failed: %s", exc)

    @callback
    def async_handle_advertisement(
        self, _info: bluetooth.BluetoothServiceInfoBleak, _change: bluetooth.BluetoothChange
    ) -> None:
        """Poll right away when the bike reappears; expire live values when it goes quiet."""
        self._last_advertisement = datetime.now(timezone.utc)
        if self._expiry is not None:
            self._expiry()
        self._expiry = async_call_later(self.hass, ADVERTISEMENT_MAX_AGE_SECONDS, self._async_expire_live)
        if self._absent:
            self._absent = False
            self.hass.async_create_task(self.async_request_refresh())

    async def async_set_clock(self, moment: datetime) -> None:
        """Set the bike's clock to ``moment`` (local wall-clock fields). Needs the bike in range."""
        await self._async_write(lambda bike: bike.set_clock(moment), "clock_failed")
        _LOGGER.info("Set the clock of %s to %s", self.address, moment)
        if self.totals is not None:
            self.totals.async_clock_set(moment)

    async def _async_automatic_writes(self, bike: TenwaysBike, publish_read=None) -> None:
        """The options' clock sync and trip reset; a failure is retried on a later read."""
        totals = self.totals
        new_session, self._new_session = self._new_session, False
        if totals is None or not (self.auto_clock or self.trip_reset != TRIP_RESET_OFF):
            return
        now = dt_util.now()
        # The trip first, right after the read: nothing ridden in between can be lost.
        await self._async_automatic_trip_reset(bike, now, new_session, publish_read)
        if self.auto_clock and totals.clock_due(now):
            try:
                await asyncio.wait_for(bike.set_clock(now), KING_METER_TIMEOUT_SECONDS)
            except (TenwaysError, TenwaysProtocolError, BleakError, OSError, TimeoutError) as exc:
                _LOGGER.warning("Setting the clock of %s failed, will retry on a later read: %s", self.address, exc)
                totals.async_write_failed(now, "clock_failures")
            else:
                _LOGGER.info("Set the clock of %s to %s (automatic)", self.address, now)
                totals.async_clock_set(now)

    async def _async_automatic_trip_reset(
        self, bike: TenwaysBike, now: datetime, new_session: bool, publish_read=None,
    ) -> None:
        totals = self.totals
        assert totals is not None
        if not self._trip_reset_wanted(now, new_session):
            return
        # The read above already took the trip into HA's totals. An empty trip needs no write,
        # but counts as done, so a ride later today is not cleared when it is read.
        if not (self._last.get('trip_distance') or self._last.get('ride_seconds')):
            totals.async_trip_reset_done(now)
            return
        if publish_read is not None:
            publish_read()
        try:
            await asyncio.wait_for(bike.reset_trip(), KING_METER_TIMEOUT_SECONDS)
        except (TenwaysError, TenwaysProtocolError, BleakError, OSError, TimeoutError) as exc:
            _LOGGER.warning("Clearing the trip of %s failed, will retry on a later read: %s", self.address, exc)
            totals.async_write_failed(now, "reset_failures")
            self._new_session = new_session  # try again on the next read of this session
        else:
            _LOGGER.info("Cleared the trip of %s (%s)", self.address, self.trip_reset)
            totals.async_trip_reset_done(now)
            # The values were read just before; show the cleared trip without waiting for the next poll.
            for key in ('trip_distance', 'ride_seconds', 'max_speed', 'average_speed'):
                if key in self._last:
                    self._last[key] = 0

    def _trip_reset_wanted(self, now: datetime, new_session: bool) -> bool:
        totals = self.totals
        assert totals is not None
        if self.trip_reset == TRIP_RESET_DAILY:
            return totals.trip_reset_due(now)
        # Per ride: the first read after the bike appeared (switched on, or back in range).
        return self.trip_reset == TRIP_RESET_RIDE and new_session and totals.trip_reset_allowed(now)

    def _account(self, telemetry: dict) -> dict:
        """Keep a status read's values and add it to the totals; returns the live values."""
        live = {key: telemetry.pop(key, None) for key in LIVE_FIELDS if key != 'rssi'}
        self._last.update(telemetry)
        if telemetry and self.totals is not None:
            self.totals.async_update(
                telemetry.get('ride_seconds'), telemetry.get('odometer'), telemetry.get('max_speed'),
                telemetry.get('trip_distance'),
            )
        return live

    async def async_reset_trip(self) -> None:
        """Read the trip into HA, then clear it (distance, time, max and average speed), in one connection."""

        async def read_then_clear(bike: TenwaysBike) -> None:
            self._account(await self._async_read_king_meter(bike))
            await bike.reset_trip()

        await self._async_write(read_then_clear, "trip_reset_failed")
        _LOGGER.info("Cleared the trip of %s", self.address)
        if self.totals is not None:
            self.totals.async_trip_reset_done(dt_util.now())
        await self.async_request_refresh()

    async def _async_write(self, send, failed_key: str) -> None:
        """One explicit write in its own BLE session; errors are reported on the press."""
        info = bluetooth.async_last_service_info(self.hass, self.address, connectable=True)
        device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
        visible = info is not None and time.monotonic() - info.time < ADVERTISEMENT_MAX_AGE_SECONDS
        if device is None or not visible:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="bike_not_in_range")
        async with self._ble_lock:
            client: BleakClient | None = None
            try:
                client = await establish_connection(
                    BleakClient, device, self.address, max_attempts=2, timeout=20.0,
                )
                await asyncio.wait_for(send(self._bike(client)), KING_METER_TIMEOUT_SECONDS)
            except (TenwaysError, TenwaysProtocolError, BleakError, OSError, TimeoutError) as exc:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key=failed_key,
                    translation_placeholders={"error": str(exc) or type(exc).__name__},
                ) from exc
            finally:
                if client is not None and client.is_connected:
                    try:
                        await asyncio.wait_for(client.disconnect(), 5)
                    except Exception as exc:
                        _LOGGER.debug("TENWAYS disconnect failed: %s", exc)

    @callback
    def _async_expire_live(self, _now: datetime) -> None:
        """No advertisement for a while: live values and visibility lapse before the next poll."""
        self._expiry = None
        self._absent = True
        self._new_session = True
        if self.data is not None:
            self.async_set_updated_data(replace(
                self.data, speed=None, light=None, remaining_range=None, power=None, rssi=None,
                bluetooth_visible=False, last_advertisement=self._last_advertisement,
            ))

    async def async_shutdown(self) -> None:
        if self._expiry is not None:
            self._expiry()
            self._expiry = None
        await super().async_shutdown()

    async def _async_read_king_meter(self, bike: TenwaysBike) -> dict[str, float | int | None]:
        """Query the proprietary King Meter service, as the TENWAYS app does."""
        if not bike.supports_protocol():
            return {}
        if not self._king_meter_info_read:
            try:
                device_info = await bike.read_device_info()
            except (TenwaysError, TenwaysProtocolError, TimeoutError) as exc:
                _LOGGER.debug('King Meter device info unavailable (%s): %s', self.address, exc)
            else:
                self._king_meter_info_read = True
                # The King Meter firmware takes precedence over Device Information.
                if device_info.firmware:
                    self._last['firmware'] = device_info.firmware
                if device_info.serial:
                    self._last['serial'] = device_info.serial
        try:
            status = await bike.read_status()
        except (TenwaysError, TenwaysProtocolError, TimeoutError) as exc:
            _LOGGER.debug('Longtail telemetry unavailable (%s): %s', self.address, exc)
            return {}
        return {
            'traction_battery': status.battery_percent,
            'speed': status.speed_kmh,
            'max_speed': status.max_speed_kmh,
            'average_speed': status.average_speed_kmh,
            'odometer': status.odometer_km,
            'ride_seconds': status.ride_time_s,
            'trip_distance': status.trip_km,
            # Field 0x11 follows the light switch (observed in HA, 0 = off).
            'light': status.light_on,
            'remaining_range': status.remaining_range_km,
            'power': status.power_w,
            'raw_0b': status.raw_0b,
            'raw_11': status.raw_11,
            'raw_23': status.raw_23,
            'raw_4f': status.raw_4f,
        }
