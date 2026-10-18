from types import SimpleNamespace
from unittest.mock import patch

from homeassistant.config_entries import SOURCE_BLUETOOTH
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tenways_ble.const import TENWAYS_SERVICE_UUID

from custom_components.tenways.const import CONF_ADDRESS, CONF_POLL_SECONDS, DOMAIN


async def test_options_flow_sets_poll_interval(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ADDRESS: "E8:88:6C:31:B3:0D"}, unique_id="E8:88:6C:31:B3:0D")
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    with patch("custom_components.tenways.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_POLL_SECONDS: 120})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_POLL_SECONDS: 120}


def _advertisement(name, service_uuids=()):
    return SimpleNamespace(
        name=name, address="e8:88:6c:31:b3:0d", connectable=True, service_uuids=list(service_uuids),
    )


async def test_bluetooth_discovery_asks_before_adding(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=_advertisement("Longtail Duo"),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"
    with patch("custom_components.tenways.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ADDRESS] == "E8:88:6C:31:B3:0D"


async def test_bluetooth_discovery_by_service_uuid(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=_advertisement(None, [TENWAYS_SERVICE_UUID]),
    )
    assert result["step_id"] == "bluetooth_confirm"


async def test_endpoint_without_telemetry_is_not_offered(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=_advertisement("Tenways-ble-400A59"),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"
