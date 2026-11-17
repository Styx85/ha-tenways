from types import SimpleNamespace
from unittest.mock import patch

from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tenways_ble.const import TENWAYS_SERVICE_UUID

from custom_components.tenways.const import (
    CONF_ADDRESS, CONF_ADVERTISED_NAME, CONF_POLL_SECONDS, CONF_RIDE_HOURS_BEFORE, DOMAIN,
)


async def test_options_flow_sets_poll_interval(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ADDRESS: "E8:88:6C:31:B3:0D"}, unique_id="E8:88:6C:31:B3:0D")
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    with patch("custom_components.tenways.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_POLL_SECONDS: 120})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    # A model not confirmed on a bike (here: not loaded yet) is not offered the automatic writes.
    assert entry.options == {CONF_POLL_SECONDS: 120, CONF_RIDE_HOURS_BEFORE: 0.0}


async def test_options_flow_sets_ride_time_before(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ADDRESS: "E8:88:6C:31:B3:0D"}, unique_id="E8:88:6C:31:B3:0D")
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch("custom_components.tenways.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_POLL_SECONDS: 300, CONF_RIDE_HOURS_BEFORE: 11.9361},
        )
    assert entry.options[CONF_RIDE_HOURS_BEFORE] == 11.9361


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


def _visible(*infos):
    return patch(
        "custom_components.tenways.config_flow.bluetooth.async_discovered_service_info",
        return_value=list(infos),
    )


async def test_manual_address_works_while_a_bike_is_visible(hass):
    with _visible(_advertisement("Longtail Duo")):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        assert result["type"] is FlowResultType.FORM
        with patch("custom_components.tenways.async_setup_entry", return_value=True):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_ADDRESS: "aa:bb:cc:dd:ee:ff"},
            )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ADDRESS] == "AA:BB:CC:DD:EE:FF"


async def test_discovered_bike_is_offered_by_name(hass):
    with _visible(_advertisement("Longtail Duo")):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        with patch("custom_components.tenways.async_setup_entry", return_value=True):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_ADDRESS: "E8:88:6C:31:B3:0D"},
            )
    assert result["title"] == "Longtail Duo"


async def test_invalid_address_is_rejected(hass):
    with _visible():
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADDRESS: "nonsense"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_ADDRESS: "invalid_address"}


async def test_configured_bike_cannot_be_added_twice(hass):
    MockConfigEntry(domain=DOMAIN, data={CONF_ADDRESS: "AA:BB:CC:DD:EE:FF"}, unique_id="AA:BB:CC:DD:EE:FF").add_to_hass(hass)
    with _visible():
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADDRESS: "aa:bb:cc:dd:ee:ff"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_non_connectable_discovery_is_ignored(hass):
    info = _advertisement("Longtail Duo")
    info.connectable = False
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info,
    )
    assert result["type"] is FlowResultType.ABORT


async def test_other_king_meter_models_are_offered(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=_advertisement("CGO800 Plus"),
    )
    assert result["step_id"] == "bluetooth_confirm"


async def test_unsupported_model_is_explained(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=_advertisement("AGO AIR", [TENWAYS_SERVICE_UUID]),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unsupported_model"
    assert "encrypted" in result["description_placeholders"]["reason"]


async def test_unsupported_model_is_not_listed(hass):
    with _visible(_advertisement("AGOX_D", [TENWAYS_SERVICE_UUID])):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert "data_schema" in result
    schema_keys = {str(k) for k in result["data_schema"].schema}
    assert schema_keys == {CONF_ADDRESS}
    # Nothing to choose from: a plain text field, not a dropdown of bikes.
    assert result["data_schema"].schema[next(iter(result["data_schema"].schema))] is str


async def test_typed_address_of_unsupported_model_is_explained(hass):
    with _visible(_advertisement("AGO AIR", [TENWAYS_SERVICE_UUID])):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADDRESS: "e8:88:6c:31:b3:0d"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unsupported_model"


# --- The advertised name, unique titles and the gated options --------------------------------

async def _confirm_discovery(hass, info):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info)
    with patch("custom_components.tenways.async_setup_entry", return_value=True):
        return await hass.config_entries.flow.async_configure(result["flow_id"], {})


async def test_discovery_stores_the_advertised_name(hass):
    result = await _confirm_discovery(hass, _advertisement("Longtail Duo"))
    assert result["data"][CONF_ADVERTISED_NAME] == "Longtail Duo"


async def test_discovery_without_a_name_stores_none(hass):
    info = _advertisement(None, [TENWAYS_SERVICE_UUID])
    result = await _confirm_discovery(hass, info)
    assert CONF_ADVERTISED_NAME not in result["data"]
    assert result["data"]["name"].startswith("TENWAYS ")  # the placeholder is only a title


async def test_an_address_as_the_name_is_not_stored(hass):
    info = _advertisement("E8:88:6C:31:B3:0D", [TENWAYS_SERVICE_UUID])
    result = await _confirm_discovery(hass, info)
    assert CONF_ADVERTISED_NAME not in result["data"]


async def test_typed_address_of_a_visible_bike_stores_its_name(hass):
    with _visible(_advertisement("Longtail Duo")):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        with patch("custom_components.tenways.async_setup_entry", return_value=True):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_ADDRESS: "E8:88:6C:31:B3:0D"},
            )
    assert result["data"][CONF_ADVERTISED_NAME] == "Longtail Duo"


async def test_typed_address_of_an_absent_bike_stores_no_name(hass):
    with _visible():
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        with patch("custom_components.tenways.async_setup_entry", return_value=True):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_ADDRESS: "aa:bb:cc:dd:ee:ff"},
            )
    assert CONF_ADVERTISED_NAME not in result["data"]
    assert result["data"]["name"] == "TENWAYS EE:FF"


async def test_a_second_bike_with_the_same_name_gets_its_address_in_the_title(hass):
    first = await _confirm_discovery(hass, _advertisement("Longtail Duo"))
    assert first["title"] == "Longtail Duo"
    second_info = _advertisement("Longtail Duo")
    second_info.address = "aa:bb:cc:dd:ee:ff"
    second = await _confirm_discovery(hass, second_info)
    assert second["title"] == "Longtail Duo EE:FF"
    assert second["data"]["name"] == "Longtail Duo"  # the model is still decided by the real name
    assert second["data"][CONF_ADVERTISED_NAME] == "Longtail Duo"


async def _options_form(hass, writes: bool, options=None):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ADDRESS: "E8:88:6C:31:B3:0D"}, unique_id="E8:88:6C:31:B3:0D", options=options or {},
    )
    entry.add_to_hass(hass)
    entry.runtime_data = SimpleNamespace(writes_allowed=writes)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return entry, result, {str(key) for key in result["data_schema"].schema}


async def test_options_offer_the_automatic_writes_for_a_confirmed_model(hass):
    _entry, _result, keys = await _options_form(hass, writes=True)
    assert {"trip_reset", "auto_clock"} <= keys


async def test_options_hide_the_automatic_writes_for_an_unconfirmed_model(hass):
    _entry, _result, keys = await _options_form(hass, writes=False)
    assert keys == {CONF_POLL_SECONDS, CONF_RIDE_HOURS_BEFORE}


async def test_saving_options_keeps_a_stored_automatic_choice_of_an_unconfirmed_model(hass):
    entry, result, _keys = await _options_form(hass, writes=False, options={"trip_reset": "daily", "auto_clock": True})
    with patch("custom_components.tenways.async_setup_entry", return_value=True):
        await hass.config_entries.options.async_configure(result["flow_id"], {CONF_POLL_SECONDS: 120})
    # Not offered, not discarded (and the coordinator ignores it for this model).
    assert entry.options["trip_reset"] == "daily" and entry.options["auto_clock"] is True
    assert entry.options[CONF_POLL_SECONDS] == 120
