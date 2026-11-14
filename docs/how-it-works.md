# How it works, limitations and troubleshooting

Back to the [README](../README.md).

## Status and verification

Unofficial HACS custom integration. The King Meter BLE protocol of the Longtail Duo is implemented in the [`tenways-ble`](https://github.com/Styx85/tenways-ble) library and verified byte-for-byte against an Android Bluetooth HCI capture of the official TENWAYS app. **Tested live on a Longtail Duo with Home Assistant 2026.11:** battery, odometer, trip, ride time, light, remaining range and setting the clock agree with the bike's display. Current speed and power have not yet been checked while riding.

## Connection

Add this repository in HACS as a custom **Integration** repository. Install and restart Home Assistant. In Settings → Devices & services, add **TENWAYS BLE** and select the device advertised as **Longtail Duo**. Requires an HA Bluetooth adapter or an active-connection-capable ESPHome proxy within range. The companion TENWAYS app may block a concurrent BLE connection.

The bike advertises two endpoints. Only **Longtail Duo** (King Meter service) delivers bike data; HA offers it automatically and asks before adding it. The second endpoint `Tenways-ble-*` shows no useful values and is no longer offered; an existing entry for it can be deleted and stays deleted. It can still be added by hand for diagnostics.

## Limitations

- Sensor values should be considered experimental until confirmed live.
- Firmware changes may require updating the command/parser.
- The proprietary poll runs on any configured device exposing the King Meter service; other TENWAYS models are untested. Poll interval: five minutes by default, adjustable in the integration options (30–3600 s). Each poll opens a short BLE connection; the TENWAYS app cannot connect at the same time.
- Bluetooth proxies must support active GATT connections. At a weak signal (around −85 dBm) some reads time out; the values from the last good read stay.
- HA only connects while the bike advertises (seen within the last 120 s). The bike stops advertising when it is switched off, so HA only reads it while it is on. When it reappears, HA polls immediately instead of waiting for the next interval. While HA is connected, the display shows a Bluetooth symbol.
- While the bike is off, out of range or a read fails, every sensor keeps its last read value, also across HA restarts; "Last successful read" says when it was read. Only current speed, light, remaining range, power and signal strength become unavailable.
- Live values (current speed, light, remaining range, power) lapse after two minutes without an advertisement instead of waiting for the next poll. "Last successful read" only moves when a valid reply arrived.
- The integration offers a diagnostics download (Bluetooth address and serial number redacted); attach it to bug reports.
- For bugs, enable debug logs for `custom_components.tenways` and submit a redacted excerpt. **Never publish a raw phone HCI log**; it may contain other devices' traffic and identifiers.

## Related projects

- **[tenways-bridge](https://github.com/stein155/tenways-bridge)** is an ESPHome firmware for an ESP32 that sits where the bike is parked, connects to the bike by itself and reports to Home Assistant. It supports more display types (Nordic UART and King Meter, including an encrypted session) and can switch the light. It lists the Longtail Duo as experimental and builds on our protocol notes. Choose it if you want a dedicated device and do not mind its firmware.
- **This integration** uses Home Assistant's own Bluetooth stack, so a standard ESPHome Bluetooth proxy with active connections is enough, and it only reads, except for the clock sync and clearing the trip, each sent only when its button is pressed (by you or an automation); there is no unlock, light or configuration command.

Both are unofficial and not affiliated with TENWAYS.

## Development

```bash
pip install -r requirements_test.txt
pytest
```

Protocol details, test vectors and research notes live in [`tenways-ble`](https://github.com/Styx85/tenways-ble).
