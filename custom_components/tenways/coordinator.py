"""Read-only TENWAYS BLE telemetry and diagnostics."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import time

from bleak import BleakClient
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from tenways_ble import TenwaysBike, TenwaysError, TenwaysProtocolError

from .const import (
    ADVERTISEMENT_MAX_AGE_SECONDS, BATTERY_UUID, DEVICE_INFO_UUIDS, MAX_POWER_W,
)

_LOGGER = logging.getLogger(__name__)

# Only describe the bike right now; every other field keeps its last read value.
LIVE_FIELDS = ('speed', 'light', 'remaining_range', 'power', 'rssi')


def _remaining_range(raw: int | None) -> int | None:
    """Field 0x0B as the app reads it: any byte >= 0x80 (655 at assist level 0) means none."""
    if raw is None or max(raw >> 8, raw & 0xFF) >= 0x80:
        return None
    return raw


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

    def __init__(self, hass: HomeAssistant, address: str, poll_seconds: int) -> None:
        super().__init__(
            hass, _LOGGER, name=f"TENWAYS {address}",
            update_interval=timedelta(seconds=poll_seconds),
        )
        self.address = address
        self._last_successful_read: datetime | None = None
        self._last_advertisement: datetime | None = None
        self._king_meter_info_read = False
        # Last read values, kept while the bike is off or a read fails.
        self._last: dict[str, float | int | str] = {}
        self._absent = True

    async def _async_update_data(self) -> TenwaysData:
        info = bluetooth.async_last_service_info(self.hass, self.address, connectable=True)
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
            return fallback
        self._absent = False

        client: BleakClient | None = None
        try:
            client = await establish_connection(
                BleakClient, device, self.address, max_attempts=2, timeout=20.0,
            )
            if client.services.get_characteristic(BATTERY_UUID):
                try:
                    raw = bytes(await asyncio.wait_for(client.read_gatt_char(BATTERY_UUID), 8))
                    if len(raw) == 1 and raw[0] <= 100:
                        self._last['battery_level'] = raw[0]
                except Exception as exc:
                    _LOGGER.debug('Standard battery read unavailable: %s', exc)
            telemetry = await self._async_read_king_meter(TenwaysBike(client))
            live = {key: telemetry.pop(key, None) for key in LIVE_FIELDS if key != 'rssi'}
            self._last.update(telemetry)
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
        """Poll right away when the bike reappears instead of waiting an interval."""
        if self._absent:
            self._absent = False
            self.hass.async_create_task(self.async_request_refresh())

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
            'light': None if status.raw_11 is None else status.raw_11 != 0,
            'remaining_range': _remaining_range(status.raw_0b),
            'power': status.raw_23 if status.raw_23 is not None and status.raw_23 <= MAX_POWER_W else None,
            'raw_0b': status.raw_0b,
            'raw_11': status.raw_11,
            'raw_23': status.raw_23,
            'raw_4f': status.raw_4f,
        }
