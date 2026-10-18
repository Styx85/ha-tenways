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
POLL_SECONDS = 300
ADVERTISEMENT_MAX_AGE_SECONDS = 120
