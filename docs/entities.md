# Entities

Everything the integration exposes, where each value comes from, and how far it is confirmed. Back to the [README](../README.md).

## Exposed sensors

- Traction battery (%) from proprietary status field `0x0F`; 48 % in HA with 3 of 5 bars on the display.
- Odometer (km, field `0x0C`), trip distance (km, field `0x09`), maximum and average ride speed (km/h), accumulated ride time (shown in hours). Odometer and trip match the display; ride time and average speed agree with the distance.
  On the Longtail Duo these are lifetime counters: the trip values equal the odometer and keep counting until the trip is cleared, on the display or with the **Reset trip** button. Odometer, trip distance and ride time are `total_increasing`, so HA's statistics give distance and riding hours per day, week or month.
- Current speed from field `0x06` (disabled by default; read 0 while parked, not yet confirmed while riding).
- Firmware (`2.20.16` observed; the app shows `1.4.0` elsewhere, so this may be another component) and serial number, read once per HA start.
- Light on/off (binary sensor) from field `0x11` (0 = off); follows the headlight, also with automatic light.
- Remaining range from field `0x0B` (`remainingRange` in the TENWAYS app). It depends on the assist level and falls in proportion to the battery, and is not available at level 0, where the app also shows none. Neither the display nor the app shows it as a number and the unit is not stated; km is probable.

  | Assist level | 1 | 2 | 3 | 4 | 5 |
  |---|---|---|---|---|---|
  | at 68 % | 60 | 54 | 50 | 45 | 43 |
  | at 48 % | 43 | 38 | 35 | 32 | 31 |
- **Unverified:** power in W from field `0x23` (`power` in the app, values above 3000 ignored); 0 while parked, not yet seen while riding.
- **Computed by HA**, because the bike only knows the current trip (see [Totals over all trips and per day](#totals-over-all-trips-and-per-day)): total ride time, average and maximum speed over all trips, ride time and distance today.
- Disabled diagnostic sensors for the raw status fields `0x0B`, `0x11`, `0x23`, `0x4F`; `0x4F` is not interpreted.
- Standard Bluetooth battery (`0x2A19`): **not the traction battery**; on the Longtail Duo it counts up by 1 roughly every read while the bike is on and resets to 0 when it is switched off, so it looks like a counter. Disabled diagnostic sensor.
- Last successful read (shows how old the kept values are), BLE signal, last advertisement and optional Device Information characteristics.

No unlock, light, power, firmware, configuration or pairing commands are implemented. The two recorded read requests (device info, 4 keys; status, 11 keys) are sent via the `4348…0002` write characteristic on every poll; replies arrive through `4348…0003` notify, are reassembled if fragmented and must pass length and CRC-16/MODBUS checks. The only other things ever sent are the two writes the TENWAYS app also makes, each only when you press its button: the clock sync (**Set clock**) and clearing the trip (**Reset trip**). No spontaneous notifications were observed without a request.

## Totals over all trips and per day

Once the trip is cleared, the bike forgets its ride time, maximum and average. The integration therefore keeps its own totals from every successful read, stored per bike and kept across restarts:

| Sensor | How it is computed |
|---|---|
| Total ride time | the option *Ride time before HA counted* plus every increase of the trip's ride time; a lower value means the trip was cleared and counts again from 0 |
| Average speed overall | odometer ÷ total ride time |
| Maximum speed overall | highest trip maximum read; values above 75 km/h are ignored, as in the TENWAYS app. The disabled **Reset overall maximum speed** button sets it to 0 (sends nothing to the bike); the current trip's maximum then only counts once it is exceeded or a new trip starts |
| Ride time today, Distance today | increase of the trip's ride time and of the odometer since local midnight |

On the first read the current trip counts as ridden. If the trip was cleared before you installed this version, enter the ride time from before that reset in the options (Settings → Devices & services → TENWAYS → Configure), in hours, so that the overall average is right. Changing it later shows up in HA's long-term statistics of the total ride time as a one-off jump.

A drop of the ride time only counts as a cleared trip if the trip distance dropped too; otherwise the reading is ignored, so a glitch cannot count the trip twice.

HA only sees changes when it reads the bike: a ride after the last read of the evening counts for the day of the next read. Riding while the trip is cleared on the display and reading only afterwards also undercounts if the new trip has grown beyond the old one by then; with the **Reset trip** button HA knows about the reset.

## Resetting the trip

The **Reset trip** button (a configuration entity of the bike device) clears the trip like the display's "Clear trip" (hold [i], broom icon): trip distance, ride time, maximum and average speed go to 0, and so do the display's "CO₂ saved" and "trees saved", which it derives from the trip. The odometer stays. It is the TENWAYS app's own write; the app has it for the Longtail Duo but does not show it. Nothing is sent on its own; press it with the bike on and in range. Confirmed on a Longtail Duo: the bike acknowledges and the display shows 0.

HA's statistics are not affected: trip distance and ride time are `total_increasing`, so a reset starts a new cycle and the distance per day, week or month keeps counting.


The daily example is in [automations.md](automations.md#example-a-fresh-trip-every-day).

## Setting the bike's clock

The bike has no daylight saving and keeps showing summer time until it is set. The **Set clock** button (a configuration entity of the bike device) sends Home Assistant's local time to the bike, the same write the TENWAYS app makes. It sends nothing on its own; press it with the bike switched on and in range of an adapter or proxy, with the TENWAYS app closed. Press it again after each time change. Confirmed on a Longtail Duo: after a press the display changed from summer time to the correct local time to the minute; the assist level and everything else stay as they are.


The automatic example is in [automations.md](automations.md#example-set-the-clock-automatically).
