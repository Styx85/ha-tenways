from unittest.mock import patch

from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
