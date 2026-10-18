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
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .protocol import STATUS_REQUEST, WRITE_UUID, NOTIFY_UUID, LONGTAIL_ADDRESS, decode_status

from .const import (
    ADVERTISEMENT_MAX_AGE_SECONDS, BATTERY_UUID, DEVICE_INFO_UUIDS, POLL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


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
    traction_battery: int | None = None
    max_speed: float | None = None
    average_speed: float | None = None
    odometer: float | None = None
    ride_seconds: int | None = None
    trip_distance: float | None = None


class TenwaysCoordinator(DataUpdateCoordinator[TenwaysData]):
    """Poll standard GATT fields through the HA-managed BLE adapter."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        super().__init__(
            hass, _LOGGER, name=f"TENWAYS {address}",
            update_interval=timedelta(seconds=POLL_SECONDS),
        )
        self.address = address
        self._last_successful_read: datetime | None = None
        self._cached_info: dict[str, str] = {}

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
            **self._cached_info,
        )
        device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
        if device is None or not visible:
            # Do not retain a stale battery value when the bicycle disappears.
            return fallback

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
            telemetry = {}
            if (client.services.get_characteristic(WRITE_UUID) is not None
                    and client.services.get_characteristic(NOTIFY_UUID) is not None
                    and self.address.upper() == LONGTAIL_ADDRESS):
                # Request/response with notify setup before the single recorded query.
                pending: asyncio.Future[dict[str, float | int]] = self.hass.loop.create_future()
                def on_notify(_sender, payload: bytearray) -> None:
                    if pending.done():
                        return
                    try:
                        parsed = decode_status(bytes(payload))
                    except ValueError:
                        return
                    pending.set_result(parsed)
                try:
                    await client.start_notify(NOTIFY_UUID, on_notify)
                    await client.write_gatt_char(WRITE_UUID, STATUS_REQUEST, response=False)
                    telemetry = await asyncio.wait_for(pending, timeout=8.0)
                except Exception as exc:
                    _LOGGER.debug('Longtail telemetry unavailable (%s): %s', self.address, exc)
                finally:
                    try:
                        await client.stop_notify(NOTIFY_UUID)
                    except Exception:
                        pass
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
                **self._cached_info, **telemetry,
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
