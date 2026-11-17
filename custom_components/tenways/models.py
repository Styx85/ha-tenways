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


def writes_confirmed(advertised_name: str | None) -> bool:
    """Whether the integration may write to a bike that advertises ``advertised_name``.

    Only a model confirmed on a bike (see ``Profile.tested``), judged by the name the bike
    really advertised. There is no fallback here: an unknown name, or none seen yet, never
    allows a write, unlike ``model_profile`` which keeps the Longtail Duo's read requests.
    """
    if not advertised_name:
        return False
    profile = profile_for(advertised_name)
    return profile.supported and profile.tested
