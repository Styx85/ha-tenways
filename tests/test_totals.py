"""Totals over all trips and per day, computed in HA from the bike's trip counters."""
from datetime import datetime
from unittest.mock import patch

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.tenways.const import CONF_ADDRESS, CONF_RIDE_HOURS_BEFORE, DOMAIN
from custom_components.tenways.totals import TenwaysTotals

ADDRESS = "E8:88:6C:31:B3:0D"


def _at(hour, day=14):
    return dt_util.as_utc(datetime(2026, 11, day, hour, 0, tzinfo=dt_util.get_default_time_zone()))


async def test_trip_reset_keeps_counting(hass):
    totals = TenwaysTotals(hass, "entry")
    await totals.async_load()
    assert totals.total_ride_s is None  # nothing read yet
    totals.async_update(3600, 100.0, 30.0)  # first read: the trip so far counts
    assert totals.total_ride_s == 3600
    assert totals.day_ride_s == 0
    totals.async_update(4000, 105.0, 31.0)
    totals.async_update(600, 110.0, 25.0)  # trip cleared on the display, then 600 s ridden
    assert totals.total_ride_s == 3600 + 400 + 600
    assert totals.day_ride_s == 1000
    assert totals.day_distance == 10.0
    assert totals.max_speed == 31.0
    assert totals.average_speed(110.0) == round(110 * 3600 / 4600, 1)
    await totals.async_unload()


async def test_cleared_by_ha_counts_from_zero(hass):
    totals = TenwaysTotals(hass, "entry")
    await totals.async_load()
    totals.async_update(3600, 100.0, None)
    totals.async_trip_cleared()
    totals.async_update(3700, 120.0, None)  # rode more than before the reset before the next read
    assert totals.total_ride_s == 3600 + 3700
    await totals.async_unload()


async def test_offset_and_implausible_maximum(hass):
    totals = TenwaysTotals(hass, "entry", ride_offset_s=7200)
    await totals.async_load()
    totals.async_update(0, 50.0, 80.0)  # above 75 km/h is ignored, as in the app
    assert totals.total_ride_s == 7200
    assert totals.max_speed is None
    assert totals.average_speed(50.0) == 25.0
    totals.async_update(0, 50.0, 20.0)
    totals.async_reset_max_speed()
    assert totals.max_speed == 0.0
    await totals.async_unload()


async def test_day_values_reset_at_midnight(hass, freezer):
    freezer.move_to(_at(20))
    totals = TenwaysTotals(hass, "entry")
    await totals.async_load()
    totals.async_update(100, 10.0, None)
    totals.async_update(700, 15.0, None)
    assert (totals.day_ride_s, totals.day_distance) == (600, 5.0)
    freezer.move_to(_at(0, day=15))
    async_fire_time_changed(hass, _at(0, day=15))
    await hass.async_block_till_done()
    assert (totals.day_ride_s, totals.day_distance) == (0, 0.0)
    totals.async_update(900, 18.0, None)
    assert (totals.day_ride_s, totals.day_distance) == (200, 3.0)
    await totals.async_unload()


async def test_stored_across_restart(hass, freezer):
    freezer.move_to(_at(10))
    totals = TenwaysTotals(hass, "entry")
    await totals.async_load()
    totals.async_update(100, 10.0, 22.0)
    totals.async_update(400, 12.0, 23.0)
    await totals.async_unload()

    again = TenwaysTotals(hass, "entry")
    await again.async_load()
    assert (again.total_ride_s, again.max_speed, again.day_ride_s, again.day_distance) == (400, 23.0, 300, 2.0)
    again.async_update(500, 13.0, None)  # continues from the stored trip value
    assert again.total_ride_s == 500
    await again.async_unload()

    freezer.move_to(_at(10, day=16))  # HA was off over midnight: day values start fresh
    later = TenwaysTotals(hass, "entry")
    await later.async_load()
    assert (later.total_ride_s, later.day_ride_s, later.day_distance) == (500, 0, 0.0)
    await later.async_unload()


async def test_total_sensors_on_the_device(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ADDRESS: ADDRESS}, unique_id=ADDRESS, title="Longtail Duo",
        options={CONF_RIDE_HOURS_BEFORE: 2},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.tenways.coordinator.bluetooth.async_last_service_info", return_value=None), \
         patch("custom_components.tenways.coordinator.bluetooth.async_ble_device_from_address", return_value=None), \
         patch("custom_components.tenways.bluetooth.async_register_callback", return_value=lambda: None):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{ADDRESS}_total_ride_time")
        assert entity_id is not None
        assert registry.async_get(entity_id).device_id is not None
        assert hass.states.get(entity_id).state == "unavailable"  # nothing read yet

        entry.runtime_data.totals.async_update(1800, 40.0, 30.0)
        await hass.async_block_till_done()
        assert float(hass.states.get(entity_id).state) == 2.5  # shown in hours: 2 h before + 0.5 h trip
        max_id = registry.async_get_entity_id("sensor", DOMAIN, f"{ADDRESS}_max_speed_total")
        assert hass.states.get(max_id).state == "30.0"
        assert await hass.config_entries.async_unload(entry.entry_id)
