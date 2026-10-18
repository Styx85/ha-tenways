"""Coordinator against a simulated bike replaying frames from the HCI capture."""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from bleak import BleakClient
import pytest
from tenways_ble.const import TENWAYS_NOTIFY_UUID, TENWAYS_WRITE_UUID
from tenways_ble.protocol import INFO_REQUEST, STATUS_REQUEST

from custom_components.tenways.coordinator import TenwaysCoordinator

ADDRESS = "E8:88:6C:31:B3:0D"
STATUS_REPLY = bytes.fromhex(
    "62 00 30 0b 06 02 00 00 07 02 01 bf 08 02 00 7e 09 04 00 00 04 b1 11 01 00"
    " 0a 04 00 00 85 44 0b 02 02 8f 0c 04 00 00 04 b1 0f 01 44 23 02 00 00 4f 01 01 83 d3 45"
)
INFO_REPLY = bytes.fromhex(
    "62 00 2d 04 04 03 02 14 10 05 10 30 30 30 30 30 30 30 30 35 33 30 36 30 30 34 35"
    " 4f 01 01 70 10 59 4a 32 35 30 33 31 39 41 30 30 32 33 34 30 00 52 88 45"
)


class FakeBike(BleakClient):
    """Answers recorded queries with 20-byte notifications (default MTU)."""

    def __init__(self, replies=None, king_meter=True):
        self.replies = {STATUS_REQUEST: STATUS_REPLY, INFO_REQUEST: INFO_REPLY} if replies is None else replies
        self.writes: list[bytes] = []
        self.connected = True
        self._notify = None
        chars = (TENWAYS_WRITE_UUID, TENWAYS_NOTIFY_UUID) if king_meter else ()
        self._services = SimpleNamespace(get_characteristic=lambda uuid: uuid if uuid in chars else None)

    @property
    def is_connected(self):
        return self.connected

    @property
    def services(self):
        return self._services

    async def start_notify(self, uuid, callback, **kwargs):
        self._notify = callback

    async def stop_notify(self, uuid):
        self._notify = None

    async def write_gatt_char(self, uuid, data, response=None):
        self.writes.append(bytes(data))
        reply = self.replies.get(bytes(data), b"")
        loop = asyncio.get_running_loop()
        for i in range(0, len(reply), 20):
            loop.call_soon(self._notify, None, bytearray(reply[i:i + 20]))

    async def disconnect(self):
        self.connected = False


@pytest.fixture
def advertising():
    info = SimpleNamespace(time=0.0, rssi=-60)
    with patch("custom_components.tenways.coordinator.bluetooth.async_last_service_info", return_value=info), \
         patch("custom_components.tenways.coordinator.time.monotonic", return_value=1.0), \
         patch("custom_components.tenways.coordinator.bluetooth.async_ble_device_from_address", return_value=object()):
        yield


async def _refresh(hass, *bikes):
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300)
    results = []
    with patch("custom_components.tenways.coordinator.establish_connection", side_effect=list(bikes)):
        for _ in bikes:
            await coordinator.async_refresh()
            results.append(coordinator.data)
    return results


async def test_info_once_then_status(hass, advertising):
    first_bike, second_bike = FakeBike(), FakeBike()
    first, second = await _refresh(hass, first_bike, second_bike)
    assert first.traction_battery == 68
    assert first.odometer == 120.1
    assert first.trip_distance == 120.1
    assert first.max_speed == 44.7
    assert first.average_speed == 12.6
    assert first.ride_seconds == 34116
    assert first.speed == 0.0
    assert first.raw_0b == 655
    assert first.firmware == "2.20.16"
    assert first.serial == "YJ250319A002340"
    assert second.serial == "YJ250319A002340"
    assert first_bike.writes == [INFO_REQUEST, STATUS_REQUEST]
    assert second_bike.writes == [STATUS_REQUEST]
    assert not first_bike.connected and not second_bike.connected


async def test_missing_info_reply_does_not_block_status(hass, advertising):
    (data,) = await _refresh(hass, FakeBike(replies={STATUS_REQUEST: STATUS_REPLY}))
    assert data.traction_battery == 68
    assert data.serial is None


async def test_unanswered_status_yields_no_telemetry(hass, advertising):
    (data,) = await _refresh(hass, FakeBike(replies={INFO_REQUEST: INFO_REPLY}))
    assert data.traction_battery is None
    assert data.bluetooth_visible


async def test_corrupted_status_yields_no_telemetry(hass, advertising):
    bad = bytearray(STATUS_REPLY)
    bad[12] ^= 1
    (data,) = await _refresh(hass, FakeBike(replies={STATUS_REQUEST: bytes(bad), INFO_REQUEST: INFO_REPLY}))
    assert data.traction_battery is None


async def test_device_without_king_meter_service(hass, advertising):
    bike = FakeBike(king_meter=False)
    (data,) = await _refresh(hass, bike)
    assert data.traction_battery is None
    assert bike.writes == []


async def test_bike_gone_clears_telemetry(hass):
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300)
    with patch("custom_components.tenways.coordinator.bluetooth.async_last_service_info", return_value=None), \
         patch("custom_components.tenways.coordinator.bluetooth.async_ble_device_from_address", return_value=None), \
         patch("custom_components.tenways.coordinator.establish_connection") as connect:
        await coordinator.async_refresh()
    assert coordinator.data.traction_battery is None
    assert not coordinator.data.bluetooth_visible
    connect.assert_not_called()


async def test_connection_failure_keeps_diagnostics(hass, advertising):
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300)
    with patch("custom_components.tenways.coordinator.establish_connection", side_effect=TimeoutError):
        await coordinator.async_refresh()
    assert coordinator.data.traction_battery is None
    assert coordinator.data.rssi == -60
