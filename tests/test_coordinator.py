"""Coordinator against a simulated bike replaying frames from the HCI capture."""
import asyncio
from datetime import timedelta
import time
from types import SimpleNamespace
from unittest.mock import patch

from bleak import BleakClient
import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from tenways_ble.const import TENWAYS_NOTIFY_UUID, TENWAYS_WRITE_UUID
from tenways_ble.protocol import CMD_STATUS, INFO_REQUEST, STATUS_REQUEST, TYPE_READ, build_frame

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
    # Do not patch time.monotonic: the event loop clock depends on it.
    info = SimpleNamespace(time=time.monotonic(), rssi=-60)
    with patch("custom_components.tenways.coordinator.bluetooth.async_last_service_info", return_value=info), \
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
    assert first.light is False
    assert first.remaining_range is None  # 655 at assist level 0 means none
    assert first.power == 0
    assert first.raw_0b == 655
    assert first.firmware == "2.20.16"
    assert first.serial == "YJ250319A002340"
    assert second.serial == "YJ250319A002340"
    assert first_bike.writes == [INFO_REQUEST, STATUS_REQUEST]
    assert second_bike.writes == [STATUS_REQUEST]
    assert not first_bike.connected and not second_bike.connected


def _status_with_0b(value: int) -> bytes:
    payload = STATUS_REPLY[4:-3].replace(bytes.fromhex("0b 02 02 8f"), bytes([0x0B, 2]) + value.to_bytes(2, "big"))
    return build_frame(TYPE_READ, CMD_STATUS, payload)


async def test_odometer_and_trip_come_from_different_fields(hass, advertising):
    # 0x0C is the odometer, 0x09 the trip; they only differ once the trip is reset.
    reply = build_frame(TYPE_READ, CMD_STATUS, STATUS_REPLY[4:-3].replace(
        bytes.fromhex("09 04 00 00 04 b1"), bytes.fromhex("09 04 00 00 00 64")))
    (data,) = await _refresh(hass, FakeBike(replies={STATUS_REQUEST: reply, INFO_REQUEST: INFO_REPLY}))
    assert (data.odometer, data.trip_distance) == (120.1, 10.0)


def test_status_reply_rebuilds():
    assert _status_with_0b(655) == STATUS_REPLY


@pytest.mark.parametrize(("raw", "range_km"), [(60, 60), (43, 43), (128, None), (655, None), (0x8000, None)])
async def test_remaining_range_follows_app_rule(hass, advertising, raw, range_km):
    (data,) = await _refresh(hass, FakeBike(replies={STATUS_REQUEST: _status_with_0b(raw), INFO_REQUEST: INFO_REPLY}))
    assert (data.remaining_range, data.raw_0b) == (range_km, raw)


@pytest.mark.parametrize(("raw", "power"), [(250, 250), (3000, 3000), (3001, None)])
async def test_power_ignores_values_above_3000(hass, advertising, raw, power):
    reply = build_frame(TYPE_READ, CMD_STATUS, STATUS_REPLY[4:-3].replace(
        bytes.fromhex("23 02 00 00"), bytes([0x23, 2]) + raw.to_bytes(2, "big")))
    (data,) = await _refresh(hass, FakeBike(replies={STATUS_REQUEST: reply, INFO_REQUEST: INFO_REPLY}))
    assert data.power == power


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


async def test_bike_switched_off_keeps_last_values(hass, advertising):
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300)
    with patch("custom_components.tenways.coordinator.establish_connection", return_value=FakeBike()):
        await coordinator.async_refresh()
    read_at = coordinator.data.last_successful_read
    seen_at = coordinator.data.last_advertisement
    with patch("custom_components.tenways.coordinator.bluetooth.async_last_service_info", return_value=None), \
         patch("custom_components.tenways.coordinator.bluetooth.async_ble_device_from_address", return_value=None):
        await coordinator.async_refresh()
    data = coordinator.data
    assert (data.odometer, data.trip_distance, data.ride_seconds) == (120.1, 120.1, 34116)
    assert (data.max_speed, data.average_speed) == (44.7, 12.6)
    assert data.traction_battery == 68
    assert data.raw_0b == 655
    assert data.serial == "YJ250319A002340"
    assert (data.last_successful_read, data.last_advertisement) == (read_at, seen_at)
    assert data.speed is None and data.light is None and data.rssi is None
    assert data.remaining_range is None and data.power is None
    assert not data.bluetooth_visible


async def test_failed_read_keeps_last_values(hass, advertising):
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300)
    with patch("custom_components.tenways.coordinator.establish_connection", side_effect=[FakeBike(), TimeoutError]):
        await coordinator.async_refresh()
        read_at = coordinator.data.last_successful_read
        await coordinator.async_refresh()
    assert coordinator.data.odometer == 120.1
    assert coordinator.data.traction_battery == 68
    assert coordinator.data.last_successful_read == read_at
    assert coordinator.data.speed is None


async def test_unanswered_status_keeps_last_values(hass, advertising):
    first, second = await _refresh(hass, FakeBike(), FakeBike(replies={}))
    assert second.traction_battery == 68
    assert second.speed is None and second.light is None


async def test_reappearing_bike_triggers_refresh(hass):
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300)
    with patch.object(coordinator, "async_request_refresh") as refresh:
        coordinator.async_handle_advertisement(None, None)
        coordinator.async_handle_advertisement(None, None)
        await hass.async_block_till_done()
    assert refresh.call_count == 1


async def test_visible_bike_advertisements_do_not_trigger_refresh(hass, advertising):
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300)
    with patch("custom_components.tenways.coordinator.establish_connection", return_value=FakeBike()):
        await coordinator.async_refresh()
    with patch.object(coordinator, "async_request_refresh") as refresh:
        coordinator.async_handle_advertisement(None, None)
        await hass.async_block_till_done()
    refresh.assert_not_called()


async def test_failed_status_read_does_not_date_the_values(hass, advertising):
    first, second = await _refresh(hass, FakeBike(), FakeBike(replies={}))
    assert first.last_successful_read is not None
    assert second.traction_battery == 68  # kept
    assert second.last_successful_read == first.last_successful_read  # but not re-dated


async def test_never_read_has_no_read_time(hass, advertising):
    (data,) = await _refresh(hass, FakeBike(replies={}))
    assert data.last_successful_read is None


class HangingBike(FakeBike):
    async def write_gatt_char(self, uuid, data, response=None):
        await asyncio.sleep(3600)


async def test_stalled_exchange_is_cut_off(hass, advertising):
    with patch("custom_components.tenways.coordinator.KING_METER_TIMEOUT_SECONDS", 0.05):
        (data,) = await _refresh(hass, HangingBike())
    assert data.traction_battery is None
    assert data.last_successful_read is None
    assert not data.speed


async def test_live_values_expire_without_advertisements(hass, advertising):
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300)
    with patch("custom_components.tenways.coordinator.establish_connection", return_value=FakeBike()):
        await coordinator.async_refresh()
    assert coordinator.data.bluetooth_visible and coordinator.data.speed == 0.0
    coordinator.async_handle_advertisement(None, None)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=200))
    await hass.async_block_till_done()
    data = coordinator.data
    assert not data.bluetooth_visible
    assert data.speed is None and data.light is None and data.rssi is None
    assert data.traction_battery == 68 and data.odometer == 120.1  # totals stay
    # The bike coming back triggers a poll again.
    with patch.object(coordinator, "async_request_refresh") as refresh:
        coordinator.async_handle_advertisement(None, None)
        await hass.async_block_till_done()
    assert refresh.call_count == 1
    await coordinator.async_shutdown()
