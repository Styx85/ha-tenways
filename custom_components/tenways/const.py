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
# The Tenways app (2.18.0) names the optional status fields: 0x0B remainingRange,
# 0x23 power. It treats a range whose bytes include one >= 0x80 (655 = 0x028F
# at assist level 0) as 0, and ignores power above 3000.
MAX_POWER_W = 3000
