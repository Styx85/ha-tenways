"""Entities keep last read values while the bike is off and across restarts."""
from datetime import datetime, timezone
from unittest.mock import patch

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_restore_cache_with_extra_data

from custom_components.tenways.const import CONF_ADDRESS, DOMAIN

ADDRESS = "E8:88:6C:31:B3:0D"
READ_AT = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def _stored(entity_id, value, unit=None):
    from homeassistant.core import State
    return (State(entity_id, str(value)), {"native_value": value, "native_unit_of_measurement": unit})


async def _setup_without_bike(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ADDRESS: ADDRESS}, unique_id=ADDRESS, title="Longtail Duo")
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    # Pre-register so disabled-by-default entities are enabled and IDs are known.
    for key in ("traction_battery", "odometer", "last_read", "speed"):
        registry.async_get_or_create("sensor", DOMAIN, f"{ADDRESS}_{key}", suggested_object_id=f"tenways_{key}", config_entry=entry)
    registry.async_get_or_create("binary_sensor", DOMAIN, f"{ADDRESS}_light", suggested_object_id="tenways_light", config_entry=entry)
    with patch("custom_components.tenways.coordinator.bluetooth.async_last_service_info", return_value=None), \
         patch("custom_components.tenways.coordinator.bluetooth.async_ble_device_from_address", return_value=None), \
         patch("custom_components.tenways.bluetooth.async_register_callback", return_value=lambda: None):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_values_restored_after_restart(hass):
    mock_restore_cache_with_extra_data(hass, [
        _stored("sensor.tenways_traction_battery", 68, "%"),
        _stored("sensor.tenways_odometer", 120.1, "km"),
        _stored("sensor.tenways_last_read", {"__type": str(type(READ_AT)), "isoformat": READ_AT.isoformat()}),
        _stored("sensor.tenways_speed", 12.0, "km/h"),
    ])
    await _setup_without_bike(hass)
    assert hass.states.get("sensor.tenways_traction_battery").state == "68"
    assert hass.states.get("sensor.tenways_odometer").state == "120.1"
    assert hass.states.get("sensor.tenways_last_read").state == READ_AT.isoformat()
    # Live values are not restored.
    assert hass.states.get("sensor.tenways_speed").state == STATE_UNAVAILABLE
    assert hass.states.get("binary_sensor.tenways_light").state == STATE_UNAVAILABLE


async def test_nothing_known_is_unavailable(hass):
    await _setup_without_bike(hass)
    assert hass.states.get("sensor.tenways_traction_battery").state == STATE_UNAVAILABLE
