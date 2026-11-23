#!/usr/bin/env python3
"""Self-tests for gate G0 (tools/pin_gate.py) and the AP TAG parser (tools/gsi_tag.py).

Synthetic only: a few bytes on disk and a fake lock. They prove that an unpinned,
resized or re-hashed input is refused before any build reads it, and that the
Android level is taken from the tokens of the GSI name instead of field 3.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True, check=False
    )


class PinGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.payload = b"pinned-bytes" * 512
        self.gsi = os.path.join(self.dir, "Pixel-demo-15-1-AB-20260101-MysticGSI.zip")
        with open(self.gsi, "wb") as fh:
            fh.write(self.payload)
        self.lock = os.path.join(self.dir, "inputs.lock.json")
        self.write_lock(
            [
                {
                    "role": "donor-gsi-primary",
                    "name": "Pixel-demo-15-1-AB-20260101-MysticGSI.zip",
                    "size": len(self.payload),
                    "md5": hashlib.md5(self.payload).hexdigest(),
                }
            ]
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_lock(self, inputs: list[dict]) -> None:
        with open(self.lock, "w", encoding="utf-8") as fh:
            json.dump({"schema": "pixelosa155f.inputs/1", "inputs": inputs}, fh)

    def gate(self, path: str, *extra: str) -> subprocess.CompletedProcess:
        return run(os.path.join(TOOLS, "pin_gate.py"), "--lock", self.lock,
                   "--file", path, "--role", "donor-gsi-primary", *extra)

    def test_pinned_file_passes(self):
        result = self.gate(self.gsi)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("G0 gate: ok", result.stdout)

    def test_drive_copy_suffix_still_matches_the_pin(self):
        copy = self.gsi + " adlı dosyanın kopyası"
        with open(copy, "wb") as fh:
            fh.write(self.payload)
        result = self.gate(copy)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("extra suffix", result.stdout)

    def test_size_mismatch_is_refused(self):
        with open(self.gsi, "ab") as fh:
            fh.write(b"x")
        result = self.gate(self.gsi)
        self.assertEqual(result.returncode, 1)
        self.assertIn("size mismatch", result.stderr)

    def test_md5_mismatch_is_refused(self):
        # same length, different bytes: only the hash can catch this
        with open(self.gsi, "r+b") as fh:
            fh.write(b"P")
        result = self.gate(self.gsi)
        self.assertEqual(result.returncode, 1)
        self.assertIn("MD5 mismatch", result.stderr)

    def test_unpinned_file_is_refused(self):
        other = os.path.join(self.dir, "SomeOther-GSI.zip")
        with open(other, "wb") as fh:
            fh.write(b"whatever")
        result = self.gate(other)
        self.assertEqual(result.returncode, 1)
        self.assertIn("is not pinned", result.stderr)

    def test_missing_md5_pin_is_refused(self):
        self.write_lock([{"role": "donor-gsi-primary",
                          "name": os.path.basename(self.gsi),
                          "size": len(self.payload), "md5": None}])
        result = self.gate(self.gsi)
        self.assertEqual(result.returncode, 1)
        self.assertIn("no pinned MD5", result.stderr)


class GsiTagTests(unittest.TestCase):
    def tag(self, name: str, *extra: str) -> subprocess.CompletedProcess:
        return run(os.path.join(TOOLS, "gsi_tag.py"), *extra, name)

    def test_numeric_token_wins(self):
        result = self.tag("Pixel-raven-17-15063635-AB-20260327-MysticGSI.zip")
        self.assertEqual(result.stdout.strip(), "raven-A17", result.stderr)

    def test_codename_token_is_mapped(self):
        result = self.tag("Pixel-cheetah-CinnamonBun-14911996-AB-20260227-MysticGSI.zip")
        self.assertEqual(result.stdout.strip(), "cheetah-A17", result.stderr)

    def test_baklava_maps_to_16(self):
        result = self.tag("Pixel-raven-Baklava-14900000-AB-20260101-MysticGSI.zip")
        self.assertEqual(result.stdout.strip(), "raven-A16", result.stderr)

    def test_build_id_and_date_are_not_mistaken_for_a_level(self):
        result = self.tag("Pixel-cheetah-CinnamonBun-14911996-AB-20260227-MysticGSI.zip",
                          "--version")
        self.assertEqual(result.stdout.strip(), "17", result.stderr)

    def test_unknown_level_is_honest(self):
        result = self.tag("Pixel-mystery-unknownthing-AB-20260101-MysticGSI.zip")
        self.assertEqual(result.stdout.strip(), "mystery-Aunknown", result.stderr)


if __name__ == "__main__":
    unittest.main()
