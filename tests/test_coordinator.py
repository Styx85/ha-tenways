"""Coordinator against a simulated bike replaying frames from the HCI capture."""
import asyncio
from datetime import datetime, timedelta
import time
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from unittest.mock import patch

from bleak import BleakClient
import pytest
from homeassistant.exceptions import HomeAssistantError
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
    info = SimpleNamespace(time=time.monotonic(), rssi=-60, name="Longtail Duo")
    with patch("custom_components.tenways.coordinator.bluetooth.async_last_service_info", return_value=info), \
         patch("custom_components.tenways.coordinator.bluetooth.async_ble_device_from_address", return_value=object()):
        yield


async def _refresh(hass, *bikes):
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300, advertised_name="Longtail Duo")
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


CLOCK_WRITE = bytes.fromhex("63 00 0a 01 3c 07 02 1a 0a 12 0e 20 12 ff f3 45")
CLOCK_REPLY = bytes.fromhex("63 00 09 01 3c 07 02 1a 12 0e 20 12 ee ed 45")
MOMENT = datetime(2026, 10, 18, 14, 32, 18)


async def test_set_clock_sends_the_app_frame_and_disconnects(hass, advertising):
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300, advertised_name="Longtail Duo")
    bike = FakeBike(replies={CLOCK_WRITE: CLOCK_REPLY})
    with patch("custom_components.tenways.coordinator.establish_connection", return_value=bike):
        await coordinator.async_set_clock(MOMENT)
    assert bike.writes == [CLOCK_WRITE]
    assert not bike.connected


CLEAR_TRIP = bytes.fromhex("63 00 04 01 2d 01 01 63 e8 45")


async def test_reset_trip_sends_the_app_frame_and_disconnects(hass, advertising):
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300, advertised_name="Longtail Duo")
    bike = FakeBike(replies={STATUS_REQUEST: STATUS_REPLY, INFO_REQUEST: INFO_REPLY, CLEAR_TRIP: CLEAR_TRIP})
    with patch("custom_components.tenways.coordinator.establish_connection", return_value=bike), \
         patch.object(TenwaysCoordinator, "async_request_refresh") as refresh:
        await coordinator.async_reset_trip()
    assert bike.writes == [INFO_REQUEST, STATUS_REQUEST, CLEAR_TRIP]  # read into HA first
    assert not bike.connected
    refresh.assert_awaited_once()


async def test_reset_trip_without_acknowledgement_is_reported(hass, advertising):
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300, advertised_name="Longtail Duo")
    bike = FakeBike(replies={})
    with patch("custom_components.tenways.coordinator.establish_connection", return_value=bike), \
         patch("custom_components.tenways.coordinator.KING_METER_TIMEOUT_SECONDS", 0.05), \
         patch.object(TenwaysCoordinator, "async_request_refresh") as refresh:
        with pytest.raises(HomeAssistantError):
            await coordinator.async_reset_trip()
    assert not bike.connected
    refresh.assert_not_called()  # no acknowledgement, no refresh


async def test_set_clock_needs_the_bike_in_range(hass):
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300, advertised_name="Longtail Duo")
    with patch("custom_components.tenways.coordinator.bluetooth.async_last_service_info", return_value=None), \
         patch("custom_components.tenways.coordinator.bluetooth.async_ble_device_from_address", return_value=None), \
         patch("custom_components.tenways.coordinator.establish_connection") as connect:
        with pytest.raises(HomeAssistantError):
            await coordinator.async_set_clock(MOMENT)
    connect.assert_not_called()


async def test_set_clock_without_acknowledgement_is_reported(hass, advertising):
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300, advertised_name="Longtail Duo")
    bike = FakeBike(replies={})
    with patch("custom_components.tenways.coordinator.establish_connection", return_value=bike), \
         patch("custom_components.tenways.coordinator.KING_METER_TIMEOUT_SECONDS", 0.05):
        with pytest.raises(HomeAssistantError):
            await coordinator.async_set_clock(MOMENT)
    assert not bike.connected


async def test_connection_failure_while_setting_clock_is_reported(hass, advertising):
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300)
    with patch("custom_components.tenways.coordinator.establish_connection", side_effect=TimeoutError):
        with pytest.raises(HomeAssistantError):
            await coordinator.async_set_clock(MOMENT)


async def test_poll_waits_for_a_clock_sync_in_progress(hass, advertising):
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300, advertised_name="Longtail Duo")
    async with coordinator._ble_lock:
        refresh = asyncio.create_task(coordinator.async_refresh())
        await asyncio.sleep(0.05)
        assert not refresh.done()
    with patch("custom_components.tenways.coordinator.establish_connection", return_value=FakeBike()):
        await refresh
    assert coordinator.data.traction_battery == 68


# Options: daily trip reset and automatic clock, written in the poll's own connection.

ZERO_TRIP_REPLY = build_frame(TYPE_READ, CMD_STATUS, STATUS_REPLY[4:-3]
    .replace(bytes.fromhex("09 04 00 00 04 b1"), bytes.fromhex("09 04 00 00 00 00"))
    .replace(bytes.fromhex("0a 04 00 00 85 44"), bytes.fromhex("0a 04 00 00 00 00")))
CLOCK_MOMENT = datetime(2026, 10, 18, 14, 32, 18, tzinfo=ZoneInfo("US/Pacific"))  # summer time


async def _refresh_with_options(
    hass, *bikes, trip_reset="off", auto_clock=False, at=CLOCK_MOMENT, between=None, advertised="Longtail Duo",
):
    """Poll once per bike; ``between(coordinator)`` runs before each poll after the first."""
    from custom_components.tenways.totals import TenwaysTotals

    totals = TenwaysTotals(hass, "entry")
    await totals.async_load()
    coordinator = TenwaysCoordinator(
        hass, ADDRESS, 300, totals, "Longtail Duo", trip_reset=trip_reset, auto_clock=auto_clock,
        advertised_name=advertised,
    )
    coordinator.entities_ready = True
    results = []
    with patch("custom_components.tenways.coordinator.establish_connection", side_effect=list(bikes)), \
         patch("custom_components.tenways.coordinator.dt_util.now", return_value=at):
        for i, _ in enumerate(bikes):
            if i and between is not None:
                between(coordinator)
            await coordinator.async_refresh()
            results.append(coordinator.data)
    await totals.async_unload()
    return totals, results


def _reappeared(coordinator):
    coordinator._new_session = True  # the bike went quiet and advertises again


def _status(trip_km: int, ride_s: int) -> bytes:
    return build_frame(TYPE_READ, CMD_STATUS, STATUS_REPLY[4:-3]
        .replace(bytes.fromhex("09 04 00 00 04 b1"), bytes([0x09, 4]) + (trip_km * 10).to_bytes(4, "big"))
        .replace(bytes.fromhex("0a 04 00 00 85 44"), bytes([0x0A, 4]) + ride_s.to_bytes(4, "big")))


async def test_daily_reset_follows_the_first_read_in_the_same_connection(hass, advertising):
    replies = {STATUS_REQUEST: STATUS_REPLY, INFO_REQUEST: INFO_REPLY, CLEAR_TRIP: CLEAR_TRIP}
    first = FakeBike(replies=replies)
    second = FakeBike(replies={STATUS_REQUEST: ZERO_TRIP_REPLY, CLEAR_TRIP: CLEAR_TRIP})  # cleared, as the bike does
    totals, (data, _) = await _refresh_with_options(hass, first, second, trip_reset="daily")
    assert first.writes == [INFO_REQUEST, STATUS_REQUEST, CLEAR_TRIP]
    assert second.writes == [STATUS_REQUEST]  # once a day
    assert (data.trip_distance, data.ride_seconds) == (0, 0)  # shown right away
    assert data.odometer == 120.1
    assert totals.total_ride_s == 34116  # the trip was counted before it was cleared


async def test_empty_trip_needs_no_reset_but_counts_for_the_day(hass, advertising):
    replies = {STATUS_REQUEST: ZERO_TRIP_REPLY, INFO_REQUEST: INFO_REPLY, CLEAR_TRIP: CLEAR_TRIP}
    later = {STATUS_REQUEST: STATUS_REPLY, CLEAR_TRIP: CLEAR_TRIP}  # a ride later that day
    first, second = FakeBike(replies=replies), FakeBike(replies=later)
    await _refresh_with_options(hass, first, second, trip_reset="daily")
    assert CLEAR_TRIP not in first.writes
    assert CLEAR_TRIP not in second.writes  # today's ride stays on the display


async def test_failed_daily_reset_is_retried_three_times_a_day(hass, advertising):
    bikes = [FakeBike(replies={STATUS_REQUEST: STATUS_REPLY, INFO_REQUEST: INFO_REPLY}) for _ in range(4)]
    with patch("tenways_ble.client.TenwaysBike.reset_trip", side_effect=TimeoutError):
        totals, _ = await _refresh_with_options(hass, *bikes, trip_reset="daily")
    assert totals.state.reset_failures == 3
    assert totals.state.trip_reset_day is None


async def test_auto_clock_once_then_after_a_time_change(hass, advertising):
    replies = {STATUS_REQUEST: STATUS_REPLY, INFO_REQUEST: INFO_REPLY, CLOCK_WRITE: CLOCK_REPLY}
    first, second = FakeBike(replies=dict(replies)), FakeBike(replies=dict(replies))
    totals, _ = await _refresh_with_options(hass, first, second, auto_clock=True)
    assert first.writes == [INFO_REQUEST, STATUS_REQUEST, CLOCK_WRITE]
    assert second.writes == [STATUS_REQUEST]
    assert totals.clock_due(CLOCK_MOMENT + timedelta(days=91))
    assert not totals.clock_due(CLOCK_MOMENT + timedelta(days=1))
    winter = datetime(2026, 11, 1, 12, 0, tzinfo=ZoneInfo("US/Pacific"))  # after the change
    assert winter.utcoffset() != CLOCK_MOMENT.utcoffset()
    assert totals.clock_due(winter)


async def test_options_off_send_nothing(hass, advertising):
    bike = FakeBike(replies={STATUS_REQUEST: STATUS_REPLY, INFO_REQUEST: INFO_REPLY, CLEAR_TRIP: CLEAR_TRIP})
    await _refresh_with_options(hass, bike)
    assert bike.writes == [INFO_REQUEST, STATUS_REQUEST]


async def test_ride_mode_reads_then_clears_each_time_the_bike_appears(hass, advertising):
    # Switch-on: read, then clear. Polls while the bike stays visible: no write.
    # Back in range after a ride: read the ride first, then clear.
    switch_on = FakeBike(replies={STATUS_REQUEST: _status(5, 600), INFO_REQUEST: INFO_REPLY, CLEAR_TRIP: CLEAR_TRIP})
    staying = FakeBike(replies={STATUS_REQUEST: _status(0, 0), CLEAR_TRIP: CLEAR_TRIP})
    back_home = FakeBike(replies={STATUS_REQUEST: _status(3, 900), CLEAR_TRIP: CLEAR_TRIP})
    steps = iter([lambda c: None, _reappeared])
    totals, results = await _refresh_with_options(
        hass, switch_on, staying, back_home, trip_reset="ride", between=lambda c: next(steps)(c),
    )
    assert switch_on.writes[-1] == CLEAR_TRIP
    assert CLEAR_TRIP not in staying.writes
    assert back_home.writes == [STATUS_REQUEST, CLEAR_TRIP]
    assert totals.total_ride_s == 600 + 900  # every ride read before it was cleared
    assert results[-1].trip_distance == 0


async def test_ride_is_published_before_the_reset_clears_it(hass, advertising):
    from custom_components.tenways.totals import TenwaysTotals

    totals = TenwaysTotals(hass, "entry")
    await totals.async_load()
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300, totals, "Longtail Duo", trip_reset="ride", advertised_name="Longtail Duo")
    coordinator.entities_ready = True
    seen = []
    unsub = coordinator.async_add_listener(lambda: seen.append(coordinator.data.trip_distance))
    bike = FakeBike(replies={STATUS_REQUEST: _status(3, 600), INFO_REQUEST: INFO_REPLY, CLEAR_TRIP: CLEAR_TRIP})
    with patch("custom_components.tenways.coordinator.establish_connection", return_value=bike), \
         patch("custom_components.tenways.coordinator.dt_util.now", return_value=CLOCK_MOMENT):
        await coordinator.async_refresh()
    unsub()
    await totals.async_unload()
    assert seen == [3.0, 0]  # the ride as read, then the cleared trip
    assert bike.writes == [INFO_REQUEST, STATUS_REQUEST, CLEAR_TRIP]



async def test_no_automatic_reset_before_the_entities_exist(hass, advertising):
    # The first refresh at setup runs before the platforms; the reset waits for the next read.
    from custom_components.tenways.totals import TenwaysTotals

    totals = TenwaysTotals(hass, "entry")
    await totals.async_load()
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300, totals, "Longtail Duo", trip_reset="ride", advertised_name="Longtail Duo")
    first = FakeBike(replies={STATUS_REQUEST: _status(3, 600), INFO_REQUEST: INFO_REPLY, CLEAR_TRIP: CLEAR_TRIP})
    second = FakeBike(replies={STATUS_REQUEST: _status(3, 600), CLEAR_TRIP: CLEAR_TRIP})
    with patch("custom_components.tenways.coordinator.establish_connection", side_effect=[first, second]), \
         patch("custom_components.tenways.coordinator.dt_util.now", return_value=CLOCK_MOMENT):
        await coordinator.async_refresh()
        coordinator.entities_ready = True
        await coordinator.async_refresh()
    await totals.async_unload()
    assert CLEAR_TRIP not in first.writes
    assert CLEAR_TRIP in second.writes
    assert totals.total_ride_s == 600  # counted once


async def test_reset_button_publishes_the_ride_first(hass, advertising):
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300, advertised_name="Longtail Duo")
    poll = FakeBike(replies={STATUS_REQUEST: _status(2, 400), INFO_REQUEST: INFO_REPLY})
    press = FakeBike(replies={STATUS_REQUEST: _status(3, 600), CLEAR_TRIP: CLEAR_TRIP})
    seen = []
    with patch("custom_components.tenways.coordinator.establish_connection", side_effect=[poll, press]), \
         patch.object(TenwaysCoordinator, "async_request_refresh"):
        await coordinator.async_refresh()
        unsub = coordinator.async_add_listener(lambda: seen.append(coordinator.data.trip_distance))
        await coordinator.async_reset_trip()
    unsub()
    assert seen[0] == 3.0  # the ride as read when the button was pressed, before it is cleared
    assert press.writes == [STATUS_REQUEST, CLEAR_TRIP]


# --- Writes only to a model confirmed on a bike ---------------------------------------------

def _writes(bike):
    """What was written to the bike other than the two read requests."""
    return [w for w in bike.writes if w not in (STATUS_REQUEST, INFO_REQUEST)]


@pytest.mark.parametrize("name", ["CGO800", "CGO009", "CGO009_D", "AGOX", "TENWAYS B3:0D", "Tenways-ble-400A59", None])
async def test_clock_and_trip_reset_are_refused_for_an_unconfirmed_model(hass, advertising, name):
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300, advertised_name=name)
    bike = FakeBike(replies={CLOCK_WRITE: CLOCK_REPLY, CLEAR_TRIP: CLEAR_TRIP})
    assert not coordinator.writes_allowed
    with patch("custom_components.tenways.coordinator.establish_connection", return_value=bike) as connect:
        with pytest.raises(HomeAssistantError) as error:
            await coordinator.async_set_clock(MOMENT)
        assert error.value.translation_key == "writes_not_confirmed"
        with pytest.raises(HomeAssistantError):
            await coordinator.async_reset_trip()
    connect.assert_not_called()  # not even a connection
    assert bike.writes == []


@pytest.mark.parametrize("name", ["CGO800", "AGOX", "TENWAYS B3:0D", None])
async def test_automatic_options_are_ignored_for_an_unconfirmed_model(hass, advertising, name):
    first = FakeBike(replies={STATUS_REQUEST: _status(5, 600), INFO_REQUEST: INFO_REPLY})
    # The bike advertises this name (the fixture's default would be the Longtail Duo).
    info = SimpleNamespace(time=time.monotonic(), rssi=-60, name=name)
    with patch("custom_components.tenways.coordinator.bluetooth.async_last_service_info", return_value=info):
        totals, (data,) = await _refresh_with_options(
            hass, first, trip_reset="daily", auto_clock=True, advertised=name,
        )
    assert data.traction_battery == 68  # still read
    assert _writes(first) == []  # but neither the trip reset nor the clock


async def test_automatic_options_still_work_for_the_confirmed_model(hass, advertising):
    first = FakeBike(replies={STATUS_REQUEST: _status(5, 600), INFO_REQUEST: INFO_REPLY, CLEAR_TRIP: CLEAR_TRIP,
                              CLOCK_WRITE: CLOCK_REPLY})
    await _refresh_with_options(hass, first, trip_reset="daily", auto_clock=True)
    assert CLEAR_TRIP in first.writes


async def test_the_unknown_name_fallback_never_allows_a_write(hass):
    # model_profile() keeps the Longtail Duo's read requests for an unknown name ...
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300, name="TENWAYS B3:0D")
    assert coordinator.profile.tested and coordinator.profile.name == "Longtail Duo"
    # ... but that is a fallback for reading, not a name the bike advertised.
    assert not coordinator.writes_allowed


async def test_a_name_seen_later_allows_writes_and_is_remembered(hass):
    seen = []
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300, name="TENWAYS B3:0D", on_name_seen=seen.append)
    changed = []
    coordinator.async_add_listener(lambda: changed.append(coordinator.writes_allowed))
    coordinator.async_handle_advertisement(SimpleNamespace(name="Longtail Duo"), None)
    assert coordinator.writes_allowed
    assert seen == ["Longtail Duo"]
    assert changed[-1] is True  # the write entities are told
    await coordinator.async_shutdown()


async def test_an_address_instead_of_a_name_does_not_change_it(hass):
    coordinator = TenwaysCoordinator(hass, ADDRESS, 300, advertised_name="Longtail Duo")
    for name in (None, "", ADDRESS, ADDRESS.lower(), ADDRESS.replace(":", "-")):
        coordinator.async_handle_advertisement(SimpleNamespace(name=name), None)
    assert coordinator.advertised_name == "Longtail Duo" and coordinator.writes_allowed
    await coordinator.async_shutdown()


async def test_two_bikes_are_judged_separately(hass, advertising):
    duo = TenwaysCoordinator(hass, ADDRESS, 300, advertised_name="Longtail Duo")
    other = TenwaysCoordinator(hass, "AA:BB:CC:DD:EE:FF", 300, advertised_name="CGO800")
    duo_bike, other_bike = FakeBike(replies={CLOCK_WRITE: CLOCK_REPLY}), FakeBike(replies={CLOCK_WRITE: CLOCK_REPLY})
    with patch("custom_components.tenways.coordinator.establish_connection", side_effect=[duo_bike, other_bike]):
        await duo.async_set_clock(MOMENT)
        with pytest.raises(HomeAssistantError):
            await other.async_set_clock(MOMENT)
    assert duo_bike.writes == [CLOCK_WRITE]
    assert other_bike.writes == []
