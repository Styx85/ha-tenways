# TENWAYS BLE – Home Assistant Custom Integration (v0.2.0)

Experimental read-only HACS integration, tested by syntax checks only. **Not yet tested against a real HA installation.**

## Capabilities

- Bluetooth discovery for `Tenways-ble-*`, manual MAC entry as fallback.
- **BLE Battery Level (0x2A19):** standard characteristic, **not validated as the traction battery**. Your Longtail Duo display shows a different level, so treat this as an unknown BLE module battery.
- BLE signal strength (RSSI) when the recent advertisement is available.
- Last advertisement time and last successful GATT read.
- Optional standard Device Information (manufacturer, model, firmware), only if advertised; otherwise unavailable.
- Diagnostic binary sensor: Bluetooth recently seen (last 120 seconds at poll time), not a connection or lock state.
- 5-minute polling. Optional diagnostic entities are disabled by default in the entity registry.
- No writes, unlocking, control, or proprietary command transmission.

## Installation

Add this repository to HACS as a custom **Integration**, install it, restart HA, and add **TENWAYS BLE** under Settings → Devices & Services. Ensure a connectable Bluetooth adapter or active-capable ESPHome proxy can reach the bicycle.

If v0.1 is already installed, install v0.2 and restart HA. The original battery unique ID is retained. In the device's Entities page, enable the diagnostic entities you want to inspect.

## Important limitations

The BLE battery reading from the user's Longtail Duo was `100%`, while the bicycle's display reported a different value. This integration **must not present it as drive-battery charge**. No trip distance, odometer, range, lights or locking values can yet be obtained without parsing verified proprietary communications. `Last advertisement` may be stale if the bike has disappeared, and only the RSSI/visible flag are freshness-gated.

`43480001-f001-4b49-4e47-204d45544552` is the proprietary KING METER-labelled service. It is deliberately untouched by this integration.
