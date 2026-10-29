"""Diagnostics for TENWAYS BLE."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import TenwaysConfigEntry
from .const import CONF_ADDRESS

TO_REDACT = {CONF_ADDRESS, "unique_id", "serial"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: TenwaysConfigEntry) -> dict[str, Any]:
    """Everything a bug report needs, without the Bluetooth address or serial number."""
    coordinator = entry.runtime_data
    data = {
        key: value.isoformat() if isinstance(value, datetime) else value
        for key, value in (asdict(coordinator.data) if coordinator.data else {}).items()
    }
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "last_update_success": coordinator.last_update_success,
        "data": async_redact_data(data, TO_REDACT),
    }
