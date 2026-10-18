"""Read-only Longtail Duo King Meter BLE protocol."""
from __future__ import annotations

WRITE_UUID = "43480002-f001-4b49-4e47-204d45544552"
NOTIFY_UUID = "43480003-f001-4b49-4e47-204d45544552"
SERVICE_UUID = "43480001-f001-4b49-4e47-204d45544552"
LONGTAIL_ADDRESS = "E8:88:6C:31:B3:0D"

# Exact ATT payload observed in original TENWAYS Android HCI capture.
STATUS_REQUEST = bytes.fromhex(
    "62 00 0c 0b 06 07 08 09 11 0a 0b 0c 0f 23 4f 84 91 45"
)


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for octet in data:
        crc ^= octet
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


def decode_status(frame: bytes) -> dict[str, float | int]:
    """Validate full frame, CRC and TLV fields before returning telemetry."""
    if (len(frame) < 10 or frame[:2] != bytes((0x62, 0x00))
            or frame[3] != 0x0B or frame[-1] != 0x45):
        raise ValueError("not a Longtail Duo status response")

    if len(frame) != frame[2] + 6:
        raise ValueError("invalid response length")

    if int.from_bytes(frame[-3:-1], "big") != crc16_modbus(frame[:-3]):
        raise ValueError("CRC mismatch")

    fields: dict[int, bytes] = {}
    pos = 4
    end = len(frame) - 3

    while pos < end:
        if pos + 2 > end:
            raise ValueError("truncated TLV header")

        key, size = frame[pos], frame[pos + 1]
        pos += 2

        if pos + size > end or key in fields:
            raise ValueError("invalid or repeated TLV")

        fields[key] = frame[pos:pos + size]
        pos += size

    expected = {
        0x07: 2,
        0x08: 2,
        0x09: 4,
        0x0A: 4,
        0x0C: 4,
        0x0F: 1,
    }

    if any(len(fields.get(key, b"")) != width
           for key, width in expected.items()):
        raise ValueError("missing or malformed telemetry fields")

    number = lambda key: int.from_bytes(fields[key], "big")
    battery = number(0x0F)

    if battery > 100:
        raise ValueError("battery out of range")

    return {
        "traction_battery": battery,
        "max_speed": number(0x07) / 10,
        "average_speed": number(0x08) / 10,
        "odometer": number(0x09) / 10,
        "ride_seconds": number(0x0A),
        "trip_distance": number(0x0C) / 10,
    }
