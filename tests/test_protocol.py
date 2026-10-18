"""Regression tests with original TENWAYS HCI frames."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "custom_components/tenways/protocol.py"
spec = importlib.util.spec_from_file_location("tenways_protocol", path)
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)

REQUEST = bytes.fromhex(
    "62 00 0c 0b 06 07 08 09 11 0a 0b 0c 0f 23 4f 84 91 45"
)

REPLY = bytes.fromhex(
    "62 00 30 0b 06 02 00 00 07 02 01 bf 08 02 00 7e "
    "09 04 00 00 04 b1 11 01 00 0a 04 00 00 85 44 "
    "0b 02 02 8f 0c 04 00 00 04 b1 0f 01 44 23 02 00 00 "
    "4f 01 01 83 d3 45"
)

class TestLongtailProtocol(unittest.TestCase):
    def test_request(self):
        self.assertEqual(protocol.STATUS_REQUEST, REQUEST)

    def test_request_crc(self):
        self.assertEqual(protocol.crc16_modbus(REQUEST[:-3]), 0x8491)

    def test_reply_crc(self):
        self.assertEqual(protocol.crc16_modbus(REPLY[:-3]), 0x83D3)

    def test_telemetry(self):
        self.assertEqual(protocol.decode_status(REPLY), {
            "traction_battery": 68,
            "max_speed": 44.7,
            "average_speed": 12.6,
            "odometer": 120.1,
            "ride_seconds": 34116,
            "trip_distance": 120.1,
        })

    def test_corrupted_crc(self):
        corrupted = bytearray(REPLY)
        corrupted[12] ^= 1
        with self.assertRaisesRegex(ValueError, "CRC"):
            protocol.decode_status(bytes(corrupted))

    def test_truncated_reply(self):
        with self.assertRaises(ValueError):
            protocol.decode_status(REPLY[:-4] + b"\\x45")

if __name__ == "__main__":
    unittest.main()
