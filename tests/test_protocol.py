"""Recorded Longtail Duo packet fixture (no other Bluetooth traffic)."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'custom_components/tenways/protocol.py'
spec = importlib.util.spec_from_file_location('tenways_protocol', path)
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)

REPLY = bytes.fromhex('300b06020000070201bf0802007e0904000004b11101000a04000085440b02028f0c04000004b10f0144230200004f010183d345')

class TestProtocol(unittest.TestCase):
    def test_real_status_packet(self):
        self.assertEqual(protocol.decode_status(REPLY), {
            'traction_battery': 68, 'max_speed': 44.7,
            'average_speed': 12.6, 'odometer': 120.1,
            'ride_seconds': 34116, 'trip_distance': 120.1,
        })

    def test_truncated_packet_rejected(self):
        with self.assertRaises(ValueError):
            protocol.decode_status(REPLY[:15] + b'\x45')

    def test_known_query(self):
        self.assertEqual(protocol.STATUS_REQUEST.hex(), '300c0b06070809110a0b0c0f234f849145')
