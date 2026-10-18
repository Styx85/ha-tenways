# TENWAYS BLE for Home Assistant (v0.1.0 experimental)

Unofficial Home Assistant custom integration for TENWAYS bicycles. First target: Longtail Duo.

**Current functionality:** read the standard BLE Battery Level (`0x180F` / `0x2A19`) once every five minutes. The reported value has **not yet been confirmed to represent the bicycle's main traction battery** rather than its BLE module battery. This integration never sends proprietary commands.

## Requirements

- Home Assistant with Bluetooth integration, and a Bluetooth adapter or an **active-connection-capable** ESPHome Bluetooth proxy within BLE range of the powered-on bicycle.
- A TENWAYS bike advertising with a name starting with `Tenways-ble-`.
- Make sure the TENWAYS phone app is disconnected during initial tests: concurrent connections may be restricted.

## Installation through HACS (custom repository)

1. Push this complete repository to your GitHub account.
2. In HACS → menu → **Custom repositories**, enter `https://github.com/YOUR_USERNAME/ha-tenways` and select **Integration**.
3. Download TENWAYS BLE from HACS and restart Home Assistant.
4. Settings → Devices & Services → Add integration → **TENWAYS BLE**.
5. Select the discovered bicycle or enter its MAC address. If the bike is away/off, the sensor stays unavailable until a successful read.

## Manual installation

Copy `custom_components/tenways` to `/config/custom_components/tenways`, restart HA, then add integration.

## Diagnostics

Enable debug logs for `custom_components.tenways` / `homeassistant.components.tenways` if needed. A 5-minute poll establishes a BLE connection, reads only `0x2A19`, then disconnects. No broker, ESP32 firmware or additional service is required.

## Caveats

- **Experimental, not tested against a running Home Assistant instance or the physical bicycle.**
- The bike might expose the BLE module battery rather than the traction battery. Verify against the bike's own display at less than 100% charge.
- BLE address may not be stable across some operating modes; v0.1 assumes the observed MAC is stable.
- Auto-discovery is triggered by advertisements; manual address entry is available when none is visible.
- No lock, GPS, speed or proprietary telemetry support.
