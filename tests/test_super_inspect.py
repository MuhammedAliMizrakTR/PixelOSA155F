#!/usr/bin/env python3
"""Synthetic tests for tools/super_inspect.py.

The fixtures are *written by this test* using the documented liblp layout, so
they prove the parser's internal consistency (checksum handling, sparse prefix
decoding, extent/group arithmetic) — they are not a real ``super.img`` and say
nothing about the Emerald donor or the A155F target.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, "tools", "super_inspect.py")
SECTOR = 512
RESERVED = 4096
GEOMETRY_SIZE = 4096


def build_metadata() -> bytes:
    # (name, attributes, first_extent_index, num_extents, group_index)
    partitions = [
        ("system", 0, 0, 1, 0),
        ("vendor", 0, 1, 1, 0),
    ]
    extents = [(2048, 0, 0, 0), (4096, 0, 2048, 0)]
    groups = [("default", 0, 64 * 1024 * 1024)]
    block_devices = [(0, 1 << 20, 0, 128 * 1024 * 1024, "super", 0)]

    part_blob = b"".join(
        name.encode().ljust(36, b"\x00") + struct.pack("<IIII", attrs, first, num, group)
        for name, attrs, first, num, group in partitions
    )
    extent_blob = b"".join(
        struct.pack("<QIIQ", sectors, ttype, tdata, tsource)
        for sectors, ttype, tdata, tsource in extents
    )
    group_blob = b"".join(
        name.encode().ljust(36, b"\x00") + struct.pack("<IQ", flags, size)
        for name, flags, size in groups
    )
    dev_blob = b"".join(
        struct.pack("<QIIQ", first, align, aloff, size)
        + name.encode().ljust(36, b"\x00")
        + struct.pack("<I", flags)
        for first, align, aloff, size, name, flags in block_devices
    )

    header_size = 128
    offsets = {}
    cursor = header_size
    # descriptor offsets are relative to the table payload that starts at header_size
    for name, blob, size in (
        ("partitions", part_blob, 52),
        ("extents", extent_blob, 24),
        ("groups", group_blob, 48),
        ("block_devices", dev_blob, 64),
        ("flags", b"", 0),
    ):
        offsets[name] = (cursor - header_size, len(blob) // size if size else 0, size)
        cursor += len(blob)

    header = bytearray(cursor)
    struct.pack_into("<IHHI", header, 0, 0x414C5030, 10, 0, header_size)
    for index, name in enumerate(
        ["partitions", "extents", "groups", "block_devices", "flags"]
    ):
        struct.pack_into("<III", header, 44 + index * 12, *offsets[name])
    header[header_size:] = part_blob + extent_blob + group_blob + dev_blob
    header[12:44] = b"\x00" * 32
    digest = hashlib.sha256(bytes(header[:header_size])).digest()
    header[12:44] = digest
    return bytes(header)


def build_super() -> bytes:
    metadata = build_metadata()
    metadata_max_size = 8192
    geometry = bytearray(52)
    struct.pack_into("<II", geometry, 0, 0x616C4467, 52)
    struct.pack_into("<III", geometry, 40, metadata_max_size, 2, 4096)
    geometry[8:40] = b"\x00" * 32
    geometry[8:40] = hashlib.sha256(bytes(geometry)).digest()

    image = bytearray(RESERVED + 2 * GEOMETRY_SIZE + metadata_max_size)
    image[RESERVED:RESERVED + GEOMETRY_SIZE] = bytes(geometry).ljust(
        GEOMETRY_SIZE, b"\x00"
    )
    # liblp keeps a backup copy of the geometry immediately after the primary one
    image[RESERVED + GEOMETRY_SIZE:RESERVED + 2 * GEOMETRY_SIZE] = bytes(
        geometry
    ).ljust(GEOMETRY_SIZE, b"\x00")
    start = RESERVED + 2 * GEOMETRY_SIZE
    image[start:start + len(metadata)] = metadata
    return bytes(image)


def wrap_sparse(payload: bytes, block: int = 4096) -> bytes:
    blocks = (len(payload) + block - 1) // block
    padded = payload.ljust(blocks * block, b"\x00")
    header = struct.pack(
        "<IHHHHIIII", 0xED26FF3A, 1, 0, 28, 12, block, blocks, 1, 0
    )
    chunk = struct.pack("<HHII", 0xCAC1, 0, blocks, 12 + len(padded))
    return header + chunk + padded


def wrap_sparse_mixed(payload: bytes, block: int = 4096) -> bytes:
    """Sparse wrapper shaped like lpmake output: DONT_CARE + RAW + FILL chunks.

    ``payload`` must start with one all-zero block (the LP reserved area), so the
    leading DONT_CARE chunk preserves offsets. A parser that does not resync on
    each chunk header loses the metadata that follows the FILL chunk.
    """
    assert payload[:block].strip(b"\x00") == b"", "first block must be zero"
    body = payload[block:]                      # geometry + metadata + padding
    body_blocks = (len(body) + block - 1) // block
    body = body.ljust(body_blocks * block, b"\x00")
    chunks = bytearray()
    chunks += struct.pack("<HHII", 0xCAC3, 0, 1, 12)                     # dont-care
    chunks += struct.pack("<HHII", 0xCAC1, 0, body_blocks, 12 + len(body))  # raw
    chunks += body
    chunks += struct.pack("<HHII", 0xCAC2, 0, 1, 16) + b"\x00" * 4       # fill
    chunks += struct.pack("<HHII", 0xCAC3, 0, 1, 12)                     # dont-care
    header = struct.pack(
        "<IHHHHIIII", 0xED26FF3A, 1, 0, 28, 12, block, body_blocks + 3, 4, 0
    )
    return header + bytes(chunks)


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True, check=False
    )


class SuperInspectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.raw = os.path.join(self.dir, "super.img")
        with open(self.raw, "wb") as fh:
            fh.write(build_super())
        self.sparse = os.path.join(self.dir, "super.sparse.img")
        with open(self.sparse, "wb") as fh:
            fh.write(wrap_sparse(build_super()))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def report(self, path: str) -> dict:
        result = run(TOOL, path, "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_raw_metadata_tables(self):
        report = self.report(self.raw)
        self.assertEqual(report["container"], "liblp")
        self.assertTrue(report["geometry"]["checksum_ok"])
        self.assertTrue(report["header"]["checksum_ok"])
        names = [p["name"] for p in report["partitions"]]
        self.assertEqual(names, ["system", "vendor"])
        sizes = {p["name"]: p["size_bytes"] for p in report["partitions"]}
        self.assertEqual(sizes["system"], 2048 * SECTOR)
        self.assertEqual(sizes["vendor"], 4096 * SECTOR)
        group = report["groups"][0]
        self.assertEqual(group["name"], "default")
        self.assertEqual(
            group["used_bytes"], sizes["system"] + sizes["vendor"]
        )
        self.assertEqual(
            group["free_bytes"], group["maximum_size"] - group["used_bytes"]
        )

    def test_sparse_prefix_is_decoded(self):
        report = self.report(self.sparse)
        self.assertEqual(report["source"], "sparse")
        self.assertEqual(report["container"], "liblp")
        self.assertTrue(report["header"]["checksum_ok"])
        self.assertEqual(len(report["partitions"]), 2)

    def test_sparse_with_fill_and_dont_care_chunks_stays_in_sync(self):
        meta = build_super()
        # pad so LP geometry sits after the 2 leading blocks of the wrapper
        image = os.path.join(self.dir, "mixed.sparse.img")
        with open(image, "wb") as fh:
            fh.write(wrap_sparse_mixed(meta))
        report = self.report(image)
        self.assertEqual(report["container"], "liblp")
        self.assertTrue(report["header"]["checksum_ok"])
        self.assertEqual([p["name"] for p in report["partitions"]], ["system", "vendor"])

    def test_corrupt_checksum_is_refused(self):
        blob = bytearray(build_super())
        # flip a byte inside the fixed metadata header (a table descriptor):
        # liblp checksums the header struct itself, so this must be refused
        blob[RESERVED + 2 * GEOMETRY_SIZE + 49] ^= 0xFF
        broken = os.path.join(self.dir, "broken.img")
        with open(broken, "wb") as fh:
            fh.write(bytes(blob))
        result = run(TOOL, broken, "--json")
        self.assertEqual(result.returncode, 1)
        self.assertIn("checksum mismatch", result.stdout)

    def test_non_lp_image_reports_problem(self):
        plain = os.path.join(self.dir, "notsuper.img")
        with open(plain, "wb") as fh:
            fh.write(b"\x00" * (RESERVED + GEOMETRY_SIZE + 64))
        result = run(TOOL, plain, "--json")
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not use liblp", result.stdout)


if __name__ == "__main__":
    unittest.main()
