"""Profile choice by advertised name in the integration."""
import pytest
from tenways_ble.profiles import AGO, AGO_AIR, CGO800, CGO009_D, LONGTAIL_DUO

from custom_components.tenways.models import model_profile, writes_confirmed


@pytest.mark.parametrize(("name", "profile"), [
    ("Longtail Duo", LONGTAIL_DUO),
    ("CGO009_D", CGO009_D),
    ("CGO800", CGO800),
    ("AGOX", AGO),
    ("AGO AIR", AGO_AIR),
    # Added by address or the second endpoint: keep the tested Duo requests.
    ("TENWAYS B3:0D", LONGTAIL_DUO),
    ("Tenways-ble-400A59", LONGTAIL_DUO),
    (None, LONGTAIL_DUO),
])
def test_model_profile(name, profile):
    assert model_profile(name) is profile


@pytest.mark.parametrize(("name", "allowed"), [
    ("Longtail Duo", True),
    ("Longtail Duo 2", True),
    ("CGO009_D", False),
    ("CGO009", False),
    ("CGO800", False),
    ("AGOX", False),
    ("AGO AIR", False),
    ("CGO600", False),
    # No fallback for writes, unlike model_profile for reads.
    ("TENWAYS B3:0D", False),
    ("Tenways-ble-400A59", False),
    ("", False),
    (None, False),
])
def test_writes_are_only_confirmed_for_the_tested_model(name, allowed):
    assert writes_confirmed(name) is allowed
