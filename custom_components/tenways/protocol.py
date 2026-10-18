"""Longtail Duo status messages observed in an Android HCI recording.

Only the exact recorded read request is sent. No unlock, configuration,
firmware or light-control commands are implemented.
"""
from __future__ import annotations

# Recorded application telemetry request, without ATT opcode/handle.
STATUS_REQUEST = bytes.fromhex('30 0c 0b 06 07 08 09 11 0a 0b 0c 0f 23 4f 84 91 45')
WRITE_UUID = '43480002-f001-4b49-4e47-204d45544552'
NOTIFY_UUID = '43480003-f001-4b49-4e47-204d45544552'
SERVICE_UUID = '43480001-f001-4b49-4e47-204d45544552'
LONGTAIL_ADDRESS = 'E8:88:6C:31:B3:0D'


def decode_status(frame: bytes) -> dict[str, float | int]:
    """Parse TLV data in a recorded 0x30 status reply.

    The final two checksum bytes are not yet verified. We check framing and
    boundaries and require the expected TLV layout. Unsupported packets fail
    closed rather than creating misleading HA sensor values.
    """
    if len(frame) < 8 or frame[0] != 0x30 or frame[-1] != 0x45:
        raise ValueError('not a Longtail status frame')
    fields: dict[int, bytes] = {}
    pos, stop = 2, len(frame) - 3
    while pos < stop:
        if pos + 2 > stop:
            raise ValueError('truncated TLV header')
        key, size = frame[pos], frame[pos + 1]
        pos += 2
        if pos + size > stop or key in fields:
            raise ValueError('invalid TLV field')
        fields[key] = frame[pos:pos + size]
        pos += size
    if pos != stop:
        raise ValueError('invalid frame trailing bytes')
    expected = {0x07: 2, 0x08: 2, 0x09: 4, 0x0A: 4, 0x0C: 4, 0x0F: 1}
    if any(len(fields.get(k, b'')) != n for k, n in expected.items()):
        raise ValueError('incomplete status fields')
    num = lambda k: int.from_bytes(fields[k], 'big')
    battery = num(0x0F)
    if battery > 100:
        raise ValueError('battery out of range')
    return {
        'traction_battery': battery,
        'max_speed': num(0x07) / 10,
        'average_speed': num(0x08) / 10,
        'odometer': num(0x09) / 10,
        'ride_seconds': num(0x0A),
        'trip_distance': num(0x0C) / 10,
    }
