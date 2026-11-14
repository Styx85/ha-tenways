# Supported models

Back to the [README](../README.md).

Only the **Longtail Duo** has been tested. For the other models, this page reasons from the TENWAYS app (versions 2.18.0 and 2.19.0, analysed statically, see [tenways-ble RESEARCH.md](https://github.com/Styx85/tenways-ble/blob/main/docs/RESEARCH.md#findings-from-the-apps-code-static-analysis)): the app picks a driver from the name the bike advertises.

| Name starts with | Driver in the app | Protocol | With this integration |
|---|---|---|---|
| `Longtail Duo` | own driver ("long tail duo/CGO009_D") on the AGO base | King Meter | **tested**: all sensors, Set clock, Reset trip |
| `CGO009_D` | the same driver as the Longtail Duo | King Meter | probably works |
| `CGO009` (not `L`/`_D`) | "009", AGO base | King Meter | possibly; it has an assist level field (`0x12`) the integration does not read |
| `AGO`, `AGOX`, `AGOT`, `CARGO` and other names | "ago", the AGO base | King Meter | possibly; the app sets the clock on `AGOX`, `AGOT` and `CARGO` too |
| `CGO800` | "800s" | King Meter, CRC low byte first | not yet: `tenways-ble` expects the CRC high byte first and rejects the replies |
| `AGO AIR`, `Wayfarer_B`, … | "AGO AIR" | King Meter, partly encrypted (`0xD8`/`0xD2` handshake) | no: the encrypted session is not implemented |
| `CGO600_D` | own driver | `0x57` frames | no |
| `CGO600` | Nordic UART | not King Meter | no |
| `smart-helmet-` | helmet | `55 B1 …` frames | no (not a bike) |

"Possibly" means: same protocol and status request as the Longtail Duo in the app, but which fields a display answers is unknown. HA discovers a bike automatically if it advertises as `Longtail Duo` or with the King Meter service UUID (`43480001-…`); otherwise add **TENWAYS BLE** by hand with the bike's Bluetooth address.

For CGO600, CGO800 and the encrypted displays, [tenways-bridge](https://github.com/stein155/tenways-bridge) (ESPHome firmware for an ESP32) has profiles.

If you try another model, please open an issue with a diagnostics download (Settings → Devices & services → TENWAYS → ⋮ → Download diagnostics) and say which values match the display.
