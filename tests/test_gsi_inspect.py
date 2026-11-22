#!/usr/bin/env python3
"""Synthetic tests for tools/gsi_inspect.py.

Fixtures are generated here: an Android-sparse image, an ext4-superblock stub and
a plain unknown blob, zipped up. They prove classification/extraction logic, not
anything about a real MysticGSI build.
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "gsi_inspect.py")


def sparse_image(blocks: int = 8, block_size: int = 4096) -> bytes:
    header = struct.pack(
        "<IHHHHIIII", 0xED26FF3A, 1, 0, 28, 12, block_size, blocks, 1, 0
    )
    payload = b"\x00" * (blocks * block_size)
    chunk = struct.pack("<HHII", 0xCAC1, 0, blocks, 12 + len(payload))
    return header + chunk + payload


def ext4_stub(block_size: int = 4096, blocks: int = 1024) -> bytes:
    blob = bytearray(4096)
    log_block = {
        1024: 0, 2048: 1, 4096: 2, 8192: 3, 16384: 4, 32768: 5, 65536: 6,
    }[block_size]
    struct.pack_into("<I", blob, 1024 + 4, blocks)
    struct.pack_into("<I", blob, 1024 + 24, log_block)
    struct.pack_into("<H", blob, 1080, 0xEF53)
    return bytes(blob)


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True, check=False
    )


class GsiInspectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.zip = os.path.join(self.dir, "Nothing-Asteroids-16-TEST-AB-MysticGSI.zip")
        with zipfile.ZipFile(self.zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("system.img", sparse_image(blocks=16, block_size=4096))
            zf.writestr("notes.txt", "synthetic fixture\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_classifies_sparse_system_image(self):
        result = run(TOOL, self.zip, "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        member = report["members"][0]
        self.assertEqual(member["name"], "system.img")
        self.assertEqual(member["container"], "android-sparse")
        self.assertEqual(member["expanded_bytes"], 16 * 4096)
        self.assertEqual(report["flavour"]["android_major_guess"], 16)
        self.assertTrue(report["flavour"]["ab_token"])
        self.assertEqual(report["image_count"], 1)

    def test_ext4_stub_and_compressed_member_are_reported(self):
        archive = os.path.join(self.dir, "mixed-AB.zip")
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("system.img", ext4_stub(block_size=4096, blocks=1024))
            zf.writestr("vendor.img.xz", b"\xfd7zXZ\x00")
        result = run(TOOL, archive, "--json")
        self.assertEqual(result.returncode, 1)  # compressed member is a problem
        report = json.loads(result.stdout)
        by_name = {m["name"]: m for m in report["members"]}
        self.assertEqual(by_name["system.img"]["container"], "ext4")
        self.assertEqual(by_name["system.img"]["expanded_bytes"], 4096 * 1024)
        self.assertEqual(by_name["vendor.img.xz"]["kind"], "compressed-image")

    def test_extract_refuses_overwrite(self):
        out = os.path.join(self.dir, "out")
        first = run(TOOL, self.zip, "--extract", out, "--only", "system.img")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        path = os.path.join(out, "system.img")
        self.assertTrue(os.path.isfile(path))
        with open(path, "rb") as fh:
            self.assertEqual(fh.read(4), struct.pack("<I", 0xED26FF3A))
        second = run(TOOL, self.zip, "--extract", out, "--only", "system.img")
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("refusing to overwrite", second.stderr)

    def test_zip_without_images_is_flagged(self):
        archive = os.path.join(self.dir, "noimg.zip")
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("readme.txt", "hello")
        result = run(TOOL, archive, "--json")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no .img member", result.stdout)


if __name__ == "__main__":
    unittest.main()
