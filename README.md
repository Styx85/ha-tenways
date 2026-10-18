# TENWAYS BLE for Home Assistant — experimental
Unofficial HACS custom integration. **The Longtail Duo status request has been reproduced from the owner's Android Bluetooth HCI capture; the live HA integration has not yet been tested on the bike.**

## Installation

Add this repository in HACS as a custom **Integration** repository. Install and restart Home Assistant. In Settings → Devices & services, add **TENWAYS BLE** and select **Longtail Duo** (`E8:88:6C:31:B3:0D`). Requires an HA Bluetooth adapter or an active-connection-capable ESPHome proxy within range. The companion TENWAYS app may block a concurrent BLE connection.

If v0.2 was already installed against `Tenways-ble-400A59`, **do not expect the new traction sensors on that old entry**. Add the separately advertised **Longtail Duo** device. Both can remain installed for diagnostics.

## Exposed sensors

- Traction battery (%) from proprietary status field `0x0F`; previously observed 68%.
- Odometer (km), trip distance (km), maximum and average ride speed (km/h), accumulated ride time (seconds).
- Standard Bluetooth battery (`0x2A19`): **not the traction battery**; may read 100% or 1% on the two BLE endpoints.
- BLE signal, last advertisement, last successful read and optional Device Information characteristics.

No unlock, light, power, firmware, configuration or pairing commands are implemented. Only the **single recorded status query** is sent via the `4348…0002` write characteristic and responses are received through `4348…0003` notify. No spontaneous notifications were observed without the query.

## Limitations

- Proprietary packet framing and TLV boundaries are checked, but **CRC validation is not yet implemented**. Sensor values should be considered experimental until confirmed live.
- Firmware changes may require updating the command/parser. A failed read yields unavailable readings rather than reusing old telemetry.
- The proprietary poll is intentionally restricted to the observed Longtail Duo BLE address; wider model discovery can follow further tests. Poll interval: five minutes.
- Bluetooth proxies must support active GATT connections.
- For bugs, enable debug logs for `custom_components.tenways` and submit a redacted excerpt. **Never publish a raw phone HCI log**; it may contain other devices' traffic and identifiers.

## Acknowledgements / Credits

Based on and inspired by [stein155/cgo600-bridge](https://github.com/stein155/cgo600-bridge), which provided valuable groundwork for understanding the proprietary TENWAYS telemetry protocol and its integration with Home Assistant.

Many thanks to the original author and contributors.

The Longtail Duo implementation was developed using independently captured Bluetooth HCI traffic from the official TENWAYS app. It uses the King Meter BLE transport rather than the Nordic UART Service used by the CGO600 bridge.
