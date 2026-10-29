"""Diagnostics hide the Bluetooth address and serial number."""
from custom_components.tenways.diagnostics import async_get_config_entry_diagnostics

from .test_sensor import ADDRESS, _setup_without_bike


async def test_diagnostics_are_redacted(hass):
    entry = await _setup_without_bike(hass)
    result = await async_get_config_entry_diagnostics(hass, entry)
    text = str(result)
    assert ADDRESS not in text
    assert result["entry"]["data"]["address"] == "**REDACTED**"
    assert result["last_update_success"] is True
    assert result["data"]["bluetooth_visible"] is False
