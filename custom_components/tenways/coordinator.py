"""Read the standard BLE Battery Level characteristic."""
from __future__ import annotations

from datetime import timedelta
import logging

from bleak.exc import BleakError
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from bleak import BleakClient

from .const import BATTERY_UUID, POLL_SECONDS

_LOGGER = logging.getLogger(__name__)


class TenwaysCoordinator(DataUpdateCoordinator[int]):
    """Poll only the standard battery service (no writes)."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        super().__init__(
            hass, _LOGGER, name=f"TENWAYS {address}",
            update_interval=timedelta(seconds=POLL_SECONDS),
        )
        self.address = address

    async def _async_update_data(self) -> int:
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise UpdateFailed("Bike not visible to a connectable Bluetooth adapter")
        try:
            client = await establish_connection(
                BleakClient, device, self.address, max_attempts=2,
                timeout=20.0,
            )
            try:
                raw = bytes(await client.read_gatt_char(BATTERY_UUID))
            finally:
                await client.disconnect()
            if len(raw) != 1 or raw[0] > 100:
                raise UpdateFailed(f"Invalid Battery Level response: {raw.hex()}")
            return raw[0]
        except (BleakError, TimeoutError, OSError) as exc:
            raise UpdateFailed(f"BLE battery read failed: {exc}") from exc
