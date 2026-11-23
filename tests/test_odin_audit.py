#!/usr/bin/env python3
"""Synthetic tests for tools/odin_audit.py.

Three shapes are generated: a real liblp super containing system+vendor+odm
(clean), a super without vendor/odm (critical), and a "super.img" that is really
a renamed ext4 system image (critical). They prove the audit logic, not any real
AP package.
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOL = os.path.join(ROOT, "tools", "odin_audit.py")
sys.path.insert(0, HERE)

from test_gsi_inspect import ext4_stub, sparse_image  # noqa: E402


def lp_super(partitions: list[str]) -> bytes:
    """Build a minimal liblp image with the given partition names (1 extent each)."""
    names = partitions
    part_blob = b"".join(
        name.encode().ljust(36, b"\x00") + struct.pack("<IIII", 0, index, 1, 0)
        for index, name in enumerate(names)
    )
    extent_blob = b"".join(struct.pack("<QIIQ", 2048, 0, index * 2048, 0)
                           for index in range(len(names)))
    group_blob = b"default".ljust(36, b"\x00") + struct.pack("<IQ", 0, 512 * 1024 * 1024)
    dev_blob = (struct.pack("<QIIQ", 0, 1 << 20, 0, 1024 * 1024 * 1024)
                + b"super".ljust(36, b"\x00") + struct.pack("<I", 0))

    header_size = 128
    tables = []
    cursor = header_size
    for blob, size in ((part_blob, 52), (extent_blob, 24), (group_blob, 48), (dev_blob, 64)):
        tables.append((cursor - header_size, len(blob) // size if size else 0, size))
        cursor += len(blob)

    header = bytearray(cursor)
    struct.pack_into("<IHHI", header, 0, 0x414C5030, 10, 0, header_size)
    for index, entry in enumerate(tables):
        struct.pack_into("<III", header, 44 + index * 12, *entry)  # classic layout
    header[header_size:] = part_blob + extent_blob + group_blob + dev_blob
    header[12:44] = b"\x00" * 32
    import hashlib
    header[12:44] = hashlib.sha256(bytes(header[:header_size])).digest()

    metadata_max = 8192
    geometry = bytearray(52)
    struct.pack_into("<II", geometry, 0, 0x616C4467, 52)
    struct.pack_into("<III", geometry, 40, metadata_max, 2, 4096)
    geometry[8:40] = b"\x00" * 32
    geometry[8:40] = hashlib.sha256(bytes(geometry)).digest()

    image = bytearray(4096 + 4096 + 4096 + metadata_max)
    image[4096:8192] = bytes(geometry).ljust(4096, b"\x00")
    image[8192:12288] = bytes(geometry).ljust(4096, b"\x00")   # backup geometry
    image[12288:12288 + len(header)] = header
    return bytes(image)


def make_tar(path: str, members: dict[str, bytes]) -> None:
    with tarfile.open(path, "w") as tf:
        for name, blob in members.items():
            tmp = path + "." + name
            with open(tmp, "wb") as fh:
                fh.write(blob)
            tf.add(tmp, arcname=name)
            os.remove(tmp)


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, check=False)


class OdinAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def audit(self, path: str) -> tuple[int, dict]:
        result = run(TOOL, path, "--json")
        return result.returncode, json.loads(result.stdout)

    def test_complete_super_is_clean(self):
        path = os.path.join(self.dir, "ok.tar")
        make_tar(path, {"super.img": lp_super(["system", "vendor", "odm", "product"])})
        code, report = self.audit(path)
        self.assertEqual(report["verdict"], "clean", report["findings"])
        self.assertEqual(code, 0)
        names = {p["name"] for p in report["members"][0]["lp"]["partitions"]}
        self.assertIn("vendor", names)

    def test_super_without_vendor_is_critical(self):
        path = os.path.join(self.dir, "novendor.tar")
        make_tar(path, {"super.img": lp_super(["system", "product"])})
        code, report = self.audit(path)
        self.assertEqual(report["verdict"], "critical")
        self.assertEqual(code, 2)
        self.assertTrue(any(f["code"] == "super-missing-vendor" for f in report["findings"]))

    def test_renamed_system_image_as_super_is_critical(self):
        path = os.path.join(self.dir, "renamed.tar")
        make_tar(path, {"super.img": ext4_stub(block_size=4096, blocks=4096)})
        code, report = self.audit(path)
        self.assertEqual(report["verdict"], "critical")
        self.assertEqual(code, 2)
        self.assertTrue(any(f["code"] == "super-not-lp" for f in report["findings"]))

    def test_bare_system_image_tar_is_only_informational(self):
        path = os.path.join(self.dir, "system.tar")
        make_tar(path, {"system.img": sparse_image(blocks=16, block_size=4096)})
        code, report = self.audit(path)
        self.assertEqual(report["verdict"], "clean", report["findings"])
        self.assertEqual(code, 0)
        self.assertTrue(any(f["code"] == "logical-partition-image" for f in report["findings"]))

    def test_directory_entry_is_only_a_note(self):
        # Samsung's stock AP TAR carries an explicit `meta-data/` directory entry
        # next to `meta-data/fota.zip`; that must not turn a good package into
        # "warnings" (the real 2026-11-22 build was flagged exactly this way).
        path = os.path.join(self.dir, "dirmember.tar")
        make_tar(path, {"super.img": lp_super(["system", "vendor", "odm", "product"])})
        with tarfile.open(path, "a") as tf:
            info = tarfile.TarInfo("meta-data")
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            tf.addfile(info)
            payload = b"x"
            info2 = tarfile.TarInfo("meta-data/fota.zip")
            info2.size = len(payload)
            import io as _io
            tf.addfile(info2, _io.BytesIO(payload))
        code, report = self.audit(path)
        self.assertEqual(report["verdict"], "clean", report["findings"])
        self.assertEqual(code, 0)
        self.assertTrue(any("meta-data" in n for n in report.get("notes", [])))

    def test_lz4_member_is_critical(self):
        path = os.path.join(self.dir, "lz4.tar")
        make_tar(path, {"boot.img": b"\x04\x22\x4d\x18" + b"\x00" * 512})
        code, report = self.audit(path)
        self.assertEqual(code, 2)
        self.assertTrue(any(f["code"] == "lz4-member" for f in report["findings"]))

    def test_md5_footer_is_flagged(self):
        path = os.path.join(self.dir, "footer.tar")
        make_tar(path, {"system.img": sparse_image(blocks=8)})
        with open(path, "ab") as fh:
            fh.write(b"0" * 32)
        code, report = self.audit(path)
        self.assertEqual(code, 1)
        self.assertTrue(report["md5_footer"])
        self.assertTrue(any(f["code"] == "md5-footer" for f in report["findings"]))


if __name__ == "__main__":
    unittest.main()
