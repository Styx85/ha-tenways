"""TENWAYS BLE constants."""
DOMAIN = "tenways"
CONF_ADDRESS = "address"
NAME_PREFIX = "Tenways-ble-"
BATTERY_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
# Optional Bluetooth Device Information characteristics. May not be exposed.
DEVICE_INFO_UUIDS = {
    "manufacturer": "00002a29-0000-1000-8000-00805f9b34fb",
    "model": "00002a24-0000-1000-8000-00805f9b34fb",
    "firmware": "00002a26-0000-1000-8000-00805f9b34fb",
}
CONF_POLL_SECONDS = "poll_seconds"
POLL_SECONDS = 300
MIN_POLL_SECONDS = 30
MAX_POLL_SECONDS = 3600
ADVERTISEMENT_MAX_AGE_SECONDS = 120
KING_METER_TIMEOUT_SECONDS = 20  # whole King Meter exchange; the library's own timeout does not cover a stalled write
# Ride time before HA started counting (hours), e.g. from before the trip was first cleared.
CONF_RIDE_HOURS_BEFORE = "ride_hours_before"
# Advertised name prefixes of the King Meter models tenways-ble has a profile for.
KING_METER_NAME_PREFIXES = ("Longtail Duo", "CGO009", "CGO800", "AGO", "CARGO")
ISSUES_URL = "https://github.com/Styx85/ha-tenways/issues"
# Clear the trip automatically, in the poll's connection right after a read.
CONF_TRIP_RESET = "trip_reset"
TRIP_RESET_OFF = "off"
TRIP_RESET_DAILY = "daily"  # after the first read of each day
TRIP_RESET_RIDE = "ride"  # at each switch-on, so the display shows the current ride
TRIP_RESET_MODES = (TRIP_RESET_OFF, TRIP_RESET_DAILY, TRIP_RESET_RIDE)
# Set the clock in the same connection after a daylight saving change or every 90 days.
CONF_AUTO_CLOCK = "auto_clock"
