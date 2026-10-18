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
# Status field 0x0B, unverified: it follows the assist level on the parked bike
# (68 % battery). It may instead be a range estimate per assist level in km;
# then the values fall as the battery drains and the lookup stops matching.
RAW_0B_ASSIST_OFF = 655
ASSIST_LEVELS = {RAW_0B_ASSIST_OFF: 0, 60: 1, 54: 2, 50: 3, 45: 4, 43: 5}
