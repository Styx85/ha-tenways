"""Which tenways-ble profile (app driver) a bike gets, by its advertised name."""
from __future__ import annotations

from tenways_ble import Profile, profile_for
from tenways_ble.profiles import LONGTAIL_DUO

from .const import KING_METER_NAME_PREFIXES


def model_profile(name: str | None) -> Profile:
    """The profile for ``name``.

    Known model names and unsupported ones get their own profile, as in the
    TENWAYS app. A missing or unknown name (e.g. a bike added by its address,
    titled "TENWAYS AB:CD") keeps the tested Longtail Duo requests instead of
    the app's default driver, so existing setups behave as before.
    """
    if name:
        profile = profile_for(name)
        if not profile.supported or name.startswith(KING_METER_NAME_PREFIXES):
            return profile
    return LONGTAIL_DUO
