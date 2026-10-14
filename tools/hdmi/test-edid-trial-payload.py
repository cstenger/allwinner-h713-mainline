#!/usr/bin/env python3
"""Check exact audio EDID preservation and malformed-payload rejection."""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / 'tools/hdmi/make-edid-trial-code.py'
EDID = ROOT / 'tools/hdmi/fixtures/hdmi-audio-edid.hex'


class Payload(unittest.TestCase):
    def test_audio_extension_is_preserved_and_invalid_input_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = (Path(directory) / name for name in ('input.bin', 'payload.h'))
            data = bytes.fromhex(EDID.read_text())
            fixture_result = subprocess.run([sys.executable, str(GENERATOR), '--edid', str(EDID), str(output)], capture_output=True)
            self.assertEqual(fixture_result.returncode, 0, fixture_result.stderr)
            fixture_header = output.read_bytes()
            source.write_bytes(data)
            command = [sys.executable, str(GENERATOR), '--edid', str(source), str(output)]
            result = subprocess.run(command, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_bytes(), fixture_header)
            payload = output.read_text().split('static const u8 edid_trial_data[] = {', 1)[1]
            self.assertEqual(bytes(int(x, 16) for x in re.findall(r'0x([0-9a-f]{2})', payload)), data)
            corrupt = bytearray(data)
            corrupt[140] ^= 1
            for invalid in (data[:-1], bytes(corrupt), data[:128] + bytes(128)):
                output.unlink(missing_ok=True)
                source.write_bytes(invalid)
                result = subprocess.run(command, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
