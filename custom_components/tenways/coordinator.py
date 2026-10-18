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
    ADVERTISEMENT_MAX_AGE_SECONDS, BATTERY_UUID, DEVICE_INFO_UUIDS,
)

_LOGGER = logging.getLogger(__name__)

TOTAL_FIELDS = ('odometer', 'trip_distance', 'ride_seconds', 'max_speed', 'average_speed')


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
        self._cached_info: dict[str, str] = {}
        self._king_meter_info_read = False
        # Totals stay valid while the bike is off; live values do not.
        self._totals: dict[str, float | int] = {}
        self._absent = True

    async def _async_update_data(self) -> TenwaysData:
        info = bluetooth.async_last_service_info(self.hass, self.address, connectable=True)
        now = time.monotonic()
        # BluetoothServiceInfoBleak.time is monotonic seconds, NOT Unix time.
        age = max(0.0, now - info.time) if info is not None else None
        visible = age is not None and age < ADVERTISEMENT_MAX_AGE_SECONDS
        rssi = info.rssi if visible and info is not None else None
        seen_at = (
            datetime.now(timezone.utc) - timedelta(seconds=age)
            if age is not None else None
        )
        fallback = TenwaysData(
            battery_level=None, rssi=rssi, bluetooth_visible=visible,
            last_advertisement=seen_at,
            last_successful_read=self._last_successful_read,
            **self._cached_info, **self._totals,
        )
        device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
        if device is None or not visible:
            # Do not retain a stale battery value when the bicycle disappears.
            self._absent = True
            return fallback
        self._absent = False

        client: BleakClient | None = None
        try:
            client = await establish_connection(
                BleakClient, device, self.address, max_attempts=2, timeout=20.0,
            )
            raw = b''
            if client.services.get_characteristic(BATTERY_UUID):
                try:
                    raw = bytes(await asyncio.wait_for(client.read_gatt_char(BATTERY_UUID), 8))
                    if len(raw) != 1 or raw[0] > 100:
                        raw = b''
                except Exception as exc:
                    _LOGGER.debug('Standard battery read unavailable: %s', exc)
            telemetry = await self._async_read_king_meter(TenwaysBike(client))
            if telemetry:
                self._totals = {key: telemetry[key] for key in TOTAL_FIELDS}
            # Optional reads only when advertised as present in the GATT table.
            for key, uuid in DEVICE_INFO_UUIDS.items():
                if key in self._cached_info:
                    continue
                if client.services.get_characteristic(uuid) is None:
                    continue
                try:
                    value = bytes(await asyncio.wait_for(client.read_gatt_char(uuid), 3))
                    decoded = value.decode("utf-8", errors="replace").strip("\x00 ")
                    if decoded:
                        self._cached_info[key] = decoded[:100]
                except (Exception, asyncio.CancelledError) as exc:
                    if isinstance(exc, asyncio.CancelledError):
                        raise
                    _LOGGER.debug("Optional TENWAYS %s characteristic not readable: %s", key, exc)
            self._last_successful_read = datetime.now(timezone.utc)
            return TenwaysData(
                battery_level=raw[0] if raw else None, rssi=rssi, bluetooth_visible=True,
                last_advertisement=seen_at,
                last_successful_read=self._last_successful_read,
                **self._cached_info, **(telemetry or self._totals),
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
                    self._cached_info['firmware'] = device_info.firmware
                if device_info.serial:
                    self._cached_info['serial'] = device_info.serial
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
            'raw_0b': status.raw_0b,
            'raw_11': status.raw_11,
            'raw_23': status.raw_23,
            'raw_4f': status.raw_4f,
        }
