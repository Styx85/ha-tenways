import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def bluetooth_dependency_loaded(request):
    """Mark HA's bluetooth component as set up.

    The manifest depends on it, and setting up the real component opens
    sockets, which the test environment blocks. The tests patch the calls
    into it that they need.
    """
    if "hass" in request.fixturenames:
        request.getfixturevalue("hass").config.components.add("bluetooth")
    yield
