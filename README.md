<p align="center"><img src="https://raw.githubusercontent.com/Styx85/ha-tenways/main/custom_components/tenways/brand/icon@2x.png" alt="" width="160"></p>

# TENWAYS BLE for Home Assistant — experimental

Unofficial integration for TENWAYS e-bikes over Bluetooth, built on the [`tenways-ble`](https://github.com/Styx85/tenways-ble) library. It reads the bike through Home Assistant's own Bluetooth stack: a local adapter or an ESPHome Bluetooth proxy with active connections. No cloud, no extra hardware. **Tested on a Longtail Duo** with Home Assistant 2026.11; other King Meter models may work (untested), see [Supported bikes](#supported-bikes).

## Features

- **Battery and ride data:** traction battery, odometer, trip distance, ride time, maximum and average speed, light, remaining range.
- **Totals HA keeps for you:** total ride time, average and maximum speed over all trips, ride time and distance today. They keep counting when the trip is cleared, are stored per bike and appear in the long-term statistics.
- **Automatic trip reset and clock (options):** clear the trip once a day or for every ride, and keep the bike's clock right across daylight saving changes. Both happen in the connection that reads the bike, right after the read, so no ride is lost and it works even if you ride off at once.
- **Buttons:** **Set clock** (the bike has no daylight saving) and **Reset trip**, each sending the TENWAYS app's own write; plus a disabled one that resets HA's overall maximum.
- Keeps the last values while the bike is off, also across restarts; polls immediately when the bike is switched on.
- Diagnostics download with the address and serial number redacted.

No unlock, light, firmware or configuration commands. Details on every entity, where its value comes from and how far it is confirmed: [docs/entities.md](https://github.com/Styx85/ha-tenways/blob/main/docs/entities.md).

## Supported bikes

The integration picks a profile from the name the bike advertises, the way the TENWAYS app picks its driver (app versions 2.18.0 and 2.19.0, analysed statically, see [tenways-ble](https://github.com/Styx85/tenways-ble/blob/main/docs/RESEARCH.md#driver-per-model)). Every King Meter model gets everything the Longtail Duo has (all sensors, the totals, **Set clock** and **Reset trip**), untested except on the Duo. The app itself sends the clock only to AGOX, AGOT, CARGO and the Longtail Duo, and has clearing the trip built into the AGO base and the CGO800 driver.

| Advertised name | App driver | Status | Notes |
|---|---|---|---|
| `Longtail Duo` | long tail duo/CGO009_D | ✅ **tested** | all features confirmed on the bike |
| `CGO009_D` | long tail duo/CGO009_D | 🧪 untested | same requests as the Longtail Duo; the app sends it no clock |
| `CGO009` (not `CGO009L`) | 009 | 🧪 untested | also reports an assist level (`0x12`), not yet a sensor; the app sends it no clock |
| `CGO800`, `CGO800 Plus`, `CGO800S` | 800s | 🧪 untested | checksum low byte first, odometer in whole km; some CGO800 Plus displays need the encrypted session and then do not answer; the app sends it no clock |
| `AGO`, `AGOX`, `AGOT`, `CARGO`, `CGO009L` | ago (the app's default) | 🧪 untested | the app sends the clock to AGOX, AGOT and CARGO only |
| `AGO AIR`, `Wayfarer_B`, `AGOX_D`, `AGOT_D`, `CGO COMPACT_D`, `AGO AIR-BELT_D` | AGO AIR | ⛔ not supported | encrypted King Meter session |
| `CGO600_D` | CGO600_D | ⛔ not supported | `0x57` frames, not King Meter |
| `CGO600`, `CGO600 Pro`, `CGO600 PLUS` | Nordic UART | ⛔ not supported | not King Meter |
| `DM…` | DM | ⛔ not supported | separate driver, not analysed |

- **Untested** means the requests follow the app, but no such bike has answered yet. The integration logs a warning with a link here. Please open an issue with a diagnostics download (Settings → Devices & services → TENWAYS → ⋮ → Download diagnostics) and say which values match the display.
- **Not supported** models are not offered; adding one by its address while it advertises explains why, and an entry that sees such a name logs a warning. With a debug log, or an HCI capture of the TENWAYS app with that bike (never publish it raw; it contains other devices' traffic), they could be added. Until then, [tenways-bridge](https://github.com/stein155/tenways-bridge) (ESPHome firmware for an ESP32) has profiles for CGO600, CGO800 and the encrypted displays.
- HA discovers a bike that advertises a name starting with `Longtail Duo`, `CGO009`, `CGO800`, `AGO` or `CARGO`, or the King Meter service (`43480001-…`). Otherwise add **TENWAYS BLE** by hand with the bike's Bluetooth address; an unknown name then uses the Longtail Duo's requests.

## Installation

1. HACS → ⋮ → Custom repositories → add `https://github.com/Styx85/ha-tenways` as **Integration**.
2. Install **TENWAYS BLE** and restart Home Assistant.
3. Switch the bike on. Settings → Devices & services: HA offers the bike (advertised as **Longtail Duo**); confirm it. Otherwise add **TENWAYS BLE** and pick it or type its Bluetooth address.

Close the TENWAYS app: the bike accepts one connection at a time.

## Options

Settings → Devices & services → TENWAYS → Configure. *Clear the trip automatically* (a dropdown) and *Set the clock automatically* (a switch) are also on the device page under Configuration and take effect at once:

- **Poll interval:** 300 s by default (30–3600 s). Each poll is a short BLE connection.
- **Ride time before HA counted:** hours ridden before the trip was first cleared, so that the total ride time and the overall average are right.
- **Clear the trip automatically:** off, once a day, or each time the bike appears (per ride). It happens right after a read, in the same connection, so it works even if you ride off at once. The read comes first, so HA never loses a ride; an empty trip is not written.
  - *Once a day:* after the first successful read of the day.
  - *Each time the bike appears:* at the first read after every switch-on, and when the bike comes back into range (then the display shows 0 after a ride; HA has read it just before).
- **Set the clock automatically:** in the same connection as a read, after a daylight saving change, every 90 days and when first enabled.

A failed automatic write is tried again on later reads, at most three attempts a day. The **Reset trip** button also reads the trip into HA first, in the same connection.

## Dashboards and automations

- Distance per week as a statistics graph, and a ride log in a calendar: [docs/automations.md](https://github.com/Styx85/ha-tenways/blob/main/docs/automations.md#distance-per-period-and-ride-log).
- If you prefer automations over the options: examples to [set the clock](https://github.com/Styx85/ha-tenways/blob/main/docs/automations.md#example-set-the-clock-automatically) and to [clear the trip once a day](https://github.com/Styx85/ha-tenways/blob/main/docs/automations.md#example-a-fresh-trip-every-day) with the buttons. They need a second connection a few seconds after the read, so they can miss a bike that rides off at once.

## Limitations

- HA only reads the bike while it is switched on and in Bluetooth range; a ride counts when the bike is next seen at home.
- Current speed and power have not yet been checked while riding.
- More on polling, kept values, Bluetooth proxies and bug reports: [docs/how-it-works.md](https://github.com/Styx85/ha-tenways/blob/main/docs/how-it-works.md).

## Documentation

- [Entities](https://github.com/Styx85/ha-tenways/blob/main/docs/entities.md) · [Dashboards and automations](https://github.com/Styx85/ha-tenways/blob/main/docs/automations.md) · [How it works, limitations and troubleshooting](https://github.com/Styx85/ha-tenways/blob/main/docs/how-it-works.md)
- Protocol, test vectors and research notes: [tenways-ble](https://github.com/Styx85/tenways-ble)

## Acknowledgements / Credits

Based on and inspired by [stein155/cgo600-bridge](https://github.com/stein155/cgo600-bridge), which provided valuable groundwork for understanding the proprietary TENWAYS telemetry protocol and its integration with Home Assistant.

Many thanks to the original author and contributors. That project has since become [tenways-bridge](https://github.com/stein155/tenways-bridge), whose protocol notes agree with our field names (both derive from the TENWAYS app).

The Longtail Duo implementation was developed using independently captured Bluetooth HCI traffic from the official TENWAYS app. It uses the King Meter BLE transport rather than the Nordic UART Service used by the CGO600 bridge.

Unofficial; not affiliated with TENWAYS.
